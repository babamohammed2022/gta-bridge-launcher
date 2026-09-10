"""Install-order management with undo history.

Algorithm inspired by Wrye Bash load order handling (GPL);
clean-room implementation. Priority = list index (higher wins file
conflicts). Map to modloader.ini Priority 0-100 on export.
"""
import json
import os
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.path.dirname(_HERE)
ORDER_FILE = os.path.join(_PROJECT, 'launcher_data', 'order.json')
_HISTORY_CAP = 20


def _blank():
    return {'order': [], 'history': []}


def _load_data(path=None):
    p = path or ORDER_FILE
    if os.path.isfile(p):
        try:
            with open(p, encoding='utf-8') as f:
                d = json.load(f)
            if isinstance(d.get('order'), list):
                d.setdefault('history', [])
                return d
        except (OSError, ValueError):
            pass
    return _blank()


def _save_data(data, path=None):
    p = path or ORDER_FILE
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, p)


class OrderManager:
    def __init__(self, path=None):
        self.path = path or ORDER_FILE
        self._data = _load_data(self.path)

    def _snapshot(self):
        self._data['history'].append({
            'date': time.time(),
            'order': [dict(e) for e in self._data['order']],
        })
        self._data['history'] = self._data['history'][-_HISTORY_CAP:]

    def save(self):
        _save_data(self._data, self.path)

    def order_names(self):
        return [e['name'] for e in self._data['order']]

    def add_pack(self, name, active=True):
        if name in self.order_names():
            return False
        self._snapshot()
        self._data['order'].append({'name': name, 'active': bool(active)})
        return True

    def remove_pack(self, name):
        if name not in self.order_names():
            return False
        self._snapshot()
        self._data['order'] = [e for e in self._data['order']
                               if e['name'] != name]
        return True

    def move(self, name, new_index):
        names = self.order_names()
        if name not in names:
            return False
        self._snapshot()
        entry = self._data['order'].pop(names.index(name))
        new_index = max(0, min(new_index, len(self._data['order'])))
        self._data['order'].insert(new_index, entry)
        return True

    def set_active(self, name, active):
        for e in self._data['order']:
            if e['name'] == name:
                if bool(e.get('active', True)) == bool(active):
                    return False
                self._snapshot()
                e['active'] = bool(active)
                return True
        return False

    def diff(self, old_names, new_names=None):
        """Port of LordDiff idea: {missing, added, reordered, active_flips}."""
        new_names = self.order_names() if new_names is None else list(new_names)
        old_act = {e['name']: bool(e.get('active', True))
                   for e in self._data.get('_last_seen', [])}
        new_act = {e['name']: bool(e.get('active', True))
                   for e in self._data['order'] if e['name'] in new_names}
        return {
            'missing': [n for n in old_names if n not in new_names],
            'added': [n for n in new_names if n not in old_names],
            'reordered': [n for n in new_names if n in old_names
                          and new_names.index(n) != old_names.index(n)],
            'active_flips': sorted(
                n for n in new_names
                if n in old_act and old_act[n] != new_act.get(n, True)),
        }

    def undo(self):
        if not self._data['history']:
            return False
        self._data['order'] = self._data['history'].pop()['order']
        return True


def priority_for_index(index, total):
    """Map order index -> modloader.ini Priority 0-100 scale."""
    if total <= 1:
        return 100
    return int(round(100.0 * index / (total - 1)))
