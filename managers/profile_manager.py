"""
Profile Manager - performance / look profiles for the GTA Bridge Launcher.

Profiles live in launcher_data/profiles/<name>.json (frozen-aware, mirroring the
other _*_source_dir helpers). Each profile owns a curated set of SkyGfx.ini
[SkyGfx] keys (the look + perf levers) and gta_bridge.ini [BRIDGE] keys
(draw-distance / streaming). The active selection is recorded in
gta_bridge.ini [PROFILES] next to the asi so it is "selectable from the ini
file next to asi" and applied on launch.
"""
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

try:
    import configparser
except ImportError:  # pragma: no cover - stdlib always present on target
    configparser = None


class ProfileManager:
    # SkyGfx.ini [SkyGfx] keys owned by profiles (look + perf levers)
    SKYGFX_KEYS = [
        'pipeline', 'buildingPipe',
        'dualPassBuilding', 'dualPassDefault', 'dualPassGrass',
        'dualPassPed', 'dualPassVehicle',
        'godRaysEnable', 'godRaysNumSamples',
        'sssPostProcessEnable', 'pedShadows', 'stencilShadows',
        'enableNormalMaps',
    ]
    # gta_bridge.ini [BRIDGE] keys owned by profiles
    BRIDGE_KEYS = ['max_lod_scale', 'streaming_mem_mb', 'vegetation_boost']

    DEFAULT_ACTIVE = 'legacy+'

    def __init__(self, launcher_base: Path):
        self.base = Path(launcher_base)

    # ---- location (frozen-aware, mirrors other _*_source_dir helpers) ----
    def profiles_dir(self) -> Path:
        if getattr(sys, 'frozen', False):
            # Always use a writable location beside the exe (game folder);
            # _MEIPASS is read-only and cannot hold user-created profiles.
            cand = Path(sys.executable).parent / 'launcher_data' / 'profiles'
            try:
                cand.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
            return cand
        return self.base / 'launcher_data' / 'profiles'

    # ---- listing / load / save ----
    def list_profiles(self) -> List[str]:
        d = self.profiles_dir()
        if not d.is_dir():
            return []
        return sorted(p.stem for p in d.glob('*.json') if p.is_file())

    def load_profile(self, name: str) -> Optional[Dict]:
        p = self.profiles_dir() / f'{name}.json'
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None

    def save_profile(self, name: str, data: Dict) -> bool:
        d = self.profiles_dir()
        d.mkdir(parents=True, exist_ok=True)
        p = d / f'{name}.json'
        try:
            blob = dict(data)
            blob['name'] = name
            p.write_text(json.dumps(blob, indent=2), encoding='utf-8')
            return True
        except OSError:
            return False

    def delete_profile(self, name: str) -> bool:
        p = self.profiles_dir() / f'{name}.json'
        try:
            if p.exists():
                p.unlink()
                return True
        except OSError:
            pass
        return False

    # ---- active selection (gta_bridge.ini [PROFILES] next to asi) ----
    def get_active_profile(self, game_dir) -> str:
        game_dir = Path(game_dir)
        ini = game_dir / 'gta_bridge.ini'
        if configparser and ini.exists():
            cp = configparser.ConfigParser()
            cp.optionxform = str
            try:
                cp.read(ini, encoding='utf-8')
                if cp.has_section('PROFILES') and cp.has_option('PROFILES', 'active_profile'):
                    return cp.get('PROFILES', 'active_profile').strip() or self.DEFAULT_ACTIVE
            except configparser.Error:
                pass
        return self.DEFAULT_ACTIVE

    def set_active_profile(self, game_dir, name: str) -> None:
        game_dir = Path(game_dir)
        ini = game_dir / 'gta_bridge.ini'
        cp = configparser.ConfigParser()
        cp.optionxform = str
        if ini.exists():
            try:
                cp.read(ini, encoding='utf-8')
            except configparser.Error:
                pass
        if not cp.has_section('PROFILES'):
            cp.add_section('PROFILES')
        cp.set('PROFILES', 'active_profile', name)
        try:
            with open(ini, 'w', encoding='utf-8') as f:
                cp.write(f)
        except OSError:
            pass

    # ---- capture current game config (for "add current config as profile") ----
    def capture_current_config(self, game_dir) -> Dict:
        game_dir = Path(game_dir)
        skygfx: Dict[str, str] = {}
        sky = game_dir / 'skygfx.ini'
        if configparser and sky.exists():
            cp = configparser.ConfigParser()
            cp.optionxform = str
            try:
                cp.read(sky, encoding='utf-8')
                if cp.has_section('SkyGfx'):
                    for k in self.SKYGFX_KEYS:
                        if cp.has_option('SkyGfx', k):
                            skygfx[k] = cp.get('SkyGfx', k)
            except configparser.Error:
                pass
        bridge: Dict[str, str] = {}
        ini = game_dir / 'gta_bridge.ini'
        if configparser and ini.exists():
            cp = configparser.ConfigParser()
            cp.optionxform = str
            try:
                cp.read(ini, encoding='utf-8')
                if cp.has_section('BRIDGE'):
                    for k in self.BRIDGE_KEYS:
                        if cp.has_option('BRIDGE', k):
                            bridge[k] = cp.get('BRIDGE', k)
            except configparser.Error:
                pass
        return {'skygfx': skygfx, 'bridge': bridge}

    # ---- apply a profile's keys into the game dir ----
    def apply_profile(self, name: str, game_dir) -> bool:
        data = self.load_profile(name)
        if not data:
            return False
        game_dir = Path(game_dir)

        # SkyGfx.ini [SkyGfx] - update only owned keys, preserve everything else
        sky = game_dir / 'skygfx.ini'
        if sky.exists() and data.get('skygfx'):
            cp = configparser.ConfigParser()
            cp.optionxform = str
            try:
                cp.read(sky, encoding='utf-8')
            except configparser.Error:
                cp = configparser.ConfigParser()
                cp.optionxform = str
            if not cp.has_section('SkyGfx'):
                cp.add_section('SkyGfx')
            for k, v in data['skygfx'].items():
                cp.set('SkyGfx', k, str(v))
            try:
                with open(sky, 'w', encoding='utf-8') as f:
                    cp.write(f)
            except OSError:
                pass

        # gta_bridge.ini [BRIDGE] overrides (preserve [PROFILES])
        if data.get('bridge'):
            ini = game_dir / 'gta_bridge.ini'
            cp = configparser.ConfigParser()
            cp.optionxform = str
            if ini.exists():
                try:
                    cp.read(ini, encoding='utf-8')
                except configparser.Error:
                    cp = configparser.ConfigParser()
                    cp.optionxform = str
            if not cp.has_section('BRIDGE'):
                cp.add_section('BRIDGE')
            for k, v in data['bridge'].items():
                cp.set('BRIDGE', k, str(v))
            if not cp.has_section('PROFILES'):
                cp.add_section('PROFILES')
            if not cp.has_option('PROFILES', 'active_profile'):
                cp.set('PROFILES', 'active_profile', name)
            try:
                with open(ini, 'w', encoding='utf-8') as f:
                    cp.write(f)
            except OSError:
                pass
        return True

    # ---- encode a sweep result as a perf profile ----
    def encode_perf_profile(self, row: Dict) -> Optional[Path]:
        """Create a perf profile JSON from a sweep result row.

        *row* should contain keys ``sweep_id``, ``candidate_id``, ``rank``,
        and optionally ``overrides`` (dict).  Only keys in *BRIDGE_KEYS* are
        written into the profile's ``bridge`` section.
        """
        ov = {k: str(v) for k, v in (row.get('overrides') or {}).items()
              if k in self.BRIDGE_KEYS}
        if not ov:
            return None
        data = {
            'name': 'perf',
            'description': 'Perf profile from sweep %s/%s (rank %.2f)' % (
                row.get('sweep_id', '?'),
                row.get('candidate_id', '?'),
                float(row.get('rank', 0.0))),
            'skygfx': {},
            'bridge': ov,
            'notes': 'Encoded by encode_perf_profile; SkyGfx ini untouched. sweep_log:0 written into [BRIDGE] on winner encode.',
        }
        p = self.profiles_dir() / 'perf.json'
        p.write_text(json.dumps(data, indent=2), encoding='utf-8')
        return p

    # ---- seed the two built-in profiles on first run ----
    def ensure_default_profiles(self, game_dir) -> None:
        if 'legacy+' not in self.list_profiles():
            captured = self.capture_current_config(game_dir)
            if not captured['skygfx']:
                captured['skygfx'] = self._legacy_plus_skygfx()
            if not captured['bridge']:
                captured['bridge'] = self._legacy_plus_bridge()
            self.save_profile('legacy+', captured)
        if 'test' not in self.list_profiles():
            self.save_profile('test', {
                'skygfx': self._test_skygfx(),
                'bridge': self._test_bridge(),
            })

    # legacy+ = the current default full-glow look (fallback if game cfg absent)
    @staticmethod
    def _legacy_plus_skygfx() -> Dict[str, str]:
        return {
            'pipeline': 'PBR', 'buildingPipe': 'PBR',
            'dualPassBuilding': '1', 'dualPassDefault': '1', 'dualPassGrass': '1',
            'dualPassPed': '1', 'dualPassVehicle': '1',
            'godRaysEnable': '1', 'godRaysNumSamples': '20',
            'sssPostProcessEnable': '1', 'pedShadows': '1',
            'stencilShadows': '1', 'enableNormalMaps': '1',
        }

    @staticmethod
    def _legacy_plus_bridge() -> Dict[str, str]:
        return {'max_lod_scale': '4.0', 'streaming_mem_mb': '2048', 'vegetation_boost': '1'}

    # test = max settings: full glow + draw distance cranked to the 6.0 ceiling
    @staticmethod
    def _test_skygfx() -> Dict[str, str]:
        return {
            'pipeline': 'PBR', 'buildingPipe': 'PBR',
            'dualPassBuilding': '1', 'dualPassDefault': '1', 'dualPassGrass': '1',
            'dualPassPed': '1', 'dualPassVehicle': '1',
            'godRaysEnable': '1', 'godRaysNumSamples': '20',
            'sssPostProcessEnable': '1', 'pedShadows': '1',
            'stencilShadows': '1', 'enableNormalMaps': '1',
        }

    @staticmethod
    def _test_bridge() -> Dict[str, str]:
        return {'max_lod_scale': '6.0', 'streaming_mem_mb': '2048', 'vegetation_boost': '1'}
