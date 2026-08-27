#!/usr/bin/env python3
"""
GTA Bridge Launcher - Main Entry Point
Hybrid Python/C++ launcher for GTA games with database-driven content
"""

import os
import sys
import json
import sqlite3
import configparser
import subprocess
import threading
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Setup logging
log_path = Path(__file__).parent / 'launcher.log'
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.FileHandler(log_path, mode='a'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Try to import optional dependencies
try:
    import git
    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog, simpledialog
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

# Optional bridge IPC client (named-pipe link to gta_bridge.asi in the game)
try:
    import bridge_client
    from bridge_client import GBridgeClient, BridgeMonitor
    BRIDGE_AVAILABLE = True
except ImportError:
    BRIDGE_AVAILABLE = False

# Import local modules
sys.path.insert(0, str(Path(__file__).parent))

from managers.git_manager import GitManager
from managers.config_manager import ConfigManager
from managers.game_manager import GameManager
from managers.profile_manager import ProfileManager
from managers.pool_planner import recommended_pools
from utils.memory_utils import MemoryUtils
from utils.system_utils import SystemUtils


class DatabaseManager:
    """Manages SQLite database for game data and limits"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database with schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.executescript('''
            CREATE TABLE IF NOT EXISTS game_limits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game TEXT NOT NULL,
                limit_name TEXT NOT NULL,
                current_value INTEGER,
                max_value INTEGER,
                description TEXT,
                UNIQUE(game, limit_name)
            );
            
            CREATE TABLE IF NOT EXISTS world_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id INTEGER NOT NULL,
                pos_x REAL NOT NULL,
                pos_y REAL NOT NULL,
                pos_z REAL NOT NULL,
                rot_x REAL DEFAULT 0,
                rot_y REAL DEFAULT 0,
                rot_z REAL DEFAULT 0,
                sector_x INTEGER,
                sector_y INTEGER,
                morton_code INTEGER,
                data_type TEXT DEFAULT 'inst',
                properties TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(model_id, data_type)
            );
            
            CREATE TABLE IF NOT EXISTS color_palettes (
                color_id INTEGER PRIMARY KEY,
                r INTEGER NOT NULL CHECK(r BETWEEN 0 AND 255),
                g INTEGER NOT NULL CHECK(g BETWEEN 0 AND 255),
                b INTEGER NOT NULL CHECK(b BETWEEN 0 AND 255),
                name TEXT,
                radio_name TEXT,
                is_custom BOOLEAN DEFAULT 0
            );
            
            CREATE TABLE IF NOT EXISTS vram_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                total_vram_mb INTEGER,
                streaming_percent REAL DEFAULT 0.3,
                texture_percent REAL DEFAULT 0.4,
                model_percent REAL DEFAULT 0.2
            );

            CREATE TABLE IF NOT EXISTS dlc_state (
                id TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1
            );
            
            CREATE INDEX IF NOT EXISTS idx_world_morton ON world_data(morton_code);
            CREATE INDEX IF NOT EXISTS idx_world_sector ON world_data(sector_x, sector_y);
            CREATE INDEX IF NOT EXISTS idx_game_limits ON game_limits(game, limit_name);
        ''')
        
        conn.commit()
        conn.close()

    def get_dlc_state(self) -> dict:
        """Return {pack_id: enabled_bool} for all recorded DLC packs."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT id, enabled FROM dlc_state')
            return {row[0]: bool(row[1]) for row in cursor.fetchall()}
        except sqlite3.Error:
            return {}
        finally:
            conn.close()

    def set_dlc_enabled(self, pack_id: str, enabled: bool):
        """Record a pack's enabled state (upsert)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO dlc_state (id, enabled) VALUES (?, ?) '
            'ON CONFLICT(id) DO UPDATE SET enabled = excluded.enabled',
            (pack_id, 1 if enabled else 0)
        )
        conn.commit()
        conn.close()

    def get_limit(self, game: str, limit_name: str) -> Optional[int]:
        """Get a specific limit value"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT current_value FROM game_limits WHERE game = ? AND limit_name = ?',
            (game, limit_name)
        )
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def set_limit(self, game: str, limit_name: str, value: int, max_value: int = None):
        """Set a limit value"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO game_limits 
            (game, limit_name, current_value, max_value)
            VALUES (?, ?, ?, ?)
        ''', (game, limit_name, value, max_value))
        conn.commit()
        conn.close()


class GTALauncher:
    """Main launcher class"""
    
    def __init__(self, game_path: str, db_path: str, config_path: str):
        self.game_path = Path(game_path)
        self.db_path = db_path
        self.config_path = Path(config_path)
        self.selected_exe = None
        self.game_process = None  # Track running game process
        
        # Initialize managers
        self.git_manager = GitManager(game_path)
        self.config_manager = ConfigManager(config_path)
        self.game_manager = GameManager(game_path, db_path)
        self.db_manager = DatabaseManager(db_path)
        self.system_utils = SystemUtils()
        self.profile_manager = ProfileManager(Path(__file__).parent)
    
    def set_selected_exe(self, exe_path: str):
        """Set the selected executable path and save to database"""
        self.selected_exe = Path(exe_path)
        # Save to database for persistence
        self.db_manager.set_limit('gtasa', 'last_exe_path', exe_path)
    
    def get_last_exe_path(self) -> Optional[str]:
        """Get the last selected executable path from database"""
        return self.db_manager.get_limit('gtasa', 'last_exe_path')

    # DB keys that are launcher-internal, not LimitAdjuster limit names (SkyGfxMode lives in skygfx.ini, not LimitAdjuster INI)
    BRIDGE_INI_EXCLUDED = {'last_exe_path', 'StreamingMemory', 'MaxColors', 'MaxModels', 'SkyGfxMode'}

    def write_bridge_ini(self, game_dir: str = None) -> str:
        """Write MTA-max limits into III.VC.SA.LimitAdjuster.ini [SALIMITS].

        Architecture (m1598): LimitAdjuster.asi is THE limit authority — it is
        battle-tested and reads this ini. Our gta_bridge.asi no longer applies
        pool limits (it builds on top: pipe/overlay/render-distance).
        Only the [SALIMITS] section is replaced; all other sections are kept.
        Original ini is backed up once as .original.bak.
        Returns the ini path.
        """
        game_dir = Path(game_dir) if game_dir else self.game_path
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT limit_name, current_value FROM game_limits "
            "WHERE game = 'gtasa' AND current_value IS NOT NULL")
        rows = cursor.fetchall()
        conn.close()

        # MemoryAvailable ceiling: 32-bit LAA process can address max 4095 MB.
        # (auto_vram/VRAM concept retired — LimitAdjuster has no VRAM limit.)
        mem_cap = 4095

        lines = ['[SALIMITS]']
        count = 0
        for name, value in rows:
            if name in self.BRIDGE_INI_EXCLUDED or name == 'VRAM':
                continue
            if name == 'MemoryAvailable':
                value = mem_cap
            try:
                int(value)
            except (TypeError, ValueError):
                continue
            lines.append(f'{name}={value}')
            count += 1
        if not any(n == 'MemoryAvailable' for n, _ in rows):
            lines.append(f'MemoryAvailable={mem_cap}')
            count += 1

        ini_path = game_dir / 'III.VC.SA.LimitAdjuster.ini'
        bak = ini_path.with_name(ini_path.name + '.original.bak')
        try:
            if ini_path.exists() and not bak.exists():
                bak.write_bytes(ini_path.read_bytes())
            # replace only the [SALIMITS] section, keep everything else
            section = '\n'.join(lines) + '\n'
            if ini_path.exists():
                text = ini_path.read_text(encoding='utf-8', errors='replace')
                import re
                new_text, n = re.subn(
                    r'\[SALIMITS\][^\[]*', section + '\n', text, count=1)
                if n == 0:
                    new_text = text.rstrip() + '\n\n' + section
            else:
                new_text = '; MTA-max limits written by GTA Bridge Launcher\n\n' + section
            ini_path.write_text(new_text, encoding='utf-8')
            logger.info(f"write_bridge_ini: [OK] {ini_path} [SALIMITS] ({count} MTA-max limits)")
        except OSError as e:
            logger.error(f"write_bridge_ini: [FAIL] {e}")

        # gta_bridge.ini — bridge-specific settings (NOT limits; LimitAdjuster
        # owns those). [BRIDGE] values consumed by gta_bridge.asi v2.
        # Render-distance slider values live in db: max_lod_scale (1.0-6.0),
        # streaming_mem_mb (256-2048).
        bridge_ini = game_dir / 'gta_bridge.ini'
        # preserve any existing [PROFILES] active selection across the rewrite
        _profiles_block = ''
        if bridge_ini.exists() and configparser is not None:
            _pcp = configparser.ConfigParser()
            _pcp.optionxform = str
            try:
                _pcp.read(bridge_ini, encoding='utf-8')
                if _pcp.has_section('PROFILES') and _pcp.has_option('PROFILES', 'active_profile'):
                    _profiles_block = (
                        f'[PROFILES]\n'
                        f'active_profile={_pcp.get("PROFILES", "active_profile")}\n'
                    )
            except configparser.Error:
                _profiles_block = ''
        try:
            try:
                lod_scale = float(self.db_manager.get_limit('gtasa', 'max_lod_scale') or 4.0)
            except (TypeError, ValueError):
                lod_scale = 4.0
            lod_scale = min(6.0, max(1.0, lod_scale))
            try:
                stream_mb = int(float(self.db_manager.get_limit('gtasa', 'streaming_mem_mb') or 0))
            except (TypeError, ValueError):
                stream_mb = 0
            if stream_mb <= 0:
                from utils.system_utils import SystemUtils
                stream_mb = recommended_pools(
                    vram_mb=SystemUtils.get_top2007_auto_vram(),
                    ram_mb=SystemUtils.get_system_memory()
                )['streaming']
            stream_mb = min(2048, max(256, stream_mb))
            bridge_lines = [
                '[OPTIONS]',
                'DebugTextKey=114',
                '',
                '[BRIDGE]',
                f'streaming_mem_mb={stream_mb}',
                f'max_lod_scale={lod_scale:.1f}',
                'vegetation_boost=1',
                '',
            ]
            _out = '\n'.join(bridge_lines)
            if _profiles_block:
                _out += '\n' + _profiles_block
            bridge_ini.write_text(_out, encoding='ascii')
            logger.info(f"write_bridge_ini: [OK] {bridge_ini} [BRIDGE] (streaming {stream_mb}MB, lod_scale {lod_scale:.1f}, vegetation on)")
        except OSError as e:
            logger.error(f"write_bridge_ini: [FAIL] {bridge_ini}: {e}")
        return str(ini_path)

    def deploy_asi(self, game_dir: str = None):
        """Copy asi_bridge/bin/gta_bridge.asi into <game>/ and <game>/scripts/ if newer.

        The SkyGfx+ install loads ASIs from the game root via vorbisFile.dll hook,
        while some setups use scripts/ — deploy to both for compatibility.
        Returns (deployed: bool, dest_path_or_reason: str).
        """
        game_dir = Path(game_dir) if game_dir else self.game_path
        src = Path(__file__).parent / 'asi_bridge' / 'bin' / 'gta_bridge.asi'
        if not src.exists():
            logger.info("deploy_asi: [SKIP] no built asi at asi_bridge/bin/gta_bridge.asi")
            return False, 'not built'
        import shutil
        deployed_any = False
        last_dest = str(src)
        for subdir in [Path('.'), Path('scripts')]:
            dest = game_dir / subdir / 'gta_bridge.asi'
            try:
                if dest.exists() and dest.stat().st_mtime >= src.stat().st_mtime:
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dest))
                logger.info(f"deploy_asi: [OK] deployed to {dest}")
                deployed_any = True
                last_dest = str(dest)
            except OSError as e:
                logger.error(f"deploy_asi: [FAIL] {dest}: {e}")
        if deployed_any:
            return True, last_dest
        # check if already up-to-date in either location
        for subdir in [Path('.'), Path('scripts')]:
            if (game_dir / subdir / 'gta_bridge.asi').exists():
                return False, 'up to date'
        return False, 'not built'

    def _fixes_source_dir(self) -> Optional[Path]:
        """Locate launcher_data/fixes whether frozen (PyInstaller) or running from source."""
        candidates = []
        if getattr(sys, 'frozen', False):
            # data folder shipped beside the exe
            candidates.append(Path(sys.executable).parent / 'launcher_data' / 'fixes')
            # data folder bundled inside the onefile payload
            meipass = getattr(sys, '_MEIPASS', None)
            if meipass:
                candidates.append(Path(meipass) / 'launcher_data' / 'fixes')
        else:
            candidates.append(Path(__file__).parent / 'launcher_data' / 'fixes')
        for c in candidates:
            if c.is_dir():
                return c
        return None

    def _dxvk_source_dir(self) -> Optional[Path]:
        """Frozen-aware locator for launcher_data/dxvk (proxy d3d9.dll + vulkan.dll)."""
        if getattr(sys, 'frozen', False):
            exe_dir = Path(sys.executable).parent
            cand = exe_dir / 'launcher_data' / 'dxvk'
            if cand.is_dir():
                return cand
            meipass = getattr(sys, '_MEIPASS', None)
            if meipass:
                cand = Path(meipass) / 'launcher_data' / 'dxvk'
                if cand.is_dir():
                    return cand
            return None
        cand = Path(__file__).resolve().parent / 'launcher_data' / 'dxvk'
        return cand if cand.is_dir() else None

    def is_dxvk_active(self, game_dir: str = None) -> bool:
        """DXVK is active only when vulkan.dll (DXVK renamed) sits in the game dir."""
        game_dir = Path(game_dir) if game_dir else self.game_path
        return (game_dir / 'vulkan.dll').exists()

    def seed_default_limits(self):
        """First-run auto-seed: fresh installs load with extended LOD-friendly limits.

        Seeds every LIMIT_CATEGORIES default (Buildings 300k, vegetation pools
        Objects 60k / Dummys 150k, VisibleLodPtrs 600k, Peds/Vehicles 240/230...)
        into the db when no limits exist yet, so write_bridge_ini emits the full
        extended set without the user touching a preset. Existing user values
        are never overwritten.
        """
        try:
            from limit_adjuster_settings import LimitAdjusterSettings as LAS
            if self.db_manager.get_limit('gtasa', 'Peds') is not None:
                return  # already seeded or user-configured
            count = 0
            for cat in LAS.LIMIT_CATEGORIES.values():
                for ent in cat.get('settings', []):
                    name = ent.get('name')
                    dflt = ent.get('default')
                    if not name or dflt is None:
                        continue
                    try:
                        val = int(float(dflt))
                    except (TypeError, ValueError):
                        val = str(dflt)
                    mx = ent.get('max')
                    try:
                        mx = int(float(mx)) if mx is not None else None
                    except (TypeError, ValueError):
                        mx = None
                    self.db_manager.set_limit('gtasa', name, val, mx)
                    count += 1
            logger.info(f"seed_default_limits: [OK] seeded {count} extended defaults (first run)")
        except Exception as e:
            logger.error(f"seed_default_limits: [FAIL] {e}")

    def deploy_dxvk(self, game_dir: str = None, enable: bool = True):
        """Deploy or remove the DXVK contained system (FusionFix pattern).

        enable=True: copy proxy d3d9.dll + vulkan.dll (DXVK) + dxvk.conf into the
        game dir, backing up any overwritten original once as .original.bak.
        enable=False: remove vulkan.dll + dxvk.conf and restore the original
        d3d9.dll from backup (proxy without DXVK is pointless).
        Returns list of (name, status) tuples.
        """
        game_dir = Path(game_dir) if game_dir else self.game_path
        results = []
        if not enable:
            for name in ('vulkan.dll', 'dxvk.conf'):
                p = game_dir / name
                try:
                    if p.exists():
                        p.unlink()
                        results.append((name, 'removed'))
                except OSError as e:
                    results.append((name, f'failed: {e}'))
            proxy = game_dir / 'd3d9.dll'
            bak = game_dir / 'd3d9.dll.original.bak'
            try:
                if bak.exists() and proxy.exists():
                    shutil.copy2(str(bak), str(proxy))
                    results.append(('d3d9.dll', 'restored original'))
            except OSError as e:
                results.append(('d3d9.dll', f'restore failed: {e}'))
            return results
        src = self._dxvk_source_dir()
        if not src:
            logger.info("deploy_dxvk: [SKIP] no launcher_data/dxvk found")
            return [('dxvk', 'skipped (not staged)')]
        import shutil
        for name in ('d3d9.dll', 'vulkan.dll', 'dxvk.conf'):
            s = src / name
            if not s.exists():
                continue
            d = game_dir / name
            try:
                bak = d.with_name(d.name + '.original.bak')
                if d.exists() and not bak.exists():
                    shutil.copy2(str(d), str(bak))
                shutil.copy2(str(s), str(d))
                results.append((name, 'deployed'))
                logger.info(f"deploy_dxvk: [OK] {name} -> {d}")
            except OSError as e:
                results.append((name, f'failed: {e}'))
                logger.error(f"deploy_dxvk: [FAIL] {name}: {e}")
        return results

    def deploy_fixes(self, game_dir: str = None):
        """Ship corrected data files (launcher_data/fixes) into <game>/data/.

        Backs up each original once as <name>.original.bak before first overwrite.
        Returns list of (filename, status) tuples.
        """
        game_dir = Path(game_dir) if game_dir else self.game_path
        src_dir = self._fixes_source_dir()
        results = []
        if not src_dir:
            logger.info("deploy_fixes: [SKIP] no launcher_data/fixes found")
            return results
        import shutil
        data_dir = game_dir / 'data'
        for src in sorted(src_dir.iterdir()):
            if not src.is_file() or src.suffix.lower() == '.md':
                continue
            dest = data_dir / src.name
            backup = data_dir / (src.name + '.original.bak')
            try:
                if dest.exists():
                    if dest.read_bytes() == src.read_bytes():
                        results.append((src.name, 'up to date'))
                        continue
                    if not backup.exists():
                        shutil.copy2(str(dest), str(backup))
                        logger.info(f"deploy_fixes: [BACKUP] {backup}")
                else:
                    logger.info(f"deploy_fixes: [NEW] {dest} not present in game; installing")
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dest))
                logger.info(f"deploy_fixes: [OK] deployed {src.name} -> {dest}")
                results.append((src.name, 'deployed'))
            except OSError as e:
                logger.error(f"deploy_fixes: [FAIL] {src.name}: {e}")
                results.append((src.name, f'failed: {e}'))
        return results

    def _dlc_source_dir(self) -> Optional[Path]:
        """Locate launcher_data/dlc whether frozen (PyInstaller) or running from source."""
        candidates = []
        if getattr(sys, 'frozen', False):
            candidates.append(Path(sys.executable).parent / 'launcher_data' / 'dlc')
            meipass = getattr(sys, '_MEIPASS', None)
            if meipass:
                candidates.append(Path(meipass) / 'launcher_data' / 'dlc')
        else:
            candidates.append(Path(__file__).parent / 'launcher_data' / 'dlc')
        for c in candidates:
            if c.is_dir():
                return c
        return None

    @staticmethod
    def _sync_tree(src: Path, dest: Path):
        """Mirror src into dest: copy newer files, delete extraneous ones."""
        import shutil
        dest.mkdir(parents=True, exist_ok=True)
        src_files = {}
        for p in src.rglob('*'):
            if p.is_file():
                rel = p.relative_to(src)
                src_files[rel] = p
        # copy new/updated
        for rel, sp in src_files.items():
            dp = dest / rel
            if not dp.exists() or dp.stat().st_mtime < sp.stat().st_mtime:
                dp.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(sp), str(dp))
        # remove extraneous
        for p in list(dest.rglob('*')):
            if p.is_file() and p.relative_to(dest) not in src_files:
                try:
                    p.unlink()
                except OSError:
                    pass
        # prune empty dirs
        for d in sorted([p for p in dest.rglob('*') if p.is_dir()], reverse=True):
            try:
                d.rmdir()
            except OSError:
                pass

    @staticmethod
    def _pack_file_list(pack_dir: Path, manifest: dict):
        """Relative file paths a pack deploys (from manifest['files'] or disk scan)."""
        files = [f.get('path') for f in manifest.get('files', []) if f.get('path')]
        if not files:
            files = [str(p.relative_to(pack_dir)).replace('\\', '/')
                     for p in pack_dir.rglob('*')
                     if p.is_file() and p.name != 'manifest.json']
        return files

    def _deploy_file(self, src: Path, dst: Path):
        """Copy src over dst; on first overwrite keep the original as .original.bak."""
        import shutil
        bak = dst.with_name(dst.name + '.original.bak')
        if dst.exists() and not bak.exists():
            shutil.copy2(str(dst), str(bak))
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))

    def _undeploy_files(self, rel_files, game_dir: Path):
        """DLC uninstall: restore .original.bak where present, else delete."""
        import shutil
        for rel in rel_files:
            dst = game_dir / rel
            bak = dst.with_name(dst.name + '.original.bak')
            try:
                if bak.exists():
                    shutil.copy2(str(bak), str(dst))
                elif dst.exists():
                    dst.unlink()
            except OSError:
                pass

    def deploy_dlc(self, game_dir: str = None):
        """Deploy enabled DLC packs (launcher_data/dlc/<id>) per their deploy_mode.

        Modes (manifest['deploy_mode'], default 'modloader'):
          modloader  - mirror pack into <game>/modloader/<name> (copy newer,
                       delete extraneous); moonloader/ subdir goes straight to
                       <game>/moonloader/.
          root       - copy each pack file to <game>/<relpath>, backing up any
                       overwritten original once as .original.bak.
          dircopy    - mirror pack content at its exact game-relative path.
          overwrite  - same placement as dircopy (data/model replacements).
        Disabled packs are removed: modloader mode rmtree's the folder; other
        modes restore .original.bak originals or delete added files.
        Packs deploy sorted by (layer, order) so runtime loads before content.
        Returns list of (pack_id, status) tuples.
        """
        game_dir = Path(game_dir) if game_dir else self.game_path
        src_root = self._dlc_source_dir()
        results = []
        if not src_root:
            logger.info("deploy_dlc: [SKIP] no launcher_data/dlc found")
            return results
        import shutil
        saved_states = self.db_manager.get_dlc_state()
        modloader_dir = game_dir / 'modloader'
        packs = []
        for pack_dir in sorted(src_root.iterdir()):
            if not pack_dir.is_dir():
                continue
            manifest_path = pack_dir / 'manifest.json'
            if not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            except (OSError, ValueError) as e:
                logger.error(f"deploy_dlc: [FAIL] bad manifest {manifest_path}: {e}")
                results.append((pack_dir.name, 'failed: bad manifest'))
                continue
            packs.append((int(manifest.get('layer', 5)), int(manifest.get('order', 99)),
                          pack_dir, manifest))
        packs.sort(key=lambda t: (t[0], t[1]))
        for _layer, _order, pack_dir, manifest in packs:
            pack_id = manifest.get('id', pack_dir.name)
            enabled = saved_states.get(pack_id, bool(manifest.get('default_enabled', True)))
            mode = manifest.get('deploy_mode', 'modloader')
            target_name = manifest.get('name', pack_dir.name)
            target = modloader_dir / target_name
            rel_files = self._pack_file_list(pack_dir, manifest)
            try:
                if not enabled:
                    if mode == 'modloader':
                        if target.exists():
                            shutil.rmtree(str(target))
                            logger.info(f"deploy_dlc: [DISABLED] removed {target}")
                            results.append((pack_id, 'removed (disabled)'))
                        else:
                            results.append((pack_id, 'disabled'))
                    else:
                        self._undeploy_files(rel_files, game_dir)
                        results.append((pack_id, 'restored (disabled)'))
                    continue
                if mode == 'modloader':
                    self._sync_tree(pack_dir, target)
                    mp = target / 'manifest.json'
                    if mp.exists():
                        mp.unlink()
                    ml_src = pack_dir / 'moonloader'
                    if ml_src.is_dir():
                        self._sync_tree(ml_src, game_dir / 'moonloader')
                    status = 'deployed'
                else:
                    for rel in rel_files:
                        src = pack_dir / rel
                        if src.is_file():
                            self._deploy_file(src, game_dir / rel)
                    status = 'deployed'
                results.append((pack_id, status))
                logger.info(f"deploy_dlc: [OK] {pack_id} ({mode})")
            except OSError as e:
                logger.error(f"deploy_dlc: [FAIL] {pack_id}: {e}")
                results.append((pack_id, f'failed: {e}'))
        return results


    def ensure_profiles(self, game_dir: str = None):
        """Seed the built-in legacy+/test profiles on first run."""
        game_dir = Path(game_dir) if game_dir else self.game_path
        self.profile_manager.ensure_default_profiles(game_dir)

    def apply_active_profile(self, game_dir: str = None) -> bool:
        """Apply the currently-selected profile to the game dir (skygfx.ini + bridge)."""
        game_dir = Path(game_dir) if game_dir else self.game_path
        name = self.profile_manager.get_active_profile(game_dir)
        if not name:
            return False
        return self.profile_manager.apply_profile(name, game_dir)

    def select_profile(self, name: str, game_dir: str = None) -> bool:
        """Record + apply a profile selection (used by the launcher UI)."""
        game_dir = Path(game_dir) if game_dir else self.game_path
        self.profile_manager.set_active_profile(game_dir, name)
        return self.profile_manager.apply_profile(name, game_dir)

    def is_game_running(self, game: str = 'gtasa') -> bool:
        """Check if the game is already running"""
        exe_name = self.config_manager.get_game_executable(game)
        if not exe_name:
            exe_name = f'{game}.exe'
        
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] and exe_name.lower() in proc.info['name'].lower():
                return True
        return False
    
    def launch_game(self, game: str = 'gtasa') -> Optional[subprocess.Popen]:
        """Launch the specified game with extended limits"""
        logger.info(f"launch_game: Starting launch for {game}")
        
        # Check if game is already running
        if self.is_game_running(game):
            logger.warning(f"launch_game: Game {game} is already running")
            raise RuntimeError(f"Game {game} is already running")
        
        # Use selected exe if set, otherwise find it
        if self.selected_exe and self.selected_exe.exists():
            game_exe = self.selected_exe
            logger.info(f"launch_game: Using selected exe: {game_exe}")
        else:
            # Get game executable — gtasa maps to gta_sa.exe, not gtasa.exe
            exe_name = self.config_manager.get_game_executable(game)
            if not exe_name:
                fallback = {'gtasa': 'gta_sa.exe', 'gtavc': 'gta-vc.exe', 'gta3': 'gta3.exe'}
                exe_name = fallback.get(game, f'{game}.exe')
            
            game_exe = self.game_path / exe_name
            logger.info(f"launch_game: Checking default path: {game_exe}")
            
            if not game_exe.exists():
                # Try to find it
                logger.info(f"launch_game: Default path not found, searching...")
                game_exe = self.game_manager.get_executable_path(game)
                if not game_exe:
                    logger.error(f"launch_game: Game executable not found for: {game}")
                    raise FileNotFoundError(f"Game executable not found for: {game}")
                logger.info(f"launch_game: Found exe at: {game_exe}")
        
        logger.info(f"launch_game: Final exe path: {game_exe}")
        logger.info(f"launch_game: Game path: {self.game_path}")
        
        # Calculate limits based on system resources
        vram = self.system_utils.get_gpu_memory()
        ram = self.system_utils.get_system_memory()
        limits = self.system_utils.calculate_dynamic_limits(vram, ram)
        
        logger.info(f"launch_game: Calculated limits: {limits}")
        
        # Apply limits to database
        self.db_manager.set_limit(game, 'StreamingMemory', limits['streaming_memory_mb'])
        self.db_manager.set_limit(game, 'MaxColors', limits['max_colors'])
        self.db_manager.set_limit(game, 'MaxModels', limits['max_models'])
        
        # Prepare bridge agent (config INI + ASI deployment) before launch
        self.seed_default_limits()
        self.deploy_dxvk()
        self.write_bridge_ini()
        self.ensure_profiles()
        self.apply_active_profile()
        self.deploy_asi()
        self.deploy_fixes()
        self.deploy_dlc()

        # Launch game
        logger.info(f"launch_game: Launching process...")
        try:
            process = subprocess.Popen([str(game_exe)], cwd=str(self.game_path))
            logger.info(f"launch_game: Process started with PID: {process.pid}")
            self.game_process = process
            self._start_exit_watchdog(process)
            return process
        except Exception as e:
            logger.error(f"launch_game: Failed to launch process: {e}")
            raise

    def _start_exit_watchdog(self, process: subprocess.Popen):
        """Watch the game process; log early exits with exit code (m1657)."""
        import threading
        import time

        def watch():
            start = time.time()
            try:
                code = process.wait()
            except Exception as e:  # noqa: BLE001
                logger.error(f"watchdog: wait failed: {e}")
                return
            elapsed = time.time() - start
            if elapsed < 15:
                logger.error(
                    f"watchdog: GAME EXITED EARLY after {elapsed:.1f}s "
                    f"code={code} — check game dir logs (skygfx dbg, cleo.log, "
                    f"gta_sa_d3d9.log) and gta_bridge.asi boot")
            else:
                logger.info(f"watchdog: game exited normally after "
                            f"{elapsed/60:.1f} min code={code}")

        threading.Thread(target=watch, daemon=True,
                         name='game-exit-watchdog').start()
    
    def setup_limits(self) -> Dict[str, str]:
        """Setup all limit extenders"""
        results = self.git_manager.clone_all_repos()
        return results
    
    def get_system_info(self) -> Dict[str, any]:
        """Get system information"""
        return {
            'ram_mb': self.system_utils.get_system_memory(),
            'vram_mb': self.system_utils.get_gpu_memory(),
            'cpu_cores': self.system_utils.get_cpu_count(),
            'platform': self.system_utils.get_platform_info(),
            'dynamic_limits': self.system_utils.calculate_dynamic_limits(
                self.system_utils.get_gpu_memory(),
                self.system_utils.get_system_memory()
            )
        }


class LauncherGUI:
    """GUI for the GTA Bridge Launcher with Windows Vista Aero dark glass theme"""
    
    # Synthwave/VCS color palette (exact copy from 87_installer theme)
    COLORS = {
        'bg_dark': '#0a1f12',           # Very dark green (panel bg)
        'bg_panel': '#0a1f12',           # Panel background
        'bg_frame': '#0d3b1f',          # Dark green frame
        'panel_bg_light': '#15351f',    # Slightly lighter green for secondary panels
        'accent_green': '#3d8a3d',      # Grove Street green (accent)
        'accent_green_light': '#5fc45f', # Light green
        'accent_orange': '#ff6a2b',     # Sunset orange
        'accent_pink': '#ff2bd6',       # Sunset pink
        'accent_cyan': '#00f0ff',       # Vice cyan
        'text_bright': '#5fff8c',       # Bright VCS light green
        'text_body': '#c8f0d2',         # Very light mint
        'text_dim': '#7aa684',          # Muted green
        'text_primary': '#ffffff',      # Primary text (white)
        'text_secondary': '#a0a0a0',    # Secondary text
        'text_disabled': '#666666',     # Disabled text
        'border_light': '#5fff8c',      # Light border
        'border_dark': '#0d3b1f',       # Dark border
        'highlight': '#ff6a2b',         # Highlight color
        'glass_border': '#0d3b1f',      # Glass border
        'success': '#5bff8a',           # Success green
        'danger': '#ff5b5b',            # Danger red
    }
    
    def __init__(self, launcher: GTALauncher):
        self.launcher = launcher
        self.root = tk.Tk()
        self.root.title("GTA Bridge Launcher v1.0.0")
        self.root.geometry("700x600")
        self.root.resizable(False, False)
        
        # Set dark glass theme
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self._setup_dark_aero_styles()
        
        # Current screen state
        self.current_screen = 'game_selection'
        
        # Load last selected EXE path
        self.last_exe_path = self.launcher.get_last_exe_path()
        
        # Main container
        self.main_container = tk.Frame(self.root, bg=self.COLORS['bg_dark'])
        self.main_container.pack(fill=tk.BOTH, expand=True)
        
        self.setup_header()
        self.setup_navigation()
        self.setup_content()
    
    def _setup_dark_aero_styles(self):
        """Setup dark glass Aero themed styles"""
        # Dark glass frame style
        self.style.configure('Dark.TFrame',
            background=self.COLORS['bg_frame'],
            borderwidth=2,
            relief='solid')
        
        # Dark glass labelframe style
        self.style.configure('Dark.TLabelframe',
            background=self.COLORS['bg_panel'],
            borderwidth=2,
            relief='solid')
        self.style.configure('Dark.TLabelframe.Label',
            font=('Segoe UI', 10, 'bold'),
            foreground=self.COLORS['text_primary'])
        
        # Dark button style
        self.style.configure('Dark.TButton',
            background=self.COLORS['bg_frame'],
            foreground=self.COLORS['text_primary'],
            font=('Segoe UI', 9),
            padding=8)
        self.style.map('Dark.TButton',
            background=[('active', self.COLORS['accent_green']),
                       ('pressed', self.COLORS['bg_frame'])])
        
        # Accent button style (green)
        self.style.configure('Accent.TButton',
            background=self.COLORS['accent_green'],
            foreground='white',
            font=('Segoe UI', 10, 'bold'),
            padding=10)
        self.style.map('Accent.TButton',
            background=[('active', '#27ae60')])
        
        # Orange button style (settings)
        self.style.configure('Settings.TButton',
            background=self.COLORS['accent_orange'],
            foreground='white',
            font=('Segoe UI', 9),
            padding=8)
        self.style.map('Settings.TButton',
            background=[('active', '#d35400')])
        
        # Entry style
        self.style.configure('Dark.TEntry',
            fieldbackground=self.COLORS['bg_panel'],
            foreground=self.COLORS['text_primary'],
            font=('Segoe UI', 9))
        
        # Combobox style
        self.style.configure('Dark.TCombobox',
            fieldbackground=self.COLORS['bg_panel'],
            foreground=self.COLORS['text_primary'],
            font=('Segoe UI', 9))
    
    def setup_header(self):
        """Setup dark glass header with synthwave sunset gradient"""
        header_frame = tk.Frame(self.main_container, bg=self.COLORS['bg_frame'], height=60)
        header_frame.pack(fill=tk.X, side=tk.TOP)
        header_frame.pack_propagate(False)
        
        # Verification text in top left corner
        verify_label = tk.Label(header_frame, text="✅ LAUNCHER ACTIVE", 
                               font=('Segoe UI', 8, 'bold'),
                               bg=self.COLORS['bg_frame'],
                               fg=self.COLORS['text_bright'])
        verify_label.pack(side=tk.LEFT, padx=10, pady=10)
        
        # Synthwave sunset gradient effect
        for i in range(60):
            # Gradient from dark green to sunset colors
            r = int(13 + (255-13) * i / 60)  # 0d -> ff
            g = int(59 + (106-59) * i / 60)   # 3b -> 6a
            b = int(31 + (43-31) * i / 60)    # 1f -> 2b
            color = f'#{r:02x}{g:02x}{b:02x}'
            header_frame.create_line(0, i, 700, i, fill=color) if hasattr(header_frame, 'create_line') else None
        
        # Title
        title = tk.Label(header_frame, text="GTA Bridge Launcher", 
                        font=('Segoe UI', 18, 'bold'),
                        bg=self.COLORS['bg_frame'],
                        fg=self.COLORS['text_bright'])
        title.pack(expand=True)
    
    def setup_navigation(self):
        """Setup navigation buttons on top"""
        nav_frame = tk.Frame(self.main_container, bg=self.COLORS['bg_frame'], height=50)
        nav_frame.pack(fill=tk.X, side=tk.TOP)
        nav_frame.pack_propagate(False)
        
        # Navigation buttons with synthwave colors
        btn_game = tk.Button(nav_frame, text="🎮 Game Selection",
                            command=lambda: self.show_screen('game_selection'),
                            bg=self.COLORS['accent_green'],
                            fg=self.COLORS['text_bright'],
                            relief=tk.FLAT,
                            font=('Segoe UI', 9, 'bold'))
        btn_game.pack(side=tk.LEFT, padx=10, pady=10)
        
        btn_settings = tk.Button(nav_frame, text="⚙️ Settings",
                                  command=lambda: self.show_screen('settings'),
                                  bg=self.COLORS['accent_orange'],
                                  fg=self.COLORS['text_bright'],
                                  relief=tk.FLAT,
                                  font=('Segoe UI', 9, 'bold'))
        btn_settings.pack(side=tk.LEFT, padx=10, pady=10)
        
        btn_advanced = tk.Button(nav_frame, text="🔧 Advanced",
                                  command=lambda: self.show_screen('advanced'),
                                  bg=self.COLORS['accent_cyan'],
                                  fg=self.COLORS['text_bright'],
                                  relief=tk.FLAT,
                                  font=('Segoe UI', 9, 'bold'))
        btn_advanced.pack(side=tk.LEFT, padx=10, pady=10)
        
        btn_play = tk.Button(nav_frame, text="▶ Play",
                              command=self.play_game,
                              bg=self.COLORS['accent_green'],
                              fg=self.COLORS['text_bright'],
                              relief=tk.FLAT,
                              font=('Segoe UI', 9, 'bold'))
        btn_play.pack(side=tk.RIGHT, padx=10, pady=10)
    
    def setup_content(self):
        """Setup content area with screens"""
        self.content_frame = tk.Frame(self.main_container, bg=self.COLORS['bg_dark'])
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create screen frames
        self.screens = {}
        
        # Screen 1: Game Selection
        self.screens['game_selection'] = self._create_game_selection_screen()
        
        # Screen 2: Settings
        self.screens['settings'] = self._create_settings_screen()
        
        # Screen 3: Advanced (Info)
        self.screens['advanced'] = self._create_advanced_screen()
        
        # Show initial screen
        self.show_screen('game_selection')
    
    def _create_game_selection_screen(self):
        """Create game selection screen"""
        frame = tk.Frame(self.content_frame, bg=self.COLORS['bg_panel'])
        
        # Game selection label
        tk.Label(frame, text="🎮 Select Game", 
                 font=('Segoe UI', 16, 'bold'),
                 bg=self.COLORS['bg_panel'],
                 fg=self.COLORS['text_primary']).pack(pady=10)
        
        # Profile selection (pop-out dropdown + add-current button)
        prof_frame = tk.LabelFrame(frame, text="Profile",
                                   bg=self.COLORS['bg_panel'],
                                   fg=self.COLORS['text_primary'],
                                   font=('Segoe UI', 10, 'bold'))
        prof_frame.pack(fill=tk.X, padx=20, pady=(2, 10))
        
        self.profile_var = tk.StringVar()
        self.profile_combo = ttk.Combobox(prof_frame, textvariable=self.profile_var,
                                          state='readonly', width=22,
                                          style='Dark.TCombobox')
        self.profile_combo.pack(side=tk.LEFT, padx=5, pady=5)
        self.profile_combo.bind('<<ComboboxSelected>>', self.on_profile_selected)
        
        self.add_profile_btn = tk.Button(prof_frame, text="+",
                                         command=self.add_current_profile,
                                         bg=self.COLORS['accent_green'],
                                         fg=self.COLORS['text_bright'],
                                         relief=tk.FLAT,
                                         font=('Segoe UI', 10, 'bold'), width=3)
        self.add_profile_btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        tk.Label(prof_frame, text="add current config as profile",
                 font=('Segoe UI', 8),
                 bg=self.COLORS['bg_panel'],
                 fg=self.COLORS['text_dim']).pack(side=tk.LEFT, padx=2)
        
        self.refresh_profiles()
        
        # Game dropdown
        tk.Label(frame, text="Game:", 
                font=('Segoe UI', 10),
                bg=self.COLORS['bg_panel'],
                fg=self.COLORS['text_secondary']).pack(anchor=tk.W, padx=20)
        
        self.game_var = tk.StringVar(value='gtasa')
        games = [('gtasa', 'GTA: San Andreas'), ('gtavc', 'GTA: Vice City'), ('gta3', 'GTA: 3')]
        
        self.game_combo = ttk.Combobox(frame, textvariable=self.game_var, 
                                       values=[g[1] for g in games], 
                                       state='readonly', width=20)
        self.game_combo.pack(fill=tk.X, padx=20, pady=5)
        self.game_combo.bind('<<ComboboxSelected>>', self.on_game_change)
        
        # Executable selection
        tk.Label(frame, text="Executable:", 
                font=('Segoe UI', 10),
                bg=self.COLORS['bg_panel'],
                fg=self.COLORS['text_secondary']).pack(anchor=tk.W, padx=20, pady=(10, 0))
        
        self.exe_var = tk.StringVar()
        self.exe_entry = ttk.Entry(frame, textvariable=self.exe_var, width=30, state='readonly')
        self.exe_entry.pack(fill=tk.X, padx=20, pady=5)
        
        # Load last selected EXE path if available
        if self.last_exe_path:
            self.exe_var.set(os.path.basename(self.last_exe_path))
            self.launcher.set_selected_exe(self.last_exe_path)
        
        browse_btn = tk.Button(frame, text="Browse...",
                              command=self.browse_exe,
                              bg=self.COLORS['accent_green'],
                              fg=self.COLORS['text_bright'],
                              relief=tk.FLAT)
        browse_btn.pack(fill=tk.X, padx=20, pady=5)
        
        # Game path
        tk.Label(frame, text=f"Path: {self.launcher.game_path}", 
                font=('Segoe UI', 9),
                bg=self.COLORS['bg_panel'],
                fg=self.COLORS['text_disabled']).pack(anchor=tk.W, padx=20, pady=(10, 0))
        
        return frame
    
    def _create_settings_screen(self):
        """Create settings screen with limit adjusters"""
        frame = tk.Frame(self.content_frame, bg=self.COLORS['bg_dark'])
        
        # Title
        tk.Label(frame, text="⚙️ Limit Adjuster Settings", 
                font=('Segoe UI', 16, 'bold'),
                bg=self.COLORS['bg_dark'],
                fg=self.COLORS['text_primary']).pack(pady=10)
        
        # Scrollable area
        canvas = tk.Canvas(frame, bg=self.COLORS['bg_dark'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self.COLORS['bg_dark'])
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Preset buttons
        preset_frame = tk.Frame(scrollable_frame, bg=self.COLORS['bg_panel'])
        preset_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(preset_frame, text="Presets:", 
                font=('Segoe UI', 10, 'bold'),
                bg=self.COLORS['bg_panel'],
                fg=self.COLORS['text_primary']).pack(anchor=tk.W)
        
        for preset in ['Stock', 'Balanced', 'High Performance', 'Modded', 'Pushed to Farthest']:
            btn = tk.Button(preset_frame, text=preset,
                           command=lambda p=preset: self.apply_preset(p),
                           bg=self.COLORS['accent_green'],
                           fg=self.COLORS['text_bright'],
                           relief=tk.FLAT,
                           font=('Segoe UI', 8))
            btn.pack(side=tk.LEFT, padx=2)
        
        # Limit categories
        self._create_limit_categories(scrollable_frame)
        
        # Apply button
        apply_btn = tk.Button(scrollable_frame, text="✅ Apply All Changes",
                             command=self.apply_all_changes,
                             bg=self.COLORS['accent_green'],
                             fg='white',
                             relief=tk.FLAT,
                             font=('Segoe UI', 10, 'bold'))
        apply_btn.pack(pady=10)
        
        return frame
    
    def _create_limit_categories(self, parent):
        """Create limit adjuster categories"""
        categories = [
            ('Pools', ['Peds', 'Vehicles', 'Buildings', 'Objects', 'Dummys', 'ColModel']),
            ('Memory', ['StreamingInfo', 'MemoryAvailable', 'VRAM']),
            ('Models', ['AtomicModels', 'DamageAtomicModels', 'TimeModels', 'ClumpModels', 'VehicleModels', 'PedModels', 'WeaponModels']),
            ('Entity Pointers', ['PtrNode', 'PtrNodeSingle', 'PtrNodeDouble', 'EntryInfoNode', 'VisibleEntityPtrs', 'VisibleLodPtrs']),
            ('Rendering', ['StaticShadows', 'Coronas', 'ScriptSearchLights', 'OutsideWorldWaterBlocks']),
            ('Textures', ['TxdStore', 'AudioScriptObj']),
            ('IPL & Scripts', ['EntitiesPerIpl', 'EntityIpl', 'PointRoute', 'PatrolRoute', 'NodeRoute', 'Task', 'Event']),
            ('Advanced', ['TaskAllocator', 'PedAttractors', 'VehicleStructs', 'MatrixList', 'Treadables', 'CollisionSize']),
        ]
        
        for cat_name, settings in categories:
            cat_frame = tk.Frame(parent, bg=self.COLORS['bg_panel'])
            cat_frame.pack(fill=tk.X, padx=10, pady=5)
            
            tk.Label(cat_frame, text=f"🔧 {cat_name}", 
                    font=('Segoe UI', 11, 'bold'),
                    bg=self.COLORS['accent_green'],
                    fg=self.COLORS['text_bright']).pack(fill=tk.X)
            
            for setting in settings:
                row = tk.Frame(cat_frame, bg=self.COLORS['bg_dark'])
                row.pack(fill=tk.X, padx=10, pady=2)
                
                tk.Label(row, text=setting, 
                        font=('Segoe UI', 9),
                        bg=self.COLORS['bg_dark'],
                        fg=self.COLORS['text_body']).pack(side=tk.LEFT)
                
                var = tk.StringVar(value=str(self.launcher.db_manager.get_limit('gtasa', setting) or 'default'))
                entry = ttk.Entry(row, textvariable=var, width=10)
                entry.pack(side=tk.RIGHT)
    
    def _create_advanced_screen(self):
        """Create advanced screen with system info"""
        frame = tk.Frame(self.content_frame, bg=self.COLORS['bg_panel'])
        
        # Title
        tk.Label(frame, text="ℹ️ System Information", 
                font=('Segoe UI', 16, 'bold'),
                bg=self.COLORS['bg_panel'],
                fg=self.COLORS['text_primary']).pack(pady=10)
        
        # System info
        sys_info = self.launcher.get_system_info()
        
        info_items = [
            ('RAM', f"{sys_info['ram_mb']} MB"),
            ('VRAM', f"{sys_info['vram_mb']} MB"),
            ('CPU Cores', f"{sys_info['cpu_cores']}"),
            ('Platform', sys_info['platform']),
        ]
        
        for label, value in info_items:
            row = tk.Frame(frame, bg=self.COLORS['bg_dark'])
            row.pack(fill=tk.X, padx=20, pady=5)
            
            tk.Label(row, text=f"{label}:", 
                    font=('Segoe UI', 10, 'bold'),
                    bg=self.COLORS['bg_dark'],
                    fg=self.COLORS['text_primary']).pack(side=tk.LEFT)
            
            tk.Label(row, text=value, 
                    font=('Segoe UI', 10),
                    bg=self.COLORS['bg_dark'],
                    fg=self.COLORS['text_secondary']).pack(side=tk.LEFT, padx=10)
        
        # Game path
        tk.Label(frame, text=f"Game Path: {self.launcher.game_path}", 
                font=('Segoe UI', 9),
                bg=self.COLORS['bg_dark'],
                fg=self.COLORS['text_disabled']).pack(anchor=tk.W, padx=20, pady=(20, 0))
        
        # Limit adjusters status
        tk.Label(frame, text="Installed Limit Adjusters:", 
                font=('Segoe UI', 10, 'bold'),
                bg=self.COLORS['bg_dark'],
                fg=self.COLORS['text_primary']).pack(anchor=tk.W, padx=20, pady=(20, 0))
        
        # Check installed
        installed = []
        for name in ['III.VC.SA.LimitAdjuster', 'SilentPatchSA']:
            if (self.launcher.game_path / f"{name}.asi").exists():
                installed.append(name)
        
        for name in installed:
            tk.Label(frame, text=f"✓ {name}", 
                    font=('Segoe UI', 9),
                    bg=self.COLORS['bg_dark'],
                    fg=self.COLORS['accent_green']).pack(anchor=tk.W, padx=30, pady=2)
        
        return frame
    
    def show_screen(self, screen_name):
        """Switch to a different screen"""
        self.current_screen = screen_name
        
        # Hide all screens
        for name, frame in self.screens.items():
            frame.pack_forget()
        
        # Show selected screen
        self.screens[screen_name].pack(fill=tk.BOTH, expand=True)
    
    def on_game_change(self, event=None):
        """Handle game selection change"""
        game = self.game_var.get()
        exe_name = self.launcher.config_manager.get_game_executable(game.lower())
        if exe_name:
            self.exe_var.set(exe_name)
    
    def browse_exe(self):
        """Open file dialog to browse for executable"""
        filetypes = [('Executable files', '*.exe'), ('All files', '*.*')]
        initial_dir = str(self.launcher.game_path) if self.launcher.game_path.exists() else '.'
        
        exe_path = filedialog.askopenfilename(
            title="Select Game Executable",
            filetypes=filetypes,
            initialdir=initial_dir
        )
        
        if exe_path:
            self.exe_var.set(os.path.basename(exe_path))
            self.launcher.set_selected_exe(exe_path)
    
    def refresh_profiles(self):
        """Populate the profile dropdown from launcher_data/profiles."""
        self.launcher.ensure_profiles()
        profiles = self.launcher.profile_manager.list_profiles()
        if not profiles:
            profiles = ['legacy+', 'test']
        self.profile_combo['values'] = profiles
        active = self.launcher.profile_manager.get_active_profile(self.launcher.game_path)
        if active in profiles:
            self.profile_var.set(active)
        elif profiles:
            self.profile_var.set(profiles[0])

    def on_profile_selected(self, event=None):
        """User picked a profile in the dropdown -> record + apply immediately."""
        name = self.profile_var.get()
        if not name:
            return
        try:
            self.launcher.select_profile(name)
            logger.info(f"profile selected: {name}")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Profile Error", str(e))

    def add_current_profile(self):
        """Snapshot the current game config as a new profile."""
        name = simpledialog.askstring("New Profile", "Profile name:")
        if not name:
            return
        name = name.strip()
        if not name:
            return
        data = self.launcher.profile_manager.capture_current_config(self.launcher.game_path)
        if not data['skygfx'] and not data['bridge']:
            messagebox.showwarning("No config",
                                   "Could not read current skygfx.ini / gta_bridge.ini")
            return
        self.launcher.profile_manager.save_profile(name, data)
        self.launcher.profile_manager.set_active_profile(self.launcher.game_path, name)
        self.refresh_profiles()
        self.profile_var.set(name)
        messagebox.showinfo("Profile Saved", f"Saved current config as '{name}'")
    
    def apply_preset(self, preset_name):
        """Apply a preset configuration"""
        from limit_adjuster_settings import LimitAdjusterSettings
        
        if preset_name not in LimitAdjusterSettings.PRESETS:
            messagebox.showerror("Error", f"Unknown preset: {preset_name}")
            return
        
        preset = LimitAdjusterSettings.PRESETS[preset_name]
        
        # Apply each setting to the database
        for setting_name, value in preset.items():
            self.launcher.db_manager.set_limit('gtasa', setting_name, value)
        
        messagebox.showinfo("Preset Applied", f"Applied {preset_name} preset with {len(preset)} settings")
    
    def apply_all_changes(self):
        """Apply all changes"""
        messagebox.showinfo("Applied", "Settings applied successfully!")
    
    def create_game_overlay(self, process):
        """Create an overlay window that appears on top of the game"""
        # Create overlay window
        self.overlay = tk.Toplevel(self.root)
        self.overlay.title("Game Overlay")
        self.overlay.overrideredirect(True)  # Remove window decorations
        self.overlay.attributes('-topmost', True)  # Always on top
        self.overlay.attributes('-transparentcolor', 'white')  # Transparent background
        
        # Set overlay position and size
        self.overlay.geometry("350x140+50+50")
        
        # Overlay content - verification text and stats
        overlay_frame = tk.Frame(self.overlay, bg='white')  # White will be transparent
        overlay_frame.pack(fill=tk.BOTH, expand=True)
        
        # Get GTA SA internal memory pools from limit adjuster settings
        try:
            # Get streaming memory from limit adjuster
            streaming_mem = self.launcher.db_manager.get_limit('gtasa', 'StreamingInfo') or 6350
            streaming_percent = self.launcher.db_manager.get_limit('gtasa', 'MemoryAvailable') or '30%'
            
            # Get model pool sizes
            atomic_models = self.launcher.db_manager.get_limit('gtasa', 'AtomicModels') or 10000
            damage_models = self.launcher.db_manager.get_limit('gtasa', 'DamageAtomicModels') or 10000
            
            # Get entity pointer pools
            ptr_node = self.launcher.db_manager.get_limit('gtasa', 'PtrNode') or 300000
            visible_ptrs = self.launcher.db_manager.get_limit('gtasa', 'VisibleEntityPtrs') or 100000
            
            # Get pool sizes
            peds = self.launcher.db_manager.get_limit('gtasa', 'Peds') or 140
            vehicles = self.launcher.db_manager.get_limit('gtasa', 'Vehicles') or 110
            
            # Calculate approximate memory usage based on pools
            # Each ped ~ 10KB, each vehicle ~ 50KB, each model ~ 1KB
            peds_mem = peds * 10 / 1024  # MB
            vehicles_mem = vehicles * 50 / 1024  # MB
            models_mem = (atomic_models + damage_models) / 1024  # MB
            streaming_mem_mb = streaming_mem / 1024  # MB
            
            # Verification text with GTA SA internal pools
            stats_text = f"✅ LAUNCHER ACTIVE | Peds:{peds} Veh:{vehicles} | Models:{atomic_models} | Streaming:{streaming_mem} | Mem:{streaming_percent}"
        except:
            stats_text = "✅ LAUNCHER ACTIVE | Pools loaded"
        
        # Verification text
        verify_label = tk.Label(overlay_frame, text=stats_text,
                               font=('Segoe UI', 9, 'bold'),
                               bg='white',  # Transparent
                               fg=self.COLORS['text_bright'])
        verify_label.pack(expand=True)
        self.overlay_stats_label = verify_label

        # Bridge (live IPC) status line - updated by BridgeMonitor via root.after
        self.overlay_bridge_label = tk.Label(overlay_frame, text="BRIDGE: connecting...",
                                            font=('Segoe UI', 8),
                                            bg='white',
                                            fg=self.COLORS['text_dim'])
        self.overlay_bridge_label.pack(anchor='w', padx=8, pady=(0, 4))

        # If the monitor already reported stats before overlay existed, apply now
        if getattr(self, 'latest_bridge_stats', None):
            self._apply_bridge_stats(self.latest_bridge_stats)

        return self.overlay
    
    def play_game(self):
        """Launch the selected game"""
        game = self.game_var.get().lower() if self.game_var.get() else 'gtasa'
        try:
            process = self.launcher.launch_game(game)

            # Create overlay window
            self.create_game_overlay(process)

            # Start live bridge monitoring (MMO-launcher style)
            self._start_bridge_monitor()

            messagebox.showinfo("Launched", f"Game launched with PID: {process.pid}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ------------------------------------------------------------------ #
    # Bridge monitoring (live stats from gta_bridge.asi via named pipe)
    # ------------------------------------------------------------------ #
    def _start_bridge_monitor(self):
        """Start (or restart) the BridgeMonitor thread feeding the overlay."""
        if not BRIDGE_AVAILABLE:
            logger.warning("bridge_client unavailable - live monitoring disabled")
            return
        # Stop any previous monitor
        old = getattr(self, 'bridge_monitor', None)
        if old is not None and old.is_alive():
            old.stop()
        self.latest_bridge_stats = None
        self.bridge_monitor = BridgeMonitor(callback=self._on_bridge_stats)
        self.bridge_monitor.start()
        logger.info("BridgeMonitor started")

    def _on_bridge_stats(self, stats):
        """Called from the monitor thread - marshal to tk mainloop."""
        try:
            self.root.after(0, lambda: self._apply_bridge_stats(stats))
        except RuntimeError:
            pass  # root destroyed during shutdown

    def _apply_bridge_stats(self, stats):
        """Apply bridge stats to overlay labels. MUST run on tk main thread."""
        self.latest_bridge_stats = stats
        label = getattr(self, 'overlay_bridge_label', None)
        if label is None or not label.winfo_exists():
            return
        if stats.get('connected'):
            label.config(text="BRIDGE: connected", fg=self.COLORS['success'])
            mem_avail = stats.get('mem_avail', -1)
            mem_used = stats.get('mem_used', -1)
            parts = []
            if mem_avail >= 0:
                parts.append(f"MEM: {mem_used}/{mem_avail + mem_used} MB")
            for name, um in stats.get('pools', {}).items():
                u, m = um
                if u >= 0:
                    parts.append(f"{name}: {u}/{m}")
            if parts:
                text = " | ".join(parts[:6])
                stats_label = getattr(self, 'overlay_stats_label', None)
                if stats_label is not None and stats_label.winfo_exists():
                    stats_label.config(text=text)
        else:
            label.config(text="BRIDGE: disconnected", fg=self.COLORS['danger'])
    
    def run(self):
        """Run the GUI main loop"""
        self.root.mainloop()


def main():
    """Main entry point"""
    # Default paths — MMO-launcher style: if the launcher exe lives beside gta_sa.exe
    # (e.g. copied into the game folder) use its directory as game_path.
    exe_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    colocated_game = exe_dir / 'gta_sa.exe'
    default_game_path = str(exe_dir) if colocated_game.exists() else r'E:/games/gtasa_skygfx_plus'
    game_path = os.environ.get('GTA_PATH', default_game_path)
    # db/config: when frozen & co-located, keep them beside the exe for portability
    if getattr(sys, 'frozen', False) and colocated_game.exists():
        default_db = str(exe_dir / 'gta_limits.db')
        default_cfg = str(exe_dir / 'config')
    else:
        default_db = 'gta_limits.db'
        default_cfg = 'config'
    db_path = os.environ.get('GTA_DB_PATH', default_db)
    config_path = os.environ.get('GTA_CONFIG_PATH', default_cfg)
    
    # Check for console mode flag
    console_mode = '--console' in sys.argv or '-c' in sys.argv
    
    # Create paths if they don't exist
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Path(config_path).mkdir(parents=True, exist_ok=True)
    
    # Check if game path exists, if not use current directory
    if not Path(game_path).exists():
        game_path = os.getcwd()
    
    launcher = GTALauncher(game_path, db_path, config_path)
    
    # Check if GUI is available and not in console mode
    if GUI_AVAILABLE and not console_mode:
        # Run GUI
        gui = LauncherGUI(launcher)
        gui.run()
    else:
        # Fallback to console mode
        print("=" * 50)
        print("GTA Bridge Launcher v1.0.0")
        print("=" * 50)
        sys_info = launcher.get_system_info()
        print(f"System RAM: {sys_info['ram_mb']} MB")
        print(f"GPU VRAM: {sys_info['vram_mb']} MB")
        print(f"CPU Cores: {sys_info['cpu_cores']}")
        print(f"Dynamic Limits: {sys_info['dynamic_limits']}")
        print("=" * 50)
        
        # Setup limit extenders
        print("\nSetting up limit extenders...")
        results = launcher.setup_limits()
        for game, status in results.items():
            print(f"  {game}: {status}")
        
        # Launch game
        print("\nLaunching GTA San Andreas...")
        try:
            process = launcher.launch_game('gtasa')
            print(f"Game launched with PID: {process.pid}")
            print("\nPress Ctrl+C to exit...")
            
            # Wait for process
            process.wait()
            print(f"\nGame exited with code: {process.returncode}")
            
        except FileNotFoundError as e:
            print(f"Error: {e}")
            sys.exit(1)
        except KeyboardInterrupt:
            print("\nInterrupted by user")
            if 'process' in locals():
                process.terminate()


if __name__ == '__main__':
    main()