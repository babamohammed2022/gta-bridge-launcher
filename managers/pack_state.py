"""
Pack State Engine — availability state machine for GitHub-modpack DLC presets.

PRESET FORMAT (launcher_data/dlc_presets/<pack_id>.json):

    {
      "id": "my_pack",
      "title": "My Modpack",
      "description": "Description text.",
      "category": "graphics",
      "source": "github:owner/repo",        // or a direct download URL
      "version": "1.0",
      "parts": [
        {
          "name": "vehicle.txd",             // display name
          "dest_rel": "modloader/MyPack/vehicle.txd",  // game-root relative
          "source_url": "https://...",       // optional direct URL
          "archive_hint": "vehicles.zip",    // filename in Downloads cache
          "size": 123456,                    // optional, bytes
          "sha1": "abc..."                   // optional
        }
      ]
    }

State machine:

    MISSING ──(parts found locally)──▶ AVAILABLE ──(install)──▶ INSTALLED
       │                                                           │
       └──────────────────── (re-classify) ────────────────────────┘

Each part is classified independently; a pack's overall state is the worst
among its parts (MISSING > AVAILABLE > INSTALLED).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional

from installer_src.extractor import find_mod_in_archives, scan_archives

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

ProgressCb = Callable[[int, int], None]  # (current, total)
StageCb = Callable[[str], None]          # stage label


class PartState(Enum):
    INSTALLED = "installed"
    AVAILABLE = "available"
    MISSING = "missing"


@dataclass
class PartInfo:
    """Result for a single preset part."""

    name: str
    dest_rel: str
    state: PartState
    archive_path: Optional[str] = None  # set when AVAILABLE


@dataclass
class PackState:
    """Overall availability state for one preset pack."""

    state: PartState  # worst among parts
    missing_parts: List[PartInfo] = field(default_factory=list)
    available_parts: List[PartInfo] = field(default_factory=list)
    installed_parts: List[PartInfo] = field(default_factory=list)
    report: List[str] = field(default_factory=list)

    @property
    def is_installed(self) -> bool:
        return self.state == PartState.INSTALLED

    @property
    def is_available(self) -> bool:
        return self.state == PartState.AVAILABLE

    @property
    def is_missing(self) -> bool:
        return self.state == PartState.MISSING


# ---------------------------------------------------------------------------
# Default search dirs for archives
# ---------------------------------------------------------------------------

def _default_archive_dirs() -> List[str]:
    """Return default directories to scan for cached archives."""
    dirs: List[str] = []
    # User Downloads folder
    try:
        dirs.append(os.path.expanduser("~/Downloads"))
    except Exception:
        pass
    # Adjacent launcher_data/dlc_presets/archives/
    project_archives = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "launcher_data",
        "dlc_presets",
        "archives",
    )
    dirs.append(project_archives)
    return dirs


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _call_progress(cb: Optional[StageCb], stage: str) -> None:
    """Safely call a stage progress callback."""
    if cb:
        try:
            cb(stage)
        except Exception:
            pass


def _find_part_dict(preset: dict, dest_rel: str) -> Optional[dict]:
    """Return the part dict matching *dest_rel*, or None."""
    for p in (preset.get("parts") or []):
        if p.get("dest_rel") == dest_rel:
            return p
    return None


def _first_writable(dirs: List[str]) -> Optional[str]:
    """Return the first directory that exists and is writable."""
    for d in dirs:
        if os.path.isdir(d) and os.access(d, os.W_OK):
            return d
    return None


# ---------------------------------------------------------------------------
# _resolve_parts  (core classification logic)
# ---------------------------------------------------------------------------

def _resolve_parts(
    preset: dict,
    game_dir: str,
    search_dirs: List[str],
) -> PackState:
    """Core classification: scan *search_dirs* for archives and classify every part.

    Returns a PackState with parts grouped by state.
    """
    all_archives: List[str] = []
    for d in search_dirs:
        all_archives.extend(scan_archives(d))

    parts = preset["parts"]
    out = PackState(state=PartState.INSTALLED)

    for part in parts:
        name = part.get("name", "?")
        dest_rel = part.get("dest_rel", "")
        expected_size = part.get("size")
        archive_hint = part.get("archive_hint", "")

        full_path = os.path.join(game_dir, dest_rel) if dest_rel else ""
        pi = PartInfo(name=name, dest_rel=dest_rel, state=PartState.MISSING)

        # Check if part is already installed
        if full_path and os.path.isfile(full_path):
            if expected_size:
                actual = os.path.getsize(full_path)
                if actual == expected_size:
                    pi.state = PartState.INSTALLED
                else:
                    pi.state = PartState.MISSING
            else:
                pi.state = PartState.INSTALLED

        if pi.state == PartState.MISSING:
            if archive_hint:
                arc = find_mod_in_archives(all_archives, archive_hint, name)
                if arc:
                    pi.state = PartState.AVAILABLE
                    pi.archive_path = arc

        # Categorize
        if pi.state == PartState.MISSING:
            out.missing_parts.append(pi)
            out.state = PartState.MISSING
            line = f"{name} -> get: {part.get('source_url', 'N/A')} | place: {dest_rel}"
            out.report.append(line)
        elif pi.state == PartState.AVAILABLE:
            out.available_parts.append(pi)
            if out.state != PartState.MISSING:
                out.state = PartState.AVAILABLE
        else:
            out.installed_parts.append(pi)

    return out


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------

def classify(
    preset: dict,
    game_dir: str,
    extra_dirs: Optional[List[str]] = None,
) -> PackState:
    """Determine availability of every part in *preset*.

    For each part:
      INSTALLED — file exists at game_dir/dest_rel (size matches if given).
      AVAILABLE — not installed, but archive_hint found via
                  extractor.scan_archives / find_mod_in_archives over
                  extra_dirs (defaults: ~/Downloads, project archives dir).
      MISSING   — otherwise.

    Returns a PackState with arrays grouped by state.
    """
    if not preset.get("parts"):
        return PackState(state=PartState.INSTALLED)
    search_dirs: List[str] = extra_dirs if extra_dirs is not None else _default_archive_dirs()
    return _resolve_parts(preset, game_dir, search_dirs)


# ---------------------------------------------------------------------------
# _install_available_parts  (shared install logic)
# ---------------------------------------------------------------------------

def _install_available_parts(
    state: PackState,
    preset: dict,
    game_dir: str,
    log_lines: List[str],
    progress: Optional[ProgressCb] = None,
) -> tuple[bool, List[str]]:
    """Extract and place every AVAILABLE part in *state*.

    Returns (ok, log_lines) — caller must re-classify to verify.
    """
    if not state.available_parts:
        return False, log_lines

    # --- backup dir ---
    backup_root = Path(_backup_dir())
    backup_root.mkdir(parents=True, exist_ok=True)
    log_lines.append(f"Backup root: {backup_root}")

    # --- build a lookup: archive_path -> [parts that need it] ---
    arc_to_parts: dict[str, List[PartInfo]] = {}
    for pi in state.available_parts:
        if pi.archive_path:
            arc_to_parts.setdefault(pi.archive_path, []).append(pi)

    total_parts = len(state.available_parts)
    done = 0

    for arc_path, part_infos in arc_to_parts.items():
        if not os.path.isfile(arc_path):
            log_lines.append(f"Archive vanished: {arc_path}")
            continue

        # --- extract to temp ---
        tmpdir = tempfile.mkdtemp(prefix="pack_install_")
        try:
            from installer_src.extractor import extract

            def _sub_prog(cur: int, tot: int) -> None:
                if progress:
                    progress(done + cur, total_parts + len(arc_to_parts))

            extract(arc_path, tmpdir, progress=_sub_prog)

            # --- find each part in the extracted tree ---
            for pi in part_infos:
                dest_rel = pi.dest_rel
                basename = os.path.basename(dest_rel)
                src = _find_in_tree(tmpdir, basename)
                if not src:
                    log_lines.append(
                        f"  WARN: '{basename}' not found inside {arc_path}"
                    )
                    continue

                dst = os.path.join(game_dir, dest_rel)
                # backup existing
                if os.path.isfile(dst):
                    bdir = backup_root / os.path.dirname(dest_rel)
                    bdir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dst, str(bdir / basename))
                    log_lines.append(f"  Backed up: {dest_rel}")

                # place
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                log_lines.append(f"  Placed: {dest_rel}")
                done += 1
                if progress:
                    progress(done, total_parts)

        except Exception as e:
            log_lines.append(f"  ERROR extracting {arc_path}: {e}")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    return True, log_lines


# ---------------------------------------------------------------------------
# install_available
# ---------------------------------------------------------------------------

def install_available(
    preset: dict,
    game_dir: str,
    extra_dirs: Optional[List[str]] = None,
    progress: Optional[ProgressCb] = None,
) -> tuple[bool, List[str]]:
    """Install an AVAILABLE preset by extracting archives and placing parts.

    Steps per available part:
      1. Extract the matched archive to a temp directory.
      2. Locate the part file inside the extracted tree (by basename match).
      3. Backup any existing file at game_dir/dest_rel to
         launcher_data/backups/pack_install_<ts>/.
      4. Copy the part to game_dir/dest_rel.
      5. After all parts placed, re-classify — must return INSTALLED.

    Returns (ok, log_lines).
    """
    log_lines: List[str] = []

    # --- classify first to locate archives ---
    state = classify(preset, game_dir, extra_dirs=extra_dirs)
    if state.is_installed:
        return True, ["All parts already installed."]
    if not state.available_parts:
        return False, ["No available parts to install. Cannot proceed."]

    ok, log_lines = _install_available_parts(state, preset, game_dir, log_lines, progress)

    # --- re-classify to verify ---
    final = classify(preset, game_dir, extra_dirs=extra_dirs)
    if final.is_installed:
        log_lines.append("INSTALLED — all parts verified.")
        return True, log_lines
    else:
        for m in final.missing_parts:
            log_lines.append(f"  FAILED: {m.name} still missing after install")
        return False, log_lines


# ---------------------------------------------------------------------------
# install_or_download
# ---------------------------------------------------------------------------

def install_or_download(
    preset: dict,
    game_dir: str,
    extra_dirs: Optional[List[str]] = None,
    allow_network: bool = False,
    progress: Optional[StageCb] = None,
) -> tuple[bool, List[str]]:
    """Install a preset, optionally downloading MISSING parts over the network.

    Classification pass (same as install_available); for each MISSING part
    with ``source_url`` and ``allow_network=True``, download the archive to
    the first writable extra_dir (fallback: ``launcher_data/dlc_presets/archives/``),
    then continue the local install flow.

    Parts without ``source_url`` or whose download fails remain MISSING.

    Progress callback receives stage strings:
      ``'classify'``, ``'download <part_name>'``, ``'extract'``,
      ``'place <part_name>'``, ``'verify'``.

    Returns (ok, log_lines).
    """
    log_lines: List[str] = []

    if not preset.get("parts"):
        return True, ["No parts to install."]

    search_dirs: List[str] = extra_dirs if extra_dirs is not None else _default_archive_dirs()

    _call_progress(progress, "classify")
    state = _resolve_parts(preset, game_dir, search_dirs)

    if state.is_installed:
        return True, ["All parts already installed."]

    # --- Network download pass for MISSING parts ---
    if allow_network and state.missing_parts:
        dl_dir = _first_writable(search_dirs)
        if not dl_dir:
            dl_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "launcher_data",
                "dlc_presets",
                "archives",
            )
            os.makedirs(dl_dir, exist_ok=True)

        try:
            from installer_src.downloader import download as _dl
        except ImportError:
            log_lines.append("network unavailable (installer_src missing)")
            allow_network = False

        if allow_network:
            for pi in list(state.missing_parts):
                part = _find_part_dict(preset, pi.dest_rel)
                if not part or not part.get("source_url"):
                    log_lines.append(f"{pi.name}: no source_url, stays MISSING")
                    continue

                source_url = part["source_url"]
                hint = part.get("archive_hint", "")
                # Derive filename from archive_hint or URL basename
                if hint:
                    fname = hint
                else:
                    fname = source_url.split("?")[0].rstrip("/").split("/")[-1]
                if not fname or ("." not in fname):
                    fname = f"{pi.name}.zip"

                dest_path = os.path.join(dl_dir, fname)

                _call_progress(progress, f"download {pi.name}")
                try:
                    _dl(source_url, dest_path)
                    log_lines.append(f"Downloaded {pi.name} -> {fname}")
                except Exception as e:
                    log_lines.append(f"Download failed for {pi.name}: {e}")
                    continue

            # Re-classify now that new archives may exist
            _call_progress(progress, "classify")
            state = _resolve_parts(preset, game_dir, search_dirs)

    # --- Nothing to install ---
    if not state.available_parts:
        for pi in state.missing_parts:
            log_lines.append(f"{pi.name}: MISSING (no source or download failed)")
        if not log_lines:
            log_lines.append("No available parts to install.")
        return False, log_lines

    # --- Install available parts ---
    _call_progress(progress, "extract")

    # Wrap StageCb -> ProgressCb for the shared helper
    placed = [0]
    total_to_place = len(state.available_parts)

    def _int_prog(cur: int, _tot: int) -> None:
        placed[0] = cur
        _call_progress(progress, f"place {cur}/{total_to_place}")

    ok, log_lines = _install_available_parts(state, preset, game_dir, log_lines, _int_prog)

    # --- Verify ---
    _call_progress(progress, "verify")
    final = _resolve_parts(preset, game_dir, search_dirs)
    if final.is_installed:
        log_lines.append("INSTALLED — all parts verified.")
        return True, log_lines
    else:
        for m in final.missing_parts:
            log_lines.append(f"  FAILED: {m.name} still missing after install")
        return False, log_lines


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_in_tree(root: str, basename: str) -> Optional[str]:
    """Walk *root* and return the first file whose basename matches."""
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.lower() == basename.lower():
                return os.path.join(dirpath, f)
    return None


def _backup_dir() -> str:
    """Return a timestamped backup directory path."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project, "launcher_data", "backups", f"pack_install_{stamp}")


