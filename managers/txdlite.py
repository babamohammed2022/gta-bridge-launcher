# -*- coding: utf-8 -*-
"""txdlite.py — minimal pure-Python RenderWare TXD engine (Path A port from librw).

GGMM-style TXD editing for the GTA Bridge Launcher:
  * parse SA-style TXDs (TexDictionary > TextureNative chunks)
  * list textures, decode any mip to a PIL image
    (DXT1/DXT3/DXT5, 8888, 888, 1555, 4444, 565, PAL8/PAL4)
  * replace a texture from a PNG/JPG/BMP (re-encodes to the original
    format when supported, else falls back to uncompressed 8888)
  * save back byte-exact for untouched textures

Binary layout ported from E:/SDKs/librw/src/{rwbase.h,texture.cpp,d3d/d3d9.cpp}:
  chunk header = <II I>  id, payload_size, version   (12 bytes, size excludes header)
  TEXDICTIONARY(0x16) > STRUCT(0x01)[numTex i16, device i16] > N x TEXTURENATIVE(0x15)
  TEXTURENATIVE > STRUCT: platform u32, filterAddressing u32, name[32], mask[32],
    rasterFormat i32, d3dFormat i32, width u16, height u16,
    depth u8, numLevels u8, type u8, flags u8,
    [palette 1024B (PAL8) | 128B (PAL4)], then per level: size u32 + data,
    then plugin chunks (kept raw inside the 0x15 payload).
Raster formats: C1555=0x0100 C565=0x0200 C4444=0x0300 LUM8=0x0400 C8888=0x0500
  C888=0x0600 AUTOMIPMAP=0x1000 PAL8=0x2000 PAL4=0x4000 MIPMAP=0x8000
Native flags: 1=hasAlpha 2=cube 4=autogenMip 8=compressed/customFormat
"""
import ctypes
import os
import struct
import sys
from pathlib import Path

# ---------------------------------------------------------------- chunk ids
ID_STRUCT = 0x01
ID_STRING = 0x02
ID_EXTENSION = 0x03
ID_TEXTURE = 0x06
ID_TEXTURENATIVE = 0x15
ID_TEXDICTIONARY = 0x16

FMT_1555 = 0x0100
FMT_565 = 0x0200
FMT_4444 = 0x0300
FMT_LUM8 = 0x0400
FMT_8888 = 0x0500
FMT_888 = 0x0600
FMT_PAL8 = 0x2000
FMT_PAL4 = 0x4000
FMT_MIPMAP = 0x8000

FLAG_ALPHA = 1
FLAG_CUBE = 2
FLAG_AUTOMIP = 4
FLAG_COMPRESSED = 8

DXT1_FMT = 0x31545844  # 'DXT1'
DXT3_FMT = 0x33545844  # 'DXT2/3'
DXT5_FMT = 0x35545844  # 'DXT4/5'


class TxdError(Exception):
    pass


# ---------------------------------------------------------------- decoding
def _expand5(c):
    return (c << 3) | (c >> 2)


def _expand6(c):
    return (c << 2) | (c >> 4)


def _decode_dxt(data, w, h, fmt):
    """Return bytearray RGBA for a DXT1/3/5 mip. Uses txdfix.dll when present."""
    dll = _get_txdfix()
    if dll is not None:
        bw, bh = (w + 3) // 4, (h + 3) // 4
        in_buf = ctypes.create_string_buffer(bytes(data), len(data))
        out_buf = ctypes.create_string_buffer(w * h * 4)
        dll.dxt_decode(in_buf, w, h, 1 if fmt == DXT1_FMT else (3 if fmt == DXT3_FMT else 5),
                       out_buf)
        return bytearray(out_buf.raw[:w * h * 4])
    return _decode_dxt_py(data, w, h, fmt)


