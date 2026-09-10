"""File-overlap conflict detection across install-registry packs.

Algorithm inspired by Wrye Bash BAIN (GPL); clean-room implementation.
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.path.dirname(_HERE)
REG_DIR = os.path.join(_PROJECT, 'launcher_data', 'install_registry')


def _load_packs(registry_dir=None, include_inactive=True):
    d = registry_dir or REG_DIR
    packs = []
    if not os.path.isdir(d):
        return packs
    for fn in sorted(os.listdir(d)):
        if not fn.endswith('.json'):
            continue
        try:
            with open(os.path.join(d, fn), encoding='utf-8') as f:
                p = json.load(f)
        except (OSError, ValueError):
            continue
        if not include_inactive and not p.get('active', True):
            continue
        packs.append(p)
    return packs


def detect_conflicts(registry_dir=None, focus=None):
    """Return {conflicts: [{rel, packs: [{name, order, sha1}]}]}.

    Same rel + >1 distinct sha1 = conflict. Identical content everywhere
    is dedup, not a conflict. With focus=<pack>, each conflict is annotated
    higher:[names]/lower:[names] by install order.
    """
    packs = _load_packs(registry_dir)
    by_rel = {}
    for p in packs:
        for f in p.get('files', []):
            by_rel.setdefault(f['rel'], []).append({
                'name': p.get('name', '?'),
                'order': int(p.get('order', 50)),
                'sha1': f.get('sha1', ''),
                'active': bool(p.get('active', True)),
            })
    out = []
    focus_order = None
    if focus:
        for p in packs:
            if p.get('name') == focus:
                focus_order = int(p.get('order', 50))
                break
    for rel in sorted(by_rel):
        entries = sorted(by_rel[rel], key=lambda e: (e['order'], e['name']))
        if len({e['sha1'] for e in entries}) < 2:
            continue
        item = {'rel': rel, 'packs': entries}
        if focus_order is not None:
            item['higher'] = [e['name'] for e in entries
                              if e['order'] > focus_order]
            item['lower'] = [e['name'] for e in entries
                             if e['order'] <= focus_order
                             and e['name'] != focus]
        out.append(item)
    return {'conflicts': out}