# ---------------------------------------------------------------------------
# load_presets
# ---------------------------------------------------------------------------

def load_presets(directory: str) -> List[dict]:
    """Load all .json preset files from *directory* with error tolerance.

    Returns a list of parsed preset dicts. Files that fail to parse or
    lack the expected "id" / "parts" keys are skipped with a warning.
    """
    presets: List[dict] = []
    if not os.path.isdir(directory):
        log.warning("Preset directory not found: %s", directory)
        return presets

    for entry in sorted(os.listdir(directory)):
        if not entry.lower().endswith(".json"):
            continue
        path = os.path.join(directory, entry)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Skipping %s — %s", entry, e)
            continue

        if not isinstance(data, dict) or "id" not in data or "parts" not in data:
            log.warning("Skipping %s — missing 'id' or 'parts'", entry)
            continue

        presets.append(data)

    return presets


# ---------------------------------------------------------------------------
# fetch_github_presets
# ---------------------------------------------------------------------------

def fetch_github_presets(
    owner_repo: str,
) -> List[dict]:
    """Fetch preset definitions from a GitHub release asset.

    Uses downloader.resolve_github_release to locate the release, then
    looks for an asset named matching '*preset*.json'.

    **IMPORTANT**: This function makes network calls.  Tests MUST NOT hit
    the network — mock ``installer_src.downloader.resolve_github_release``
    or set up a local fixture.  Network errors are caught and produce
    a warning + empty list return.

    Returns a list of preset dicts (may be empty).
    """
    from installer_src.downloader import resolve_github_release

    releases_url = f"https://github.com/{owner_repo}/releases"
    try:
        release_asset_url = resolve_github_release(releases_url)
    except Exception as e:
        log.warning("GitHub release resolution failed for %s: %s", owner_repo, e)
        return []

    if not release_asset_url:
        log.warning("No release asset URL resolved for %s", owner_repo)
        return []

    # The resolved URL is a .zip download.  We expect the release to contain
    # a JSON file named *preset*.json.  Attempt to fetch it directly.
    # (In production the release .zip would be downloaded and inspected;
    #  this implementation focuses on the protocol stub.)
    import requests
    from installer_src import config as dl_config

    try:
        resp = requests.get(
            release_asset_url,
            headers={"User-Agent": dl_config.HTTP_USER_AGENT},
            timeout=dl_config.HTTP_TIMEOUT,
        )
        resp.raise_for_status()
    except Exception as e:
        log.warning("Failed to download release asset for %s: %s", owner_repo, e)
        return []

    # If the asset itself is JSON, parse as a single preset or list
    if release_asset_url.lower().endswith(".json"):
        try:
            data = resp.json()
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "id" in data:
                return [data]
        except Exception as e:
            log.warning("GitHub preset JSON parse failed: %s", e)
            return []

    # For .zip assets, note the limitation
    log.info(
        "GitHub asset is a .zip (%s); download and inspect "
        "manually or configure a direct JSON asset URL.",
        release_asset_url,
    )
    return []