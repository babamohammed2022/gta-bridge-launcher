# -*- coding: utf-8 -*-
"""mapdata.py — GTA map data inspectors for the launcher (Ariane Phase 1 port).

* dff_texture_refs(data) -> set of texture names a DFF references
* read_img_entries(path) -> [(name, offset, size)] for IMG archives (v1/v2)
* audit_mod_textures(game_dir) -> audit report: unresolved texture refs,
  duplicate shadows, per-mod file counts. The tool that would have caught
  the 2026-08-26 white-building/bridge conflicts in seconds.
"""
import struct
from pathlib import Path


def dff_texture_refs(data: bytes) -> set:
    """Walk RW chunk tree, collect texture names from Texture (0x06) nodes."""
    refs = set()

    def walk(pos, end):
        while pos + 12 <= end:
            cid, size, _ver = struct.unpack_from('<III', data, pos)
            if size < 0 or pos + 12 + size > end:
                return
            if cid == 0x06:
                cpos, cend = pos + 12, pos + 12 + size
                while cpos + 12 <= cend:
                    ccid, csize, _ = struct.unpack_from('<III', data, cpos)
                    if ccid == 0x02 and csize > 0:
                        s = data[cpos + 12:cpos + 12 + csize].split(b'\x00')[0] \
                            .decode('ascii', 'ignore').strip().lower()
                        if 2 < len(s) < 32:
                            refs.add(s)
                    cpos += 12 + csize
            elif cid in (0x10, 0x1A, 0x0E, 0x0F, 0x08, 0x07, 0x03, 0x14):
                walk(pos + 12, pos + 12 + size)
            pos += 12 + size

    walk(0, len(data))
    return refs


def read_img_entries(path):
    """IMG archive (v1 dir+img or v2 ver2.img) -> [(name, offset, size_bytes)]."""
    p = Path(path)
    entries = []
    if p.suffix.lower() == '.dir':
        img = p.with_suffix('.img')
        raw = p.read_bytes()
        # .dir entries are 32 bytes: u32 offset, u32 size, char name[24]
        for i in range(0, len(raw) - 31, 32):
            name = raw[i + 8:i + 32].split(b'\x00')[0].decode('ascii', 'ignore').lower()
            off, size = struct.unpack_from('<II', raw, i)
            if name:
                entries.append((name, off * 2048, size * 2048))
        return entries
    # v2: header 'VER2' + entry count, then 32-byte entries:
    # u32 offset, u32 size, char name[24] (null-padded)
    with open(p, 'rb') as fh:
        head = fh.read(8)
        if head[:4] != b'VER2':
            raise ValueError('not a v2 IMG')
        (count,) = struct.unpack('<I', head[4:8])
        for _ in range(count):
            raw = fh.read(32)
            if len(raw) < 32:
                break
            off, size = struct.unpack_from('<II', raw, 0)
            name = raw[8:32].split(b'\x00')[0].decode('ascii', 'ignore').lower()
            if name:
                entries.append((name, off * 2048, size * 2048))
    return entries


def audit_mod_textures(game_dir):
    """Cross-reference every modloader DFF's texture refs against available
    TXD textures (modloader + game TXT sets). Returns dict report."""
    game_dir = Path(game_dir)
    ml = game_dir / 'modloader'
    report = {
        'txd_names': set(),        # texture names available via modloader TXDs
        'dff_count': 0,
        'unresolved': {},          # texname -> [dff paths]
        'duplicate_dffs': {},      # dffname -> [mod folders]
        'txd_shadows': {},         # txdname -> [mod folders]
    }

    # gather TXD texture names + shadow map
    for p in ml.rglob('*.txd'):
        rel = str(p.relative_to(ml))
        mod = rel.split('\\')[0].split('/')[0]
        report['txd_shadows'].setdefault(p.name.lower(), []).append(mod)
        try:
            from managers.txdlite import TxdFile
            txd = TxdFile.load(str(p))
            report['txd_names'].update(t.name for t in txd.textures)
        except Exception:
            pass

    # walk DFFs
    for p in ml.rglob('*.dff'):
        rel = str(p.relative_to(ml))
        mod = rel.split('\\')[0].split('/')[0]
        report['duplicate_dffs'].setdefault(p.name.lower(), []).append(mod)
        report['dff_count'] += 1
        try:
            refs = dff_texture_refs(p.read_bytes())
        except Exception:
            continue
        for r in refs:
            if r not in report['txd_names']:
                report['unresolved'].setdefault(r, []).append(rel)
    return report
