#!/usr/bin/env python3
"""RenderWare binary stream inspector (pure stdlib).

Section IDs empirically calibrated against real SA files (modloader packs):
    0x01 Struct            0x02 String         0x03 Extension
    0x07 Material          0x08 MaterialList   0x0E FrameList
    0x0F GeometryList      0x10 Clump          0x14 Atomic
    0x15 TextureNative     0x16 TextureDictionary
    0x1A GeometryList-outer (SA clumps wrap {Struct, 0x0F})
SA vendor plugin ids found in Extensions: 0x116 skin, 0x11E 2dfx.
TXD TexNativeHeader (Struct body): platform@0 u32, filter@4 u8, addr@5 u8,
    name@8[32], maskName@40[32], rasterFormat@72 u32, fourCC@76[4],
    width@80 u16, height@82 u16, depth@84 u8, mips@85 u8, rasterType@86,
    dxtType@87.
Usage: python rw_inspect.py <file...>  -> JSON per file
"""
import json
import struct
import sys
from pathlib import Path

SECTION_NAMES = {
    0x01: 'Struct', 0x02: 'String', 0x03: 'Extension', 0x05: 'Texture',
    0x07: 'Material', 0x08: 'MaterialList', 0x0E: 'FrameList',
    0x0F: 'GeometryList', 0x10: 'Clump', 0x14: 'Atomic',
    0x15: 'TextureNative', 0x16: 'TextureDictionary', 0x1A: 'GeometryList',
}

FOURCC_DXT = {'DXT1', 'DXT2', 'DXT3', 'DXT4', 'DXT5'}
ALPHA_DXT = {'DXT2', 'DXT3', 'DXT4', 'DXT5'}


def _walk(data, off, end):
    """Yield (tid, size, body_off, body_end) chunks in [off, end)."""
    while off + 12 <= end:
        try:
            tid, size, _ver = struct.unpack_from('<III', data, off)
        except struct.error:
            return
        if size < 0 or off + 12 + size > end:
            return
        yield tid, size, off + 12, off + 12 + size
        off += 12 + size


def _fmt_name(raster_format, fourcc):
    if fourcc in FOURCC_DXT:
        return fourcc
    base = raster_format & 0xF
    names = {0x01: '1555', 0x02: '565', 0x03: '4444', 0x04: 'LUM8',
             0x05: '8888', 0x06: '16', 0x07: '24', 0x08: '32'}
    return names.get(base, f'fmt{raster_format:#010x}')


def inspect_txd(path):
    data = Path(path).read_bytes()
    out = {'type': 'txd', 'file': Path(path).name, 'bytes': len(data),
           'texture_count': 0, 'textures': []}
    for tid, size, boff, bend in _walk(data, 0, len(data)):
        if tid != 0x16:  # TextureDictionary root
            continue
        for ctid, csize, coff, cend in _walk(data, boff, bend):
            if ctid != 0x15:  # TextureNative
                continue
            tex = {'name': '', 'mask': '', 'w': 0, 'h': 0, 'depth': 0,
                   'format': '', 'alpha': False, 'mipmaps': 0}
            for stid, ssize, soff, send in _walk(data, coff, cend):
                if stid == 0x01 and ssize >= 88:
                    try:
                        platform, = struct.unpack_from('<I', data, soff)
                        filter_mode = data[soff + 4]
                        name = data[soff + 8:soff + 40].split(b'\x00')[0]
                        mask = data[soff + 40:soff + 72].split(b'\x00')[0]
                        rfmt, = struct.unpack_from('<I', data, soff + 72)
                        fourcc = data[soff + 76:soff + 80].decode(
                            'ascii', 'replace').strip('\x00')
                        w, h = struct.unpack_from('<HH', data, soff + 80)
                        depth, mips, rtype, dxt = struct.unpack_from(
                            '<BBBB', data, soff + 84)
                        tex.update(
                            platform=platform, filter=filter_mode,
                            name=name.decode('ascii', 'replace').lower(),
                            mask=mask.decode('ascii', 'replace').lower(),
                            w=w, h=h, depth=depth, mipmaps=mips,
                            raster_type=rtype,
                            format=_fmt_name(rfmt, fourcc),
                            alpha=bool(rfmt & 0x2)
                            or fourcc in ALPHA_DXT)
                    except struct.error:
                        pass
            out['textures'].append(tex)
            out['texture_count'] += 1
    return out


