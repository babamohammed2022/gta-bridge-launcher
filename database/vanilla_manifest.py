"""Vanilla San Andreas structure manifest -> SQLite DB.

Source of truth: the game's own data files (data/gta.dat, data/default.dat,
models/*.img, IDE/IPL/TXDP). No external manifest needed — skygfx and other
repos ship no vanilla file map; gta.dat IS the map.

DB: database/vanilla_sa.db
Tables:
  base_files(path, size, sha1, kind)   -- game-root/data/anim/audio(sizes)/streams(sizes)
  img_entries(archive, name, offset, size)
  ide_models(id, model, txd, src_file)
  txdp_links(child, parent, src_file)
  dat_refs(kind, path, src_file)        -- IMG/IDE/IPL/SPLASH lines per dat file

Regenerate: venv64 python database/vanilla_manifest.py --game-dir <dir> [--db out]
"""
import argparse
import hashlib
import os
import sqlite3
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.path.dirname(_HERE)
sys.path.insert(0, _PROJECT)

from managers import mapdata  # noqa: E402

SCHEMA = """
CREATE TABLE IF NOT EXISTS base_files(path TEXT PRIMARY KEY, size INTEGER,
    sha1 TEXT, kind TEXT);
CREATE TABLE IF NOT EXISTS img_entries(archive TEXT, name TEXT,
    offset INTEGER, size INTEGER, PRIMARY KEY (archive, name));
CREATE TABLE IF NOT EXISTS img_textures(txd TEXT, tex TEXT,
    PRIMARY KEY (txd, tex));
CREATE TABLE IF NOT EXISTS ide_models(id TEXT, model TEXT, txd TEXT,
    src_file TEXT, PRIMARY KEY (id, src_file));
CREATE TABLE IF NOT EXISTS txdp_links(child TEXT, parent TEXT,
    src_file TEXT, PRIMARY KEY (child, src_file));
CREATE TABLE IF NOT EXISTS dat_refs(kind TEXT, path TEXT, src_file TEXT);
CREATE INDEX IF NOT EXISTS idx_img_name ON img_entries(name);
CREATE INDEX IF NOT EXISTS idx_ide_id ON ide_models(id);
"""


def sha1_of(path, bulk=False, chunk=65536):
    if bulk:
        return ''
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for blk in iter(lambda: f.read(chunk), b''):
            h.update(blk)
    return h.hexdigest()


def parse_dat_lines(path):
    """Yield (kind, arg) for IMG/IDE/IPL/SPLASH/CDIMAGE lines."""
    out = []
    try:
        text = open(path, encoding='utf-8', errors='replace').read()
    except OSError:
        return out
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith('#'):
            continue
        parts = s.split(None, 1)
        if len(parts) == 2 and parts[0].upper() in (
                'IMG', 'IDE', 'IPL', 'SPLASH', 'CDIMAGE', 'TEXDICTION',
                'COLFILE', 'MODELFILE'):
            out.append((parts[0].upper(), parts[1].strip()))
    return out


def parse_ide(path):
    """Yield (section, fields) rows; sections objs/tobj/txdp tracked."""
    rows = []
    try:
        text = open(path, encoding='utf-8', errors='replace').read()
    except OSError:
        return rows
    section = None
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith(('#', '//', ';')):
            continue
        low = s.lower()
        if low == 'end':
            section = None
            continue
        if low in ('objs', 'tobj', 'hier', 'txdp', 'anim', 'cars', 'peds',
                    'weap', '2dfx'):
            section = low
            continue
        if section in ('objs', 'tobj', 'txdp'):
            rows.append((section, [x.strip() for x in ln.split(',')]))
        elif section in ('cars', 'weap'):
            # vehicles.ide/weapons.ide: id, model, txd, ... (same columns)
            rows.append(('objs', [x.strip() for x in ln.split(',')]))
            # NOTE: peds.ide 'peds' section is ped GROUPS, not models — skipped
    return rows


