"""
Config Registry — single source of truth for ALL external game config files.

Every external INI (skygfx.ini, gta_bridge.ini, LimitAdjuster.ini,
modloader/modloader.ini) is read, written, snapshotted, and reset through this
module.  No other code opens these files directly (except legacy paths that
will be migrated).

cp1252 / ASCII only.  ConfigParser strict=False, optionxform=str.
"""

import configparser
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Registry definition
# ---------------------------------------------------------------------------

FILES = {
    # key -> (game-relative path, ini-format flag, section-defaults dict)
    'gta_bridge': (
        'gta_bridge.ini',
        True,
        {'streaming_mem_mb': '2048', 'max_lod_scale': '4.0',
         'vegetation_boost': '1', 'sweep_log': '0'},
    ),
    'skygfx': (
        'skygfx.ini',
        True,
        {},  # defaults captured on first snapshot, not hardcoded
    ),
    'limit_adjuster': (
        'III.VC.SA.LimitAdjuster.ini',
        True,
        {},  # snapshot-driven
    ),
    'modloader': (
        'modloader/modloader.ini',
        True,
        {},  # snapshot-driven
    ),
    'player_options': (
        'PlayerOptions.ini',
        True,
        {
            'Gameplay.AutoAim': '0',
            'Density.CarMultiplier': '1.3',
            'Density.PedMultiplier': '1.3',
            'Player.FreeResprays': '1',
            'Debug.ShowMessages': '0',
        },
    ),
}

SNAPSHOT_REL = 'config_defaults_snapshot.json'