def _decode_dxt_py(data, w, h, fmt):
    """Pure-Python DXT1/3/5 decode (fallback)."""
    out = bytearray(w * h * 4)
    is_dxt1 = fmt == DXT1_FMT
    is_dxt3 = fmt == DXT3_FMT
    bw, bh = (w + 3) // 4, (h + 3) // 4
    off = 0
    for by in range(bh):
        for bx in range(bw):
            if is_dxt3:
                a_row = struct.unpack_from("<8H", data, off)
                off += 8
            elif not is_dxt1:  # dxt5
                a0, a1 = data[off], data[off + 1]
                bits = struct.unpack_from("<Q", data, off + 2)[0]
                off += 8
                apal = [a0, a1]
                if a0 > a1:
                    for i in range(6):
                        apal.append(((6 - i) * a0 + (i + 1) * a1) // 7)
                else:
                    apal.extend([(4 * a0 + a1) // 5, (3 * a0 + 2 * a1) // 5,
                                 (2 * a0 + 3 * a1) // 5, (a0 + 4 * a1) // 5, 0, 255])
            c0, c1 = struct.unpack_from("<HH", data, off)
            cbits = struct.unpack_from("<I", data, off + 4)[0]
            off += 8
            pal = []
            for c in (c0, c1):
                pal.append((_expand5((c >> 11) & 31), _expand6((c >> 5) & 63),
                            _expand5(c & 31), 255))
            if is_dxt1:
                if c0 <= c1:
                    pal.append((0, 0, 0, 0))
                    pal.append((0, 0, 0, 0))
                else:
                    r0, g0, b0, _ = pal[0]
                    r1, g1, b1, _ = pal[1]
                    pal.append(((2 * r0 + r1) // 3, (2 * g0 + g1) // 3,
                                (2 * b0 + b1) // 3, 255))
                    pal.append(((r0 + 2 * r1) // 3, (g0 + 2 * g1) // 3,
                                (b0 + 2 * b1) // 3, 255))
            else:
                r0, g0, b0, _ = pal[0]
                r1, g1, b1, _ = pal[1]
                pal.append(((2 * r0 + r1) // 3, (2 * g0 + g1) // 3, (2 * b0 + b1) // 3, 255))
                pal.append(((r0 + 2 * r1) // 3, (g0 + 2 * g1) // 3, (b0 + 2 * b1) // 3, 255))
            for py in range(4):
                yy = by * 4 + py
                if yy >= h:
                    break
                for px in range(4):
                    xx = bx * 4 + px
                    if xx >= w:
                        cbits >>= 2
                        continue
                    idx = cbits & 3
                    cbits >>= 2
                    r, g, b, a = pal[idx]
                    if is_dxt3:
                        a = (a_row[py] >> (px * 4)) & 0xF
                        a = (a << 4) | a
                    elif not is_dxt1:
                        a = apal[(bits >> (3 * (py * 4 + px))) & 7]
                    o = (yy * w + xx) * 4
                    out[o:o + 4] = bytes((r, g, b, a))
    return out


def _decode_16bit(data, w, h, fmt):
    out = bytearray(w * h * 4)
    words = struct.unpack_from("<%dH" % (w * h), data)
    o = 0
    if fmt == FMT_1555:
        for c in words:
            out[o] = _expand5(c & 31)
            out[o + 1] = _expand5((c >> 5) & 31)
            out[o + 2] = _expand5((c >> 10) & 31)
            out[o + 3] = 255 if (c & 0x8000) else 0
            o += 4
    elif fmt == FMT_565:
        for c in words:
            out[o] = _expand5(c & 31)
            out[o + 1] = _expand6((c >> 5) & 63)
            out[o + 2] = _expand5((c >> 11) & 31)
            out[o + 3] = 255
            o += 4
    else:  # 4444
        for c in words:
            n = c & 0xF
            out[o] = (n << 4) | n
            n = (c >> 4) & 0xF
            out[o + 1] = (n << 4) | n
            n = (c >> 8) & 0xF
            out[o + 2] = (n << 4) | n
            n = (c >> 12) & 0xF
            out[o + 3] = (n << 4) | n
            o += 4
    return out


def decode_mip(tex, level=0):
    """Decode mip `level` of `tex` into a PIL RGBA image."""
    from PIL import Image
    w = max(1, tex.width >> level)
    h = max(1, tex.height >> level)
    data = tex.mips[level]
    rf = tex.raster_format & 0x0F00  # format bits only (MIPMAP=0x8000 excluded)
    if tex.flags & FLAG_COMPRESSED and tex.d3d_format in (DXT1_FMT, DXT3_FMT, DXT5_FMT):
        rgba = _decode_dxt(data, w, h, tex.d3d_format)
    elif tex.flags & FLAG_COMPRESSED:
        # bogus/unknown FourCC (e.g. PS2-origin 0x15) — data is raw BGRA8888
        rgba = bytearray(w * h * 4)
        for o in range(0, len(rgba), 4):
            rgba[o] = data[o + 2]
            rgba[o + 1] = data[o + 1]
            rgba[o + 2] = data[o]
            rgba[o + 3] = data[o + 3]
    elif rf == FMT_8888:
        rgba = bytearray(w * h * 4)
        for o in range(0, len(rgba), 4):
            rgba[o] = data[o + 2]      # file order BGRA -> RGBA
            rgba[o + 1] = data[o + 1]
            rgba[o + 2] = data[o]
            rgba[o + 3] = data[o + 3]
    elif rf == FMT_888:
        rgba = bytearray(w * h * 4)
        for i in range(w * h):
            s = i * 3
            d = i * 4
            rgba[d] = data[s + 2]
            rgba[d + 1] = data[s + 1]
            rgba[d + 2] = data[s]
            rgba[d + 3] = 255
    elif rf in (FMT_1555, FMT_565, FMT_4444):
        rgba = _decode_16bit(data, w, h, rf)
    elif tex.raster_format & FMT_PAL8:
        rgba = bytearray(w * h * 4)
        for i in range(w * h):
            p = data[i] * 4
            rgba[i * 4] = tex.palette[p + 2]
            rgba[i * 4 + 1] = tex.palette[p + 1]
            rgba[i * 4 + 2] = tex.palette[p]
            rgba[i * 4 + 3] = tex.palette[p + 3]
    elif tex.raster_format & FMT_PAL4:
        rgba = bytearray(w * h * 4)
        for i in range(w * h):
            idx = (data[i >> 1] >> 4) if (i & 1) == 0 else (data[i >> 1] & 0xF)
            p = idx * 4
            rgba[i * 4] = tex.palette[p + 2]
            rgba[i * 4 + 1] = tex.palette[p + 1]
            rgba[i * 4 + 2] = tex.palette[p]
            rgba[i * 4 + 3] = tex.palette[p + 3]
    elif rf == FMT_LUM8:
        rgba = bytearray(w * h * 4)
        for i in range(w * h):
            rgba[i * 4] = rgba[i * 4 + 1] = rgba[i * 4 + 2] = data[i]
            rgba[i * 4 + 3] = 255
    else:
        raise TxdError("unsupported raster format 0x%04X (%s)" % (rf, tex.name))
    return Image.frombytes("RGBA", (w, h), bytes(rgba))


# ---------------------------------------------------------------- encoding
def _fit_dxt1_block(px):
    """px = 16 (r,g,b,a) tuples -> (color0, color1, index_bits) opaque mode.

    Indices MUST be chosen against the decoder's real palette order:
      idx0=c0, idx1=c1, idx2=(2*c0+c1)/3, idx3=(c0+2*c1)/3
    and c0 must stay > c1 so the decoder never enters 3-color+transparent mode.
    """
    lo = [255, 255, 255]
    hi = [0, 0, 0]
    for r, g, b, _ in px:
        for k, v in enumerate((r, g, b)):
            if v < lo[k]:
                lo[k] = v
            if v > hi[k]:
                hi[k] = v

    def pack565(rgb):
        return ((rgb[0] >> 3) << 11) | ((rgb[1] >> 2) << 5) | (rgb[2] >> 3)

    def unpack565(c):
        return (_expand5((c >> 11) & 31), _expand6((c >> 5) & 63), _expand5(c & 31))

    c0 = pack565(hi)
    c1 = pack565(lo)
    if c0 == c1:
        c1 = c0 ^ 1          # force strict 4-color mode on uniform blocks
    if c0 < c1:
        c0, c1 = c1, c0
    p0 = unpack565(c0)
    p1 = unpack565(c1)
    pal = (p0, p1,
           tuple((2 * a + b) // 3 for a, b in zip(p0, p1)),
           tuple((a + 2 * b) // 3 for a, b in zip(p0, p1)))
    bits = 0
    for i, (r, g, b, _) in enumerate(px):
        best, bd = 0, 1 << 30
        for j in range(4):
            pr, pg, pb = pal[j]
            d = (pr - r) ** 2 + (pg - g) ** 2 + (pb - b) ** 2
            if d < bd:
                bd, best = d, j
        bits |= best << (2 * i)
    return c0, c1, bits


def _encode_dxt(img, fmt):
    """img: PIL RGBA. Returns DXT payload bytes. Uses txdfix.dll when present."""
    w, h = img.size
    data = img.tobytes()
    dll = _get_txdfix()
    if dll is not None:
        is_dxt1 = fmt == DXT1_FMT
        is_dxt3 = fmt == DXT3_FMT
        bw, bh = (w + 3) // 4, (h + 3) // 4
        out_size = bw * bh * (8 if is_dxt1 else 16)
        in_buf = ctypes.create_string_buffer(data, len(data))
        out_buf = ctypes.create_string_buffer(out_size)
        n = dll.dxt_encode(in_buf, w, h, 1 if is_dxt1 else (3 if is_dxt3 else 5),
                           out_buf)
        return out_buf.raw[:n]
    return _encode_dxt_py(img, fmt)


_TXDFIX = None
_TXDFIX_TRIED = False


def _get_txdfix():
    """Load txdfix.dll (next to module / next to exe) once; None = fallback."""
    global _TXDFIX, _TXDFIX_TRIED
    if _TXDFIX_TRIED:
        return _TXDFIX
    _TXDFIX_TRIED = True
    import ctypes
    import sys
    candidates = [os.path.join(os.path.dirname(os.path.abspath(__file__)), 'txdfix.dll')]
    if getattr(sys, 'frozen', False):
        candidates.insert(0, os.path.join(os.path.dirname(sys.executable), 'txdfix.dll'))
    for c in candidates:
        try:
            dll = ctypes.CDLL(c)
            dll.dxt_encode.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_void_p]
            dll.dxt_encode.restype = ctypes.c_int
            _TXDFIX = dll
            return dll
        except OSError:
            continue
    return None


def _encode_dxt_py(img, fmt):
    """img: PIL RGBA. Returns DXT payload bytes (pure-Python fallback)."""
    w, h = img.size
    data = img.tobytes()
    out = bytearray()
    bw, bh = (w + 3) // 4, (h + 3) // 4
    is_dxt1 = fmt == DXT1_FMT
    is_dxt3 = fmt == DXT3_FMT
    for by in range(bh):
        for bx in range(bw):
            px = []
            for py in range(4):
                yy = min(by * 4 + py, h - 1)
                for pxx in range(4):
                    xx = min(bx * 4 + pxx, w - 1)
                    o = (yy * w + xx) * 4
                    px.append((data[o], data[o + 1], data[o + 2], data[o + 3]))
            if is_dxt3:
                abits = 0
                for i in range(16):
                    abits |= (px[i][3] >> 4) << (4 * i)
                out += struct.pack("<Q", abits)
            elif not is_dxt1:
                alphas = [p[3] for p in px]
                a0, a1 = max(alphas), min(alphas)
                out += bytes((a0, a1))
                bits = 0
                if a0 > a1:
                    for i in range(16):
                        a = px[i][3]
                        if a == a0:
                            idx = 0
                        elif a == a1:
                            idx = 1
                        elif a > (a0 + a1) // 2:
                            idx = 2
                        else:
                            idx = 3
                        bits |= idx << (3 * i)
                out += struct.pack("<Q", bits)
            c0, c1, bits = _fit_dxt1_block(px)
            out += struct.pack("<HHI", c0, c1, bits)
    return bytes(out)


def _mip_chain(img, max_levels=None):
    """Magic.TXD-parity mip chain (txdread.common.hxx mipGenLevelGenerator):
    each dimension halves INDEPENDENTLY until it reaches 1 (generateToMinimum).
    max_levels caps the count (None = full chain)."""
    from PIL import Image
    yield img
    cur = img
    count = 1
    while (cur.width > 1 or cur.height > 1):
        if max_levels is not None and count >= max_levels:
            return
        nw = cur.width // 2 if cur.width > 1 else 1
        nh = cur.height // 2 if cur.height > 1 else 1
        cur = cur.resize((nw, nh), Image.BOX)
        count += 1
        yield cur


def encode_replace(tex, img):
    """Re-encode `tex` from a PIL image, keeping its format when supported."""
    from PIL import Image
    img = img.convert("RGBA")
    if img.size != (tex.width, tex.height):
        raise TxdError("size mismatch: %dx%d required, got %dx%d"
                       % (tex.width, tex.height, *img.size))
    rf = tex.raster_format & 0x0F00
    compressed = tex.flags & FLAG_COMPRESSED and \
        tex.d3d_format in (DXT1_FMT, DXT3_FMT, DXT5_FMT)
    if tex.flags & FLAG_COMPRESSED and not compressed:
        # unknown FourCC (e.g. PS2-origin 0x15): data is raw BGRA8888 —
        # normalize header so size math and decoders agree
        tex.flags &= ~FLAG_COMPRESSED
        tex.d3d_format = 0
        tex.depth = 32
        tex.palette = None
        tex.dirty = True
        rf = FMT_8888
        tex.raster_format = (tex.raster_format & ~0xFF00) | FMT_8888
    if compressed:
        encoder_fmt = tex.d3d_format
    elif rf in (FMT_8888, FMT_888, FMT_1555, FMT_565, FMT_4444, FMT_LUM8) or \
            tex.raster_format & (FMT_PAL8 | FMT_PAL4):
        encoder_fmt = None  # fall back to 8888 below for exotic formats
        if rf != FMT_8888:
            rf = FMT_8888
            tex.raster_format = (tex.raster_format & ~0xFF00) | FMT_8888
            tex.depth = 32
            tex.palette = None
    else:
        raise TxdError("cannot re-encode format 0x%04X" % tex.raster_format)
    mips = []
    for lvl in _mip_chain(img):
        if compressed:
            mips.append(_encode_dxt(lvl, encoder_fmt))
        else:
            mips.append(lvl.tobytes("raw", "BGRA"))
    tex.mips = mips
    tex.num_levels = len(mips)
    tex.flags |= FLAG_ALPHA if any(p[3] != 255 for p in img.getdata()) else tex.flags & FLAG_ALPHA
    tex.dirty = True


# ---------------------------------------------------------------- mip health
def expected_level_size(w, h, tex):
    """Byte size a mip level of w x h should occupy for this texture's format."""
    if tex.flags & FLAG_COMPRESSED:
        bw, bh = (w + 3) // 4, (h + 3) // 4
        bytes_per_block = 8 if tex.d3d_format == DXT1_FMT else 16
        return bw * bh * bytes_per_block
    rf = tex.raster_format & 0x0F00
    if tex.raster_format & FMT_PAL8:
        return w * h
    if tex.raster_format & FMT_PAL4:
        return (w * h + 1) // 2
    bpp = {FMT_8888: 4, FMT_888: 3, FMT_1555: 2, FMT_4444: 2,
           FMT_565: 2, FMT_LUM8: 1}.get(rf, 4)
    return w * h * bpp


def mip_issues(tex, strict=True):
    """Return issue strings for one texture ([] = healthy).
    strict=False: missing-mips reported as optimization potential, not an issue."""
    issues = []
    exp_levels = max(1, max(tex.width, tex.height).bit_length())
    if strict and tex.width >= 8 and tex.num_levels < exp_levels:
        issues.append('missing mips (%d/%d)' % (tex.num_levels, exp_levels))
    for i, m in enumerate(tex.mips):
        w = max(1, tex.width >> i)
        h = max(1, tex.height >> i)
        exp = expected_level_size(w, h, tex)
        if len(m) != exp:
            issues.append('level %d corrupt (size %d != %d)' % (i, len(m), exp))
            break
    return issues


def fix_texture_mips(tex, conservative=True):
    """Regenerate the mip chain from the top level.

    conservative=True (safe default): keep the ORIGINAL level count and never
    touch header fields — only fills in missing levels the game would want.
    conservative=False: full chain to 1x1 + MIPMAP flag rewrite (aggressive).
    """
    img = decode_mip(tex, 0)
    from PIL import Image
    if conservative:
        target = max(1, tex.num_levels)
        chain = []
        cur = img
        for _ in range(target):
            chain.append(cur)
            if cur.width == 1 and cur.height == 1:
                break
            cur = cur.resize((max(1, cur.width // 2), max(1, cur.height // 2)),
                             Image.BOX)
        tex.mips = [_encode_dxt(lvl, tex.d3d_format)
                    if tex.flags & FLAG_COMPRESSED and
                    tex.d3d_format in (DXT1_FMT, DXT3_FMT, DXT5_FMT)
                    else lvl.tobytes('raw', 'BGRA') for lvl in chain]
        tex.num_levels = len(tex.mips)
    else:
        encode_replace(tex, img)
        tex.raster_format |= FMT_MIPMAP
    tex.dirty = True


# ---------------------------------------------------------------- RW version
# libraryID stamp packing (gtamods wiki): version 0xVJNBB, build 0xFFFF ->
# stamp = ((V<<3|J)<<4|N)<<6|BB packed as VVJJJJNN NNBBBBBB + build<<16, minus 0x30000 pre-shift
KNOWN_VERSIONS = [
    ("GTA San Andreas (3.6.0.3)", 0x6003FFFF),
    ("GTA Vice City (3.4.0.3)", 0x4003FFFF),
    ("GTA Vice City (3.3.0.2)", 0x3002FFFF),
    ("GTA III (3.1.0.1)", 0x1001FFFF),
    ("GTA III (3.4.0.3)", 0x4003FFFF),
    ("Manhunt (3.6.0.3)", 0x6003FFFF),
    ("Bully (3.7.0.2)", 0x7002FFFF),
]


def version_decode(stamp):
    """libraryID stamp -> (version_str, build). Layout: packed=(v-0x30000)<<16 | build.
    v = V.J.N.BB packed as (V<<16)|(J<<12)|(N<<8)|BB."""
    if not stamp or stamp == 0xFFFFFFFF:
        return ("unknown", 0)
    packed = (stamp >> 16) & 0xFFFF
    build = stamp & 0xFFFF
    v = packed + 0x30000
    ver = "%x.%x.%x.%x" % ((v >> 16) & 0xF, (v >> 12) & 0xF,
                           (v >> 8) & 0xF, v & 0xFF)
    return (ver, build)


def version_encode(ver_str, build=0xFFFF):
    parts = [int(p, 16) for p in ver_str.split('.')]
    while len(parts) < 4:
        parts.append(0)
    v = (parts[0] << 16) | (parts[1] << 12) | (parts[2] << 8) | (parts[3] & 0xFF)
    packed = v - 0x30000
    return ((packed & 0xFFFF) << 16) | (build & 0xFFFF)


def version_friendly(stamp):
    for name, s in KNOWN_VERSIONS:
        if s == stamp:
            return name
    ver, build = version_decode(stamp)
    return "RW %s (build %04X)" % (ver, build)


# ---------------------------------------------------------------- model
class TxdTexture(object):
    __slots__ = ("platform", "filter_addressing", "name", "mask", "raster_format",
                 "d3d_format", "width", "height", "depth", "num_levels", "rtype",
                 "flags", "palette", "mips", "raw_payload", "dirty")

    def __init__(self):
        self.raw_payload = None
        self.dirty = False
        self.palette = None
        self.mips = []

    @property
    def compressed(self):
        return bool(self.flags & FLAG_COMPRESSED)

    def fmt_name(self):
        if self.compressed:
            return {DXT1_FMT: "DXT1", DXT3_FMT: "DXT3", DXT5_FMT: "DXT5"}.get(
                self.d3d_format, "DXT?0x%08X" % self.d3d_format)
        return {FMT_1555: "1555", FMT_565: "565", FMT_4444: "4444",
                FMT_LUM8: "LUM8", FMT_8888: "8888", FMT_888: "888"}.get(
                    self.raster_format & 0x0F00,
                    "PAL8" if self.raster_format & FMT_PAL8 else
                    "PAL4" if self.raster_format & FMT_PAL4 else
                    "0x%04X" % (self.raster_format & 0x0F00))

    def _serialize(self, version):
        if not self.dirty and self.raw_payload is not None:
            return struct.pack("<III", ID_TEXTURENATIVE, len(self.raw_payload), version) \
                + self.raw_payload
        hdr = struct.pack("<II32s32siiHHBBBB",
                          self.platform, self.filter_addressing,
                          self.name.encode("ascii", "ignore")[:32].ljust(32, b"\0"),
                          self.mask.encode("ascii", "ignore")[:32].ljust(32, b"\0"),
                          self.raster_format, self.d3d_format,
                          self.width, self.height, self.depth, self.num_levels,
                          self.rtype, self.flags)
        body = bytearray(hdr)
        if self.raster_format & FMT_PAL8:
            body += self.palette or bytes(1024)
        elif self.raster_format & FMT_PAL4:
            body += self.palette or bytes(128)
        for m in self.mips:
            body += struct.pack("<I", len(m)) + m
        payload = struct.pack("<III", ID_STRUCT, len(body), version) + bytes(body)
        return struct.pack("<III", ID_TEXTURENATIVE, len(payload), version) + payload


class TxdFile(object):
    def __init__(self):
        self.textures = []
        self.dict_struct_raw = b"\x00\x00\x00\x00"
        self.inner_tail = b""    # unknown chunks inside the declared TXD range
        self.outer_tail = b""    # bytes beyond declared end (IMG sector padding)
        self.version = 0x1803FFFF
        self.path = None

    # ---- reading
    @classmethod
    def load(cls, path):
        with open(path, "rb") as fh:
            return cls.loads(fh.read(), path=path)

    @classmethod
    def loads(cls, buf, path=None):
        self = cls()
        self.path = path
        pos = 0
        cid, csize, cver = struct.unpack_from("<III", buf, pos)
        if cid != ID_TEXDICTIONARY:
            raise TxdError("not a TXD (top chunk id 0x%X)" % cid)
        self.version = cver
        end = min(len(buf), pos + 12 + csize)
        pos += 12
        # first child must be STRUCT
        sid, ssize, sver = struct.unpack_from("<III", buf, pos)
        if sid != ID_STRUCT:
            raise TxdError("TXD: expected STRUCT, got 0x%X" % sid)
        self.dict_struct_raw = buf[pos + 12:pos + 12 + ssize]
        pos += 12 + ssize
        while pos + 12 <= end:
            tid, tsize, tver = struct.unpack_from("<III", buf, pos)
            if tid != ID_TEXTURENATIVE:
                # unknown chunk inside the dictionary: keep raw, counts to size
                self.inner_tail += buf[pos:end]
                break
            payload = buf[pos + 12:min(len(buf), pos + 12 + tsize)]
            self.textures.append(self._parse_texture(payload, tver))
            pos += 12 + tsize
        if end < len(buf):
            # trailing padding / extra data beyond declared chunk (IMG sector
            # alignment): preserve byte-exact, NOT counted into the TXD size
            self.outer_tail += buf[end:]
        return self

    @staticmethod
    def _parse_texture(payload, version):
        tex = TxdTexture()
        tex.raw_payload = payload
        pid, psize, pver = struct.unpack_from("<III", payload, 0)
        if pid != ID_STRUCT:
            raise TxdError("texture: expected STRUCT, got 0x%X" % pid)
        body = payload[12:12 + psize]
        (tex.platform, tex.filter_addressing, name_b, mask_b,
         tex.raster_format, tex.d3d_format, tex.width, tex.height,
         tex.depth, nl, tex.rtype, tex.flags) = struct.unpack_from("<II32s32siiHHBBBB", body, 0)
        tex.name = name_b.split(b"\0")[0].decode("ascii", "ignore").lower()
        tex.mask = mask_b.split(b"\0")[0].decode("ascii", "ignore").lower()
        tex.num_levels = nl
        off = 88
        if tex.raster_format & FMT_PAL8:
            tex.palette = body[off:off + 1024]
            off += 1024
        elif tex.raster_format & FMT_PAL4:
            tex.palette = body[off:off + 128]
            off += 128
        tex.mips = []
        for _ in range(nl):
            (msize,) = struct.unpack_from("<I", body, off)
            off += 4
            tex.mips.append(body[off:off + msize])
            off += msize
        return tex

    # ---- writing
    def save(self, path):
        body = bytearray(struct.pack("<III", ID_STRUCT, len(self.dict_struct_raw),
                                     self.version) + self.dict_struct_raw)
        for tex in self.textures:
            body += tex._serialize(self.version)
        body += self.inner_tail
        # patch texture count (first i16 of dict struct, right after 12B header)
        cnt = struct.pack("<h", len(self.textures))
        body = body[:12] + cnt + body[14:]
        out = struct.pack("<III", ID_TEXDICTIONARY, len(body), self.version) + bytes(body)
        out += self.outer_tail
        with open(path, "wb") as fh:
            fh.write(out)
        self.path = path

    # ---- helpers
    def get(self, name):
        name = name.lower()
        for t in self.textures:
            if t.name == name:
                return t
        return None

    def replace(self, name, pil_image):
        tex = self.get(name)
        if tex is None:
            raise TxdError("texture '%s' not found" % name)
        encode_replace(tex, pil_image)
        tex.dirty = True
        return tex

    # ---- Magic.TXD-style structure ops -------------------------------------
    @classmethod
    def create(cls, path=None):
        self = cls()
        self.dict_struct_raw = struct.pack("<hh", 0, 0)  # numTex=0, device=0
        self.path = path
        return self

    def add_texture(self, pil_image, name, fmt="auto"):
        """Create a texture from a PIL image. fmt: auto|8888|DXT1|DXT3|DXT5."""
        from PIL import Image
        img = pil_image.convert("RGBA")
        if img.width & (img.width - 1) or img.height & (img.height - 1):
            raise TxdError("dimensions must be power-of-two (%dx%d)" % img.size)
        if self.get(name):
            raise TxdError("texture '%s' already exists" % name)
        has_alpha = any(p[3] != 255 for p in img.getdata())
        if fmt == "auto":
            fmt = "DXT5" if has_alpha else "DXT1"
        tex = TxdTexture()
        tex.platform = 9
        tex.filter_addressing = 0x6  # LINEARMIPLINEAR, wrap/wrap
        tex.name = name.lower()[:31]
        tex.mask = ""
        tex.width, tex.height = img.size
        tex.rtype = 0x04
        tex.raster_format = FMT_8888  # provisional; finalized after encode
        if fmt in ("DXT1", "DXT3", "DXT5"):
            tex.flags = FLAG_COMPRESSED | (FLAG_ALPHA if has_alpha else 0)
            tex.d3d_format = {"DXT1": DXT1_FMT, "DXT3": DXT3_FMT, "DXT5": DXT5_FMT}[fmt]
            tex.depth = 24 if fmt == "DXT1" else 32
        elif fmt == "8888":
            tex.flags = FLAG_ALPHA if has_alpha else 0
            tex.d3d_format = 0
            tex.depth = 32
        else:
            raise TxdError("unsupported target format %r" % fmt)
        encode_replace(tex, img)
        tex.raster_format = (FMT_MIPMAP if tex.num_levels > 1 else 0) | \
            (0 if tex.compressed else FMT_8888)
        tex.dirty = True
        self.textures.append(tex)
        return tex

    def remove_texture(self, name):
        tex = self.get(name)
        if tex is None:
            raise TxdError("texture '%s' not found" % name)
        self.textures.remove(tex)
        return tex

    def duplicate_texture(self, name, new_name):
        import copy
        src = self.get(name)
        if src is None:
            raise TxdError("texture '%s' not found" % name)
        if self.get(new_name):
            raise TxdError("texture '%s' already exists" % new_name)
        dst = copy.copy(src)
        dst.mips = list(src.mips)
        dst.name = new_name.lower()[:31]
        dst.dirty = True
        self.textures.append(dst)
        return dst


# ---- per-texture edits (Magic.TXD properties panel) ------------------------
def texture_rename(tex, new_name):
    tex.name = new_name.strip().lower()[:31]
    tex.dirty = True


def texture_set_mask(tex, new_mask):
    tex.mask = new_mask.strip().lower()[:31]
    tex.dirty = True


def texture_set_filter_addressing(tex, value):
    tex.filter_addressing = value & 0xFFFF
    tex.dirty = True


def texture_remove_mips(tex):
    if not tex.mips:
        return
    tex.mips = [tex.mips[0]]
    tex.num_levels = 1
    tex.raster_format &= ~FMT_MIPMAP
    tex.flags &= ~FLAG_AUTOMIP
    tex.dirty = True


def texture_generate_mips(tex):
    """Re-encode from decoded top level, regenerating the full chain."""
    from PIL import Image
    img = decode_mip(tex, 0)
    encode_replace(tex, img)
    tex.raster_format |= FMT_MIPMAP
    tex.dirty = True


def texture_resize(tex, new_w, new_h):
    """Scale texture to new power-of-two dimensions and re-encode."""
    if new_w & (new_w - 1) or new_h & (new_h - 1) or new_w < 1 or new_h < 1:
        raise TxdError("dimensions must be power-of-two (%dx%d)" % (new_w, new_h))
    from PIL import Image
    img = decode_mip(tex, 0).resize((new_w, new_h), Image.LANCZOS)
    tex.width, tex.height = new_w, new_h
    encode_replace(tex, img)
    tex.dirty = True


def texture_convert(tex, target):
    """Convert format. target: 8888|DXT1|DXT3|DXT5."""
    img = decode_mip(tex, 0)
    if target == "8888":
        tex.raster_format = (tex.raster_format & ~0xFF00) | FMT_8888
        tex.flags &= ~FLAG_COMPRESSED
        tex.d3d_format = 0
        tex.depth = 32
        tex.palette = None
    else:
        fourcc = {"DXT1": DXT1_FMT, "DXT3": DXT3_FMT, "DXT5": DXT5_FMT}[target]
        tex.flags |= FLAG_COMPRESSED
        tex.d3d_format = fourcc
        tex.depth = 24 if target == "DXT1" else 32
        tex.raster_format &= ~0xFF00  # compressed rasters carry no Cxxx bits
        tex.palette = None
    encode_replace(tex, img)
    tex.dirty = True

    def summary(self):
        return ["%-24s %4dx%-4d %-5s mips=%d%s" %
                (t.name, t.width, t.height, t.fmt_name(), t.num_levels,
                 "  alpha" if t.flags & FLAG_ALPHA else "")
                for t in self.textures]


def _fix_one(args):
    """Worker: backup -> fix -> save one TXD. Returns (path, status)."""
    path, bdir = args
    p = Path(path)
    try:
        Path(bdir).mkdir(parents=True, exist_ok=True)
        (Path(bdir) / p.name).write_bytes(p.read_bytes())
    except OSError:
        return (str(p), 'backup_failed')
    try:
        txd = TxdFile.load(str(p))
    except Exception:
        return (str(p), 'corrupt')
    changed = False
    for t in txd.textures:
        if mip_issues(t):
            try:
                fix_texture_mips(t)
                changed = True
            except Exception:
                pass
    if not changed:
        (Path(bdir) / p.name).unlink(missing_ok=True)
        return (str(p), 'clean')
    try:
        txd.save(str(p))
        return (str(p), 'fixed')
    except Exception:
        return (str(p), 'save_failed')


def batch_fix(roots, bdir, workers=None, progress=None):
    """Scan roots for TXDs with mip issues, fix them in parallel.
    roots: iterable of dir paths. Returns (fixed, failed, scanned).
    Files inside fake-IMG dirs (a folder named like an .img) are override-
    critical and are NEVER modified — the game's RW loader is stricter about
    those than our spec-level validation (learned 2026-08-26)."""
    from multiprocessing import Pool
    from pathlib import Path
    bdir = str(Path(bdir).resolve())   # workers have different cwd

    def is_fakeimg(p):
        return any(part.lower().endswith('.img') for part in p.parts[:-1])

    targets = []
    scanned = 0
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        for p in root.rglob('*.txd'):
            scanned += 1
            if is_fakeimg(p):
                continue  # override-critical: skip entirely
            try:
                txd = TxdFile.load(str(p))
                if any(mip_issues(t) for t in txd.textures):
                    targets.append((str(p), str(bdir)))
            except Exception:
                targets.append((str(p), str(bdir)))
    if not targets:
        return (0, 0, scanned)
    fixed = failed = 0
    with Pool(workers) as pool:
        for i, (path, status) in enumerate(
                pool.imap_unordered(_fix_one, targets, chunksize=4)):
            if status == 'fixed':
                fixed += 1
            elif status != 'clean':
                failed += 1
            if progress:
                progress(i + 1, len(targets))
    return (fixed, failed, scanned)


# ---------------------------------------------------------------- cli
def _cli(argv):
    if len(argv) < 3:
        print("usage: txdlite.py info|export|replace|verify <txd> [args]")
        return 2
    cmd, path = argv[1], argv[2]
    txd = TxdFile.load(path)
    if cmd == "info":
        print("\n".join(txd.summary()) or "(empty)")
    elif cmd == "export":
        name, png = argv[3], argv[4]
        decode_mip(txd.get(name)).save(png)
        print("exported", name, "->", png)
    elif cmd == "replace":
        name, png, out = argv[3], argv[4], argv[5]
        from PIL import Image
        txd.replace(name, Image.open(png))
        txd.save(out)
        print("replaced", name, "->", out)
    elif cmd == "verify":
        import io
        bio = io.BytesIO()
        txd.save(path + ".roundtrip.tmp")
        orig = open(path, "rb").read()
        new = open(path + ".roundtrip.tmp", "rb").read()
        os.remove(path + ".roundtrip.tmp")
        print("ROUNDTRIP_OK" if orig == new else
              "ROUNDTRIP_DIFF (orig=%d new=%d)" % (len(orig), len(new)))
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
