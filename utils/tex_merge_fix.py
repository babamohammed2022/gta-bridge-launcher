"""Merge orphaned vehicle-detail textures into override copies of base TXDs.

Mechanism: ML loose TXDs override same-named gta3.img entries, so an
enriched copy streams through the model's existing IDE chain. Textures are
transplanted byte-verbatim (raw_payload, dirty=False) or aliased by header
rebuild only (dirty=True, mip bytes untouched) — NEVER re-encoded, so this
is safe for DXT3 (hard rule: never regenerate DXT3 mips).

Usage: venv64 python utils/tex_merge_fix.py [--apply]
  dry-run (default) prints the plan; --apply writes
  modloader/zz_vehtex_fix/<base>.txd (new files only, asserts no overwrite).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.path.dirname(_HERE)
sys.path.insert(0, _PROJECT)

from managers import mapdata, txdlite  # noqa: E402

GAME = r'E:\games\gtasa_skygfx_plus'
BACK = os.path.join(GAME, 'modloader_back', 'Proper Vehicles Retex',
                    '1 - cutscene.img', 'csbravura.txd')
FIXPACK = os.path.join(GAME, 'modloader', 'zz_vehtex_fix')

# texture -> (source_txd_path, alias_of_or_None)
# CS_BRAVA = shared vehicle-detail donor in the disabled Proper Vehicles pack
CS_BRAVA = os.path.join(GAME, 'modloader_back', 'Proper Vehicles Retex',
                        '1 - cutscene.img', 'csbravura.txd')
BANDITO_SRC = os.path.join(GAME, 'modloader_back', 'Proper Vehicles Retex',
                           '3 - veiculos', 'bandito.txd')
SOURCES = {
    'vehicledash32': (CS_BRAVA, None),
    'vehiclegeneric256': (CS_BRAVA, None),
    'vehiclegrunge256': (CS_BRAVA, None),
    'vehiclelights128': (CS_BRAVA, None),
    'vehiclesteering128': (CS_BRAVA, None),
    'vehicletyres128': (CS_BRAVA, None),
    'vehiclescratch64': (CS_BRAVA, 'vehiclegrunge256'),
    'vehicleshatter128': (CS_BRAVA, 'vehiclegrunge256'),
    'bandito92interior128': (BANDITO_SRC, None),
}

FIELDS = ("platform", "filter_addressing", "name", "mask", "raster_format",
          "d3d_format", "width", "height", "depth", "num_levels", "rtype",
          "flags", "palette", "mips", "raw_payload", "dirty")


def clone_tex(src_tex, new_name=None):
    t = txdlite.TxdTexture()
    for f in FIELDS:
        setattr(t, f, getattr(src_tex, f))
    if new_name and new_name != t.name:
        t.name = new_name
        t.dirty = True  # header rebuild only; mip bytes preserved
    return t


def base_txd_bytes(name):
    entries = {n: (o, s) for n, o, s in
               mapdata.read_img_entries(os.path.join(GAME, 'models', 'gta3.img'))}
    if name not in entries:
        return None
    off, size = entries[name]
    with open(os.path.join(GAME, 'models', 'gta3.img'), 'rb') as fh:
        fh.seek(off)
        return fh.read(size)


def main():
    apply = '--apply' in sys.argv
    from managers import mapdata as md
    rep = md.audit_mod_textures(GAME)
    # DFF stem -> needed missing vehicle-detail textures, resolved to the
    # IDE-linked TXD (veh_mods tuning parts link to the CAR's txd, e.g.
    # exh_a_l -> elegy) via the vanilla manifest, not the DFF stem.
    import sqlite3
    con = sqlite3.connect(os.path.join(_PROJECT, 'database', 'vanilla_sa.db'))
    def ide_txd(model):
        rows = con.execute('SELECT txd FROM ide_models WHERE model=?',
                           (model,)).fetchall()
        return (rows[0][0] + '.txd') if rows else (model + '.txd')
    need = {}
    for tex in SOURCES:
        for d in rep['unresolved'].get(tex, []):
            stem = os.path.splitext(os.path.basename(d))[0].lower()
            need.setdefault(ide_txd(stem), set()).add(tex)
    con.close()
    print('target base TXDs:', len(need))
    # load sources once
    src_txds = {}
    for tex, (spath, _alias) in SOURCES.items():
        if spath not in src_txds:
            src_txds[spath] = txdlite.TxdFile.load(spath)
    by_name = {}
    for _sp, tf in src_txds.items():
        for x in tf.textures:
            by_name.setdefault(str(getattr(x, 'name', '')).lower(), x)
    # alias sources must exist
    for tex, (_sp, alias) in SOURCES.items():
        if alias and alias not in by_name:
            print('FATAL: alias source missing:', alias)
            return 1
    if not apply:
        for txd in sorted(need):
            print(' ', txd, sorted(need[txd]))
        print('dry-run only; re-run with --apply')
        return 0
    os.makedirs(FIXPACK, exist_ok=True)
    done, skipped = [], []
    for txd_name in sorted(need):
        out = os.path.join(FIXPACK, txd_name)
        if os.path.exists(out):
            skipped.append((txd_name, 'exists'))
            continue
        buf = base_txd_bytes(txd_name)
        if buf is None:
            skipped.append((txd_name, 'no base in gta3.img'))
            continue
        try:
            base = txdlite.TxdFile.loads(buf)
        except Exception as e:
            skipped.append((txd_name, 'parse: %s' % e))
            continue
        have = {str(getattr(x, 'name', '')).lower() for x in base.textures}
        added = 0
        for tex in sorted(need[txd_name]):
            if tex in have:
                continue
            _sp, alias = SOURCES[tex]
            donor = by_name[alias or tex]
            base.textures.append(clone_tex(donor, tex))
            added += 1
        if not added:
            skipped.append((txd_name, 'nothing to add'))
            continue
        base.save(out)
        # verify: every NEEDED texture present by name + merged ones mip-clean
        # (pre-existing base textures may have strict quirks — not our problem)
        chk = txdlite.TxdFile.load(out)
        names = {str(getattr(x, 'name', '')).lower(): x for x in chk.textures}
        bad = [t for t in need[txd_name] if t not in names]
        bad += [t for t in need[txd_name]
                if t in names and any(txdlite.mip_issues(names[t], strict=True))]
        if bad:
            os.remove(out)
            skipped.append((txd_name, 'verify fail: %s' % bad[:3]))
            continue
        done.append((txd_name, added))
    print('merged:', len(done), 'skipped:', len(skipped))
    for s in skipped:
        print('  skip:', s)
    return 0


if __name__ == '__main__':
    sys.exit(main())
