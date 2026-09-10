"""Install provenance registry (BAIN-style tracking).

Algorithm inspired by Wrye Bash BAIN (GPL); clean-room implementation.
"""
import hashlib
import json
import os
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.path.dirname(_HERE)
REG_DIR = os.path.join(_PROJECT, 'launcher_data', 'install_registry')


def _reg_dir():
    os.makedirs(REG_DIR, exist_ok=True)
    return REG_DIR


def sha1_file(path, chunk=65536):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for blk in iter(lambda: f.read(chunk), b''):
            h.update(blk)
    return h.hexdigest()


def _pack_path(name):
    safe = ''.join(c for c in name if c.isalnum() or c in (' ', '_', '-', '.')).strip()
    return os.path.join(_reg_dir(), safe + '.json')


def record(name, source, files, order=50, group=''):
    """Register an installed pack. files = [{rel, size, sha1}]."""
    data = {
        'name': name, 'source': source, 'files': list(files),
        'order': int(order), 'active': True, 'group': group,
        'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    with open(_pack_path(name), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    return data


def _load(name):
    p = _pack_path(name)
    if not os.path.isfile(p):
        return None
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def unregister(name):
    """Remove a pack record; returns its tracked rel paths (for uninstall)."""
    data = _load(name)
    p = _pack_path(name)
    if os.path.isfile(p):
        os.remove(p)
    return [f['rel'] for f in (data or {}).get('files', [])]


def installed_files(name):
    data = _load(name)
    return [f['rel'] for f in (data or {}).get('files', [])]


def all_packs():
    out = []
    if not os.path.isdir(REG_DIR):
        return out
    for fn in sorted(os.listdir(REG_DIR)):
        if fn.endswith('.json'):
            try:
                with open(os.path.join(REG_DIR, fn), encoding='utf-8') as f:
                    out.append(json.load(f))
            except (OSError, ValueError):
                continue
    return out


def pack_for_file(rel):
    """Reverse lookup: which packs track this game-relative path?"""
    return [p['name'] for p in all_packs()
            if any(f['rel'] == rel for f in p.get('files', []))]


def scan_tree(root):
    """Walk an installed pack dir -> [{rel, size, sha1}]."""
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for fn in sorted(files):
            ap = os.path.join(dirpath, fn)
            rel = os.path.relpath(ap, root).replace(os.sep, '/')
            try:
                out.append({'rel': rel, 'size': os.path.getsize(ap),
                            'sha1': sha1_file(ap)})
            except OSError:
                continue
    return out


def anneal(name, root):
    """Report per-file status vs registry. NEVER deletes or overwrites.

    Returns {ok:[], missing:[], mismatched:[]}.
    """
    res = {'ok': [], 'missing': [], 'mismatched': []}
    data = _load(name)
    if not data:
        return res
    for f in data.get('files', []):
        ap = os.path.join(root, f['rel'].replace('/', os.sep))
        if not os.path.isfile(ap):
            res['missing'].append(f['rel'])
            continue
        try:
            ok = (os.path.getsize(ap) == f['size']
                  and sha1_file(ap) == f['sha1'])
        except OSError:
            ok = False
        res['ok' if ok else 'mismatched'].append(f['rel'])
    return res