def build(game_dir, db_path):
    game = os.path.abspath(game_dir)
    if os.path.exists(db_path):
        os.remove(db_path)
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    # --- base files -----------------------------------------------------
    bulk_dirs = ('audio', 'streams')
    for dirpath, _dirs, files in os.walk(game):
        rel_dir = os.path.relpath(dirpath, game)
        if rel_dir.split(os.sep)[0].lower() in ('modloader', 'modloader_back'):
            continue
        for fn in sorted(files):
            ap = os.path.join(dirpath, fn)
            try:
                rel = os.path.relpath(ap, game).replace(os.sep, '/')
            except (OSError, ValueError):
                continue  # undead paths (NUL device, broken junctions)
            if rel.startswith('launcher_data/'):
                continue
            try:
                size = os.path.getsize(ap)
            except OSError:
                continue
            bulk = rel.split('/')[0].lower() in bulk_dirs
            try:
                digest = sha1_of(ap, bulk=bulk)
            except OSError:
                continue
            con.execute('INSERT OR REPLACE INTO base_files VALUES (?,?,?,?)',
                        (rel, size, digest,
                         'bulk' if bulk else 'base'))
    # --- dat refs + IDE/IPL models --------------------------------------
    for dat in ('data/gta.dat', 'data/default.dat'):
        ap = os.path.join(game, dat.replace('/', os.sep))
        for kind, arg in parse_dat_lines(ap):
            con.execute('INSERT INTO dat_refs VALUES (?,?,?)',
                        (kind, arg, dat))
    ide_files = [r[0] for r in
                 con.execute("SELECT path FROM dat_refs WHERE kind='IDE'")]
    for rel in ide_files:
        ap = os.path.join(game, rel.replace('/', os.sep).replace('\\', os.sep))
        for section, fields in parse_ide(ap):
            src = rel.replace('\\', '/')
            if section in ('objs', 'tobj') and len(fields) >= 3 \
                    and fields[0].isdigit():
                con.execute('INSERT OR REPLACE INTO ide_models VALUES (?,?,?,?)',
                            (fields[0], fields[1].lower(),
                             fields[2].lower(), src))
            elif section == 'txdp' and len(fields) == 2:
                con.execute('INSERT OR REPLACE INTO txdp_links VALUES (?,?,?)',
                            (fields[0].lower(), fields[1].lower(), src))
    # --- IMG entries -----------------------------------------------------
    # NOTE: gta.dat lists only 3 IMGs. SA hardcodes the rest in the exe —
    # these well-known archives are always loaded by a vanilla game.
    HARDCODED_IMGS = ['MODELS/GTA3.IMG', 'MODELS/PLAYER.IMG',
                      'MODELS/GTA_INT.IMG', 'ANIM/CUTS.IMG']
    seen = set()
    for (arc,) in con.execute("SELECT path FROM dat_refs WHERE kind='IMG'"):
        seen.add(arc.replace('\\', '/').upper())
    img_refs = [r[0] for r in
                con.execute("SELECT path FROM dat_refs WHERE kind='IMG'")]
    for hard in HARDCODED_IMGS:
        if hard.upper() not in seen:
            img_refs.append(hard)
            con.execute('INSERT INTO dat_refs VALUES (?,?,?)',
                        ('IMG', hard, '<engine-hardcoded>'))
    for arc in img_refs:
        ap = os.path.join(game, arc.replace('/', os.sep).replace('\\', os.sep))
        if not os.path.isfile(ap):
            continue
        try:
            entries = mapdata.read_img_entries(ap)
        except Exception:
            continue
        aname = arc.replace('\\', '/')
        for name, off, size in entries:
            if not name or not name.split('.')[0]:
                continue  # junk entries (empty stem like '.dff')
            con.execute('INSERT OR REPLACE INTO img_entries VALUES (?,?,?,?)',
                        (aname, name, off, size))
    con.commit()
    stats = {t: con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
             for t in ('base_files', 'img_entries', 'ide_models',
                       'txdp_links', 'dat_refs')}
    # --- base TXD texture-name index (kills audit false positives) ---------
    try:
        from managers import txdlite as _txd
    except ImportError:
        _txd = None
    if _txd is not None:
        for (arc,) in con.execute(
                "SELECT DISTINCT archive FROM img_entries"):
            ap = os.path.join(game, arc.replace('/', os.sep))
            if not os.path.isfile(ap):
                continue
            try:
                entries = mapdata.read_img_entries(ap)
            except Exception:
                continue
            with open(ap, 'rb') as fh:
                for name, off, size in entries:
                    if not name.endswith('.txd') or size > 32 * 1048576:
                        continue
                    try:
                        fh.seek(off)
                        tf = _txd.TxdFile.loads(fh.read(size))
                        for x in tf.textures:
                            xn = str(getattr(x, 'name', '')).lower()
                            if xn:
                                con.execute('INSERT OR IGNORE INTO img_textures '
                                            'VALUES (?,?)', (name, xn))
                    except Exception:
                        continue
        con.commit()
        stats['img_textures'] = con.execute(
            'SELECT COUNT(*) FROM img_textures').fetchone()[0]
    con.close()
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(description='Build vanilla SA manifest DB')
    ap.add_argument('--game-dir', required=True)
    ap.add_argument('--db', default=os.path.join(_HERE, 'vanilla_sa.db'))
    args = ap.parse_args(argv)
    stats = build(args.game_dir, args.db)
    print('wrote %s' % args.db)
    for k, v in stats.items():
        print('  %-12s %d' % (k, v))
    return 0


if __name__ == '__main__':
    sys.exit(main())
