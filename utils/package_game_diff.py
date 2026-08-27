#!/usr/bin/env python3
"""package_game_diff.py — scan game dir vs clean SA baseline and package the diff
into layered DLC packs under launcher_data/dlc/.

DLC format v2: manifest gains layer/order/deploy_mode so deployment lands each
file where it belongs (root ASIs, data overwrites w/ backup, model overrides,
dir copies) in deterministic order — faster and more precise than modloader's
rescan-everything approach.
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rw_inspect import inspect_any  # noqa: E402

GAME = Path('E:/games/gtasa_skygfx_plus')
CLEAN = Path('H:/games/clean_sa')
PROJECT = Path(__file__).resolve().parent.parent
DLC_OUT = PROJECT / 'launcher_data' / 'dlc'

# junk exclusions applied everywhere
JUNK = [
    '*.7z', '*.zip', '*.pdb', '*.lib', '*.exp', '*.map', '*.dmp', '*.log',
    '*.bak', '*.backup', '*_olf*', '*.asi_', '*.disabled', 'desktop.ini',
    'thumbs.db', 'main.cpp.backup', 'imgui.ini', 'gta_limits.db', 'gta_sa.set',
]
JUNK_DIRS = {
    'repos', 'temp', 'modloader_back', '_disabled', '_disabled_plugins',
    '_removed_plugins', '.lsai', '.mimocode', 'reference_build_20260630_2159',
    'presets', 'config', 'reshade-shaders',
}

def is_junk(rel: str) -> bool:
    low = rel.lower()
    if any(part in JUNK_DIRS for part in low.split('/')):
        return True
    from fnmatch import fnmatch
    name = low.rsplit('/', 1)[-1]
    return any(fnmatch(name, pat) for pat in JUNK)

# ---- pack definitions -------------------------------------------------------
# each rule: (pack_id, title, category, default_enabled, layer, order, deploy_mode, include_prefixes)
# deploy_mode: root=copy to game root | overwrite=data/model file replace w/ backup
#              | dircopy=mirror whole subtree to same path in game
PACKS = [
    ('runtime_redist', 'Runtime Redistributables (CLEO/ModLoader/MoonLoader)',
     'runtime', True, 0, 0, 'root',
     ['cleo.asi', 'modloader.asi', 'moonloader.asi', 'minhook.x86.dll', 'zlib1.dll']),
    ('cleo_scripts', 'CLEO Scripts', 'scripting', True, 0, 1, 'dircopy', ['cleo/']),
    ('moonloader_scripts', 'MoonLoader Scripts', 'scripting', True, 0, 2, 'dircopy',
     ['moonloader/gta_bridge_diag.lua']),  # only our diag script; lib/ runtime excluded
    ('skygfx_core', 'SkyGfx Core (ASI + configs)', 'graphics', True, 1, 0, 'root',
     ['skygfx.asi', 'skygfx.ini', 'skygfx_modern_pbr.ini', 'skygfx_current_backup.ini']),
    ('silentpatch', 'SilentPatch SA', 'fixes', True, 1, 1, 'root',
     ['silentpatchsa.asi', 'silentpatchsa.ini']),
    ('limit_adjuster', 'III.VC.SA.LimitAdjuster', 'limits', True, 1, 2, 'root',
     ['iii.vc.sa.limitadjuster.asi', 'iii.vc.sa.limitadjuster.ini']),
    ('neo_effects', 'NEO Effects (cartweaks + textures)', 'effects', True, 2, 0, 'dircopy',
     ['neo/']),
    ('grinch_trainer', 'GrinchTrainer SA (optional trainer)', 'tools', False, 2, 1, 'dircopy',
     ['grinchtrainersa/', 'grinchtrainersa.toml', 'modelextras/']),
    ('data_patches', 'Data Patches (colorcycle/weathers/seabed)', 'data', True, 3, 0, 'overwrite',
     ['data/colorcycle.dat', 'data/weathers2.dat', 'data/maps/leveldes/seabed.ipl']),
    ('hd_vehicle_textures', 'HD Vehicle Textures (vehicle.txd)', 'models', True, 4, 0, 'overwrite',
     ['models/generic/vehicle.txd']),
    ('particle_overhaul', 'Particle Overhaul (particle.txd)', 'models', True, 4, 1, 'overwrite',
     ['models/particle.txd']),
    ('model_extras', 'Model Extras (mobile details/buttons/beams/envmaps)', 'models', True, 4, 2,
     'overwrite',
     ['models/mobile_details.txd', 'models/ps3btns.txd', 'models/sixaxis.txd',
      'models/lightbeam1.png', 'models/lightbeam2.png', 'models/generic/vehicle/']),
]

def build_index(root: Path):
    out = {}
    for p in root.rglob('*'):
        if p.is_file():
            rel = str(p.relative_to(root)).replace('\\', '/')
            out[rel.lower()] = p
    return out

def rw_stats(path: Path):
    try:
        if path.suffix.lower() in ('.txd', '.dff', '.col'):
            return inspect_any(str(path))
    except Exception as e:
        return {'error': str(e)}
    return None

def main():
    game_idx = build_index(GAME)
    clean_idx = build_index(CLEAN)

    # changed set = added or size-differing vs clean
    changed = set(game_idx) - set(clean_idx)
    for rel, gp in game_idx.items():
        cp = clean_idx.get(rel)
        if cp and cp.stat().st_size != gp.stat().st_size:
            changed.add(rel)

    total_files = 0
    total_bytes = 0
    index_out = []
    for (pid, title, cat, default_on, layer, order, mode, prefixes) in PACKS:
        pack_dir = DLC_OUT / pid
        if pack_dir.exists():
            shutil.rmtree(pack_dir)
        files_meta = []
        nbytes = 0
        for rel in sorted(changed):
            if is_junk(rel):
                continue
            src = game_idx[rel]
            hit = False
            for pref in prefixes:
                p = pref.lower()
                if p.endswith('/'):
                    if rel.startswith(p):
                        hit = True
                        break
                elif rel == p:
                    hit = True
                    break
            if not hit:
                continue
            dst = pack_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            sz = src.stat().st_size
            nbytes += sz
            entry = {'path': rel, 'bytes': sz}
            st = rw_stats(src)
            if st:
                entry['rw'] = {k: st[k] for k in ('textures', 'geometries', 'triangles',
                                                  'vertices', 'entries') if k in st}
            files_meta.append(entry)
        if not files_meta:
            continue
        manifest = {
            'id': pid, 'name': title, 'version': '1.0.0',
            'description': f'{title} — packaged from gtasa_skygfx_plus diff vs clean SA',
            'category': cat, 'default_enabled': default_on,
            'dlc_format': 2, 'layer': layer, 'order': order, 'deploy_mode': mode,
            'file_count': len(files_meta), 'bytes': nbytes, 'files': files_meta,
        }
        (pack_dir / 'manifest.json').write_text(
            json.dumps(manifest, indent=2), encoding='utf-8')
        print(f"[PACK] {pid}: {len(files_meta)} files, {nbytes/1024/1024:.1f} MB "
              f"(layer {layer}, order {order}, {mode})")
        index_out.append({'id': pid, 'name': title, 'category': cat,
                          'default_enabled': default_on, 'layer': layer,
                          'order': order, 'deploy_mode': mode})
        total_files += len(files_meta)
        total_bytes += nbytes

    # refresh aggregate index (merge with existing packs like bridge_scripts/modloader ones)
    idx_path = DLC_OUT / 'index.json'
    existing = []
    if idx_path.exists():
        try:
            raw = json.loads(idx_path.read_text(encoding='utf-8'))
            if isinstance(raw, dict):
                raw = raw.get('packs', [])
            if isinstance(raw, list):
                existing = [e for e in raw if isinstance(e, dict) and 'id' in e]
        except Exception:
            existing = []
    by_id = {e['id']: e for e in existing}
    for e in index_out:
        by_id[e['id']] = e
    merged = sorted(by_id.values(), key=lambda e: (e.get('layer', 5), e.get('order', 99)))
    idx_path.write_text(json.dumps(merged, indent=2), encoding='utf-8')
    print(f"\nTOTAL packaged: {total_files} files, {total_bytes/1024/1024:.1f} MB "
          f"across {len(index_out)} new packs; index.json has {len(merged)} packs")

if __name__ == '__main__':
    main()
