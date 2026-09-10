"""Vanilla-manifest validator: install health + mod-pack checks.

Backed by database/vanilla_sa.db (see database/vanilla_manifest.py).
Call sites: SCAN FOR ISSUES 'Vanilla' category, pre-launch preflight,
pack_state install verification.
"""
import os
import sqlite3

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.path.dirname(_HERE)
DEFAULT_DB = os.path.join(_PROJECT, 'database', 'vanilla_sa.db')

_VANILLA_ASIS = {'modloader.asi'}


def open_db(path=None):
    p = path or DEFAULT_DB
    if not os.path.isfile(p):
        raise FileNotFoundError('vanilla manifest DB missing: %s '
                                '(regenerate: python database/vanilla_manifest.py '
                                '--game-dir <dir>)' % p)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    return con


def base_texture_names(con=None):
    """All texture names inside base-game IMG TXDs (for audit dedup)."""
    own = con is None
    if own:
        con = open_db()
    try:
        return {r[0] for r in
                con.execute('SELECT tex FROM img_textures')}
    finally:
        if own:
            con.close()


def validate_install(game_dir, con=None):
    """Health-check a game install. Returns dict report (lists, all JSON-safe)."""
    game = os.path.abspath(game_dir)
    own = con is None
    if own:
        con = open_db()
    rep = {'missing_base': [], 'unexpected_root_asi': [],
           'ide_redefinitions': [], 'txdp_unresolved': [],
           'img_entry_total': 0}
    try:
        rep['img_entry_total'] = con.execute(
            'SELECT COUNT(*) FROM img_entries').fetchone()[0]
        # 1. base files present? (sample: exe, gta.dat, default.dat + spot-check)
        must = ['gta_sa.exe', 'data/gta.dat', 'data/default.dat',
                'models/gta3.img', 'models/player.img', 'models/gta_int.img']
        for rel in must:
            ap = os.path.join(game, *rel.split('/'))
            if not os.path.isfile(ap):
                rep['missing_base'].append(rel)
                continue
            row = con.execute('SELECT size, sha1 FROM base_files WHERE path=?',
                              (rel,)).fetchone()
            if row and row['sha1'] and _sha1(ap) != row['sha1']:
                rep['missing_base'].append(rel + ' (MODIFIED vs manifest)')
        # 2. unexpected root ASIs (anything beyond known shims)
        try:
            root_files = os.listdir(game)
        except OSError:
            root_files = []
        known_roots = {r['path'].split('/')[0] for r in
                       con.execute("SELECT path FROM base_files WHERE path NOT "
                                   "LIKE '%/%'")}
        for fn in sorted(root_files):
            if not fn.lower().endswith(('.asi', '.dll')):
                continue
            if fn not in known_roots and fn.lower() not in _VANILLA_ASIS:
                rep['unexpected_root_asi'].append(fn)
        # 3. modloader IDE redefinitions vs vanilla (different model, same id)
        ml = os.path.join(game, 'modloader')
        if os.path.isdir(ml):
            for dirpath, _d, files in os.walk(ml):
                for fn in files:
                    if not fn.lower().endswith('.ide'):
                        continue
                    for _id, model in _ide_ids(os.path.join(dirpath, fn)):
                        rows = con.execute(
                            'SELECT model, txd FROM ide_models WHERE id=?',
                            (_id,)).fetchall()
                        vanilla = {r['model'] for r in rows}
                        if vanilla and model.lower() not in vanilla:
                            pack = os.path.relpath(dirpath, ml).split(os.sep)[0]
                            rep['ide_redefinitions'].append(
                                {'id': _id, 'model': model, 'pack': pack,
                                 'vanilla': sorted(vanilla)[:3]})
                            if len(rep['ide_redefinitions']) >= 200:
                                break
                else:
                    continue
                break
        # 4. txdp parents resolvable? (parent txd file or img entry must exist)
        img_names = {r[0].lower() for r in
                     con.execute('SELECT name FROM img_entries')}
        loose_txds = set()
        for dirpath, _d, files in os.walk(ml):
            for fn in files:
                if fn.lower().endswith('.txd'):
                    loose_txds.add(fn.lower())
        for child, parent, _src in con.execute(
                'SELECT child, parent, src_file FROM txdp_links'):
            if parent + '.txd' not in loose_txds \
                    and parent + '.txd' not in img_names:
                rep['txdp_unresolved'].append(
                    {'child': child, 'parent': parent})
    finally:
        if own:
            con.close()
    return rep


def check_pack(pack_path, con=None):
    """Files in a mod pack that collide with vanilla base paths or IMG names.

    Returns {overwrites_base: [rel], shadows_img: [name]}.
    """
    own = con is None
    if own:
        con = open_db()
    try:
        base = {r[0] for r in con.execute('SELECT path FROM base_files')}
        imgs = {r[0].lower() for r in
                con.execute('SELECT name FROM img_entries')}
        overwrites, shadows = [], []
        for dirpath, _d, files in os.walk(pack_path):
            for fn in files:
                rel = os.path.relpath(os.path.join(dirpath, fn),
                                      pack_path).replace(os.sep, '/')
                if rel in base:
                    overwrites.append(rel)
                if fn.lower() in imgs:
                    shadows.append(fn)
        return {'overwrites_base': sorted(set(overwrites)),
                'shadows_img': sorted(set(shadows))}
    finally:
        if own:
            con.close()


def _sha1(path, chunk=65536):
    import hashlib
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for blk in iter(lambda: f.read(chunk), b''):
            h.update(blk)
    return h.hexdigest()


def _ide_ids(path):
    """Yield (id, model) from objs/tobj sections."""
    out = []
    try:
        text = open(path, encoding='utf-8', errors='replace').read()
    except OSError:
        return out
    section = None
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith(('#', '//', ';')):
            continue
        low = s.lower()
        if low == 'end':
            section = None
            continue
        if low in ('objs', 'tobj'):
            section = low
            continue
        if section in ('objs', 'tobj'):
            parts = [x.strip() for x in ln.split(',')]
            if len(parts) >= 2 and parts[0].isdigit():
                out.append((parts[0], parts[1]))
    return out