def _data_dir() -> Path:
    """Writable launcher_data dir: next to exe when frozen, repo dir in dev."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent / 'launcher_data'
    return Path(__file__).resolve().parent.parent / 'launcher_data'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parser() -> configparser.ConfigParser:
    cp = configparser.ConfigParser(strict=False)
    cp.optionxform = str  # preserve case of keys
    return cp


def _snapshot_path() -> Path:
    return _data_dir() / SNAPSHOT_REL


def _backup_dir() -> Path:
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return _data_dir() / 'backups' / f'config_reset_{stamp}'


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve(game_dir: str) -> Dict[str, Optional[str]]:
    """Return dict mapping each registry key to its absolute path (or None)."""
    gd = Path(game_dir)
    result: Dict[str, Optional[str]] = {}
    for key, (rel_path, _is_ini, _defaults) in FILES.items():
        abspath = gd / rel_path
        result[key] = str(abspath) if abspath.exists() else None
    return result


def read(key: str, game_dir: str) -> configparser.ConfigParser:
    """Parse the requested config file and return a ConfigParser.

    Raises KeyError if *key* is unknown.
    Returns an empty ConfigParser if the file does not exist or fails to parse.
    """
    if key not in FILES:
        raise KeyError(f"Unknown registry key: {key!r}")
    rel_path, _is_ini, _defaults = FILES[key]
    path = Path(game_dir) / rel_path
    cp = _parser()
    if path.exists():
        try:
            cp.read(str(path), encoding='utf-8')
        except configparser.Error:
            pass
    return cp


def save(key: str, game_dir: str, cp: configparser.ConfigParser) -> bool:
    """Write a ConfigParser back to the file for *key*.

    Returns True on success, False on OSError.
    """
    if key not in FILES:
        raise KeyError(f"Unknown registry key: {key!r}")
    rel_path, _is_ini, _defaults = FILES[key]
    path = Path(game_dir) / rel_path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(str(path), 'w', encoding='utf-8') as f:
            cp.write(f)
        return True
    except OSError:
        return False


def save_player_options(game_dir: str, values: Dict[str, str]) -> bool:
    """Write dotted-section.key values into PlayerOptions.ini preserving comments.

    *values* keys are dotted like ``'Density.CarMultiplier'``.
    Uses line-level regex replacement so comment blocks survive intact.
    If the file does not exist, copies the template first.
    Returns True on success.
    """
    path = Path(game_dir) / 'PlayerOptions.ini'
    if not path.exists():
        template = _data_dir() / 'templates' / 'PlayerOptions.ini'
        if template.exists():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(template), str(path))
            except OSError:
                return False
        else:
            return False

    try:
        text = path.read_text(encoding='utf-8')
    except OSError:
        return False

    for dotted_key, val in values.items():
        # dotted_key = 'Section.Key'
        if '.' not in dotted_key:
            continue
        _section, _key = dotted_key.rsplit('.', 1)
        val_str = str(val)
        # Replace existing key=value line; if not found, append after section header
        pattern = re.compile(
            r'(?m)^(\s*' + re.escape(_key) + r'\s*=\s*).*$')
        if pattern.search(text):
            text = pattern.sub(r'\g<1>' + val_str, text)
        else:
            # Append after the section header [Section]
            sec_pat = re.compile(
                r'(?m)^(\[' + re.escape(_section) + r'\]\s*)$')
            m = sec_pat.search(text)
            if m:
                # Insert new key=value line after the section header line
                pos = m.end()
                # Find the end of the section header line
                eol = text.find('\n', pos)
                if eol == -1:
                    text += '\n' + _key + '=' + val_str
                else:
                    insert_at = eol + 1
                    text = (text[:insert_at] + _key + '=' + val_str + '\n' +
                            text[insert_at:])

    try:
        path.write_text(text, encoding='utf-8')
        return True
    except OSError:
        return False


def snapshot_defaults(game_dir: str) -> Path:
    """First-run: snapshot raw bytes + full ini text per file.

    Skips if snapshot already exists.
    Returns the snapshot path.
    """
    snap = _snapshot_path()
    if snap.exists():
        return snap

    gd = Path(game_dir)
    records: Dict[str, dict] = {}
    for key, (rel_path, _is_ini, _defaults) in FILES.items():
        abspath = gd / rel_path
        if not abspath.exists():
            continue
        try:
            raw = abspath.read_bytes()
        except OSError:
            continue
        records[key] = {
            'bytes_b64': raw.hex(),  # hex-encoded for ASCII safety
            'sha256': hashlib.sha256(raw).hexdigest(),
            'text': raw.decode('utf-8', errors='replace'),
            'path': rel_path,
        }

    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text(json.dumps(records, indent=2), encoding='ascii')
    return snap


def reset_to_defaults(key: str, game_dir: str) -> bool:
    """Restore raw text from SNAPSHOT for *key*.

    Backs up current file to launcher_data/backups/config_reset_<ts>/ first.
    Returns False if no snapshot exists for *key*.
    """
    snap = _snapshot_path()
    if not snap.exists():
        return False

    try:
        records = json.loads(snap.read_text(encoding='ascii'))
    except (OSError, ValueError):
        return False

    if key not in records:
        return False

    rel_path, _is_ini, _defaults = FILES[key]
    target = Path(game_dir) / rel_path
    record = records[key]

    # backup current file
    if target.exists():
        bdir = _backup_dir()
        bdir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(str(target), str(bdir / target.name))
        except OSError:
            pass

    # restore from snapshot
    try:
        raw = bytes.fromhex(record['bytes_b64'])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        return True
    except (OSError, ValueError):
        return False


def preflight(game_dir: str) -> Tuple[bool, List[str]]:
    """Check all registered config files exist, parse, and have expected keys.

    Returns (ok, problems[]).
    """
    problems: List[str] = []
    gd = Path(game_dir)

    for key, (rel_path, is_ini, defaults) in FILES.items():
        abspath = gd / rel_path
        if not abspath.exists():
            problems.append(f"{key}: file not found ({rel_path})")
            continue

        if is_ini:
            # modloader.ini uses non-standard INI (bare values in some
            # sections); just verify it is readable as text.
            if key == 'modloader':
                try:
                    abspath.read_bytes()
                except OSError as e:
                    problems.append(f"{key}: unreadable — {e}")
                continue

            cp = _parser()
            try:
                cp.read(str(abspath), encoding='utf-8')
            except configparser.Error as e:
                problems.append(f"{key}: parse error — {e}")
                continue

            # gta_bridge must have [BRIDGE] section with core keys
            if key == 'gta_bridge':
                if not cp.has_section('BRIDGE'):
                    problems.append(f"{key}: missing [BRIDGE] section")
                else:
                    # only check the 3 core keys (sweep_log is optional)
                    for k in ('streaming_mem_mb', 'max_lod_scale',
                              'vegetation_boost'):
                        if not cp.has_option('BRIDGE', k):
                            problems.append(
                                f"{key}: [BRIDGE] missing key {k!r}")

    # snapshot must exist
    if not _snapshot_path().exists():
        problems.append("snapshot not found — run snapshot_defaults() first")

    return (len(problems) == 0, problems)