def inspect_dff(path):
    data = Path(path).read_bytes()
    out = {'type': 'dff', 'file': Path(path).name, 'bytes': len(data),
           'frames': 0, 'geometries': 0, 'triangles': 0, 'vertices': 0,
           'materials': 0, 'has_skin': False, 'has_2dfx_ext': False}

    def visit(off, end):
        for tid, size, boff, bend in _walk(data, off, end):
            if tid in (0x10, 0x1A):        # Clump / outer geometry wrapper
                visit(boff, bend)
            elif tid == 0x0F:              # GeometryList
                for stid, ssize, soff, send in _walk(data, boff, bend):
                    if stid == 0x01 and ssize >= 12:  # geometry native struct
                        try:
                            _fmt, ntri, nvert = struct.unpack_from(
                                '<III', data, soff)
                            out['geometries'] += 1
                            out['triangles'] += ntri
                            out['vertices'] += nvert
                        except struct.error:
                            pass
                    elif stid == 0x08:       # MaterialList
                        for mtid, msize, moff, mend in _walk(data, soff, send):
                            if mtid == 0x01 and msize >= 4:
                                (n,) = struct.unpack_from('<I', data, moff)
                                out['materials'] += n
                    elif stid == 0x03:       # geometry Extension
                        _scan_extension(data, soff, send, out)
            elif tid == 0x0E:              # FrameList
                for stid, ssize, soff, send in _walk(data, boff, bend):
                    if stid == 0x01 and ssize >= 4:
                        (n,) = struct.unpack_from('<I', data, soff)
                        out['frames'] += n

    for tid, size, boff, bend in _walk(data, 0, len(data)):
        if tid == 0x10:
            visit(boff, bend)
    return out


def _scan_extension(data, off, end, out):
    """Walk extension sub-chunks (u32 id, u32 size, ...) for SA plugins."""
    blob_off = off
    i = 0
    total = end - off
    while i + 8 <= total:
        plg_id, plg_size = struct.unpack_from('<II', data, blob_off + i)
        if plg_size < 0 or i + 8 + plg_size > total:
            break
        if plg_id == 0x116:
            out['has_skin'] = True
        elif plg_id == 0x11E:
            out['has_2dfx_ext'] = True
        i += 8 + plg_size


def inspect_col(path):
    data = Path(path).read_bytes()
    out = {'type': 'col', 'file': Path(path).name, 'bytes': len(data),
           'entries': [], 'entry_count': 0}
    magics = (b'COLL', b'COL2', b'COL3')
    off = 0
    while off + 8 <= len(data):
        magic = data[off:off + 4]
        if magic not in magics:
            break
        (size,) = struct.unpack_from('<I', data, off + 4)
        name_raw = data[off + 8:off + 28].split(b'\x00')[0]
        out['entries'].append({'magic': magic.decode(),
                               'name': name_raw.decode('ascii', 'replace'),
                               'size': size})
        out['entry_count'] += 1
        off += 8 + max(size, 4)
    return out


def inspect_any(path):
    ext = Path(path).suffix.lower()
    try:
        if ext == '.txd':
            return inspect_txd(path)
        if ext == '.dff':
            return inspect_dff(path)
        if ext == '.col':
            return inspect_col(path)
        return {'type': ext.lstrip('.') or 'unknown', 'file': Path(path).name,
                'bytes': Path(path).stat().st_size, 'note': 'no parser'}
    except Exception as exc:  # error-safe: never crash batch runs
        return {'type': ext.lstrip('.') or 'unknown',
                'file': Path(path).name, 'error': str(exc)}


if __name__ == '__main__':
    for arg in sys.argv[1:]:
        print(json.dumps(inspect_any(arg), indent=1))
