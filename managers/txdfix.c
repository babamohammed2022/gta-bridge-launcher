/* txdfix.c — DXT1/DXT3/DXT5 block encoder core for txdlite.
 * Build (VS2022): cl /O2 /LD txdfix.c /Fe:txdfix.dll
 * ABI: single entry point, operates on whole mip buffers.
 */
#include <stdint.h>
#include <string.h>

static inline void rgb_to_565(int r, int g, int b, uint16_t *out) {
    *out = (uint16_t)(((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3));
}

static inline void unpack565(uint16_t c, int *rgb) {
    int r5 = (c >> 11) & 31, g6 = (c >> 5) & 63, b5 = c & 31;
    rgb[0] = (r5 << 3) | (r5 >> 2);
    rgb[1] = (g6 << 2) | (g6 >> 4);
    rgb[2] = (b5 << 3) | (b5 >> 2);
}

/* Decode one DXT block into 16 RGBA pixels. fmt: 1/3/5. */
static void decode_dxt_block(const uint8_t *in, int fmt, uint8_t *out16) {
    const uint8_t *op = in;
    int a[16];
    if (fmt == 3) {
        for (int i = 0; i < 16; i++) {
            uint8_t nib = (i & 1) ? (op[i >> 1] & 0xF) : (op[i >> 1] >> 4);
            a[i] = (nib << 4) | nib;
        }
        op += 8;
    } else if (fmt == 5) {
        int a0 = op[0], a1 = op[1];
        uint64_t bits = 0;
        memcpy(&bits, op + 2, 6);
        int pal[8];
        pal[0] = a0; pal[1] = a1;
        if (a0 > a1) {
            for (int i = 0; i < 6; i++) pal[2 + i] = ((6 - i) * a0 + (i + 1) * a1) / 7;
            pal[7] = 255;
        } else {
            pal[2] = (4 * a0 + a1) / 5; pal[3] = (3 * a0 + 2 * a1) / 5;
            pal[4] = (2 * a0 + 3 * a1) / 5; pal[5] = (a0 + 4 * a1) / 5;
            pal[6] = 0; pal[7] = 255;
        }
        for (int i = 0; i < 16; i++) a[i] = pal[(bits >> (3 * i)) & 7];
        op += 8;
    }
    uint16_t c0, c1;
    memcpy(&c0, op, 2); memcpy(&c1, op + 2, 2);
    uint32_t cbits;
    memcpy(&cbits, op + 4, 4);
    int p0[3], p1[3], pal[4][3];
    unpack565(c0, p0);
    unpack565(c1, p1);
    for (int k = 0; k < 3; k++) {
        pal[0][k] = p0[k]; pal[1][k] = p1[k];
        if (c0 > c1) {
            pal[2][k] = (2 * p0[k] + p1[k]) / 3;
            pal[3][k] = (p0[k] + 2 * p1[k]) / 3;
        } else {
            pal[2][k] = (p0[k] + p1[k]) / 2;
            pal[3][k] = 0;
        }
    }
    for (int i = 0; i < 16; i++) {
        int idx = (cbits >> (2 * i)) & 3;
        uint8_t *o = out16 + i * 4;
        o[0] = (uint8_t)pal[idx][0];
        o[1] = (uint8_t)pal[idx][1];
        o[2] = (uint8_t)pal[idx][2];
        o[3] = (fmt == 1) ? ((idx == 3 && c0 <= c1) ? 0 : 255)
                          : (uint8_t)a[i];
    }
}

/* Decode DXT data (w x h) to RGBA. fmt: 1/3/5. Returns bytes written. */
__declspec(dllexport)
int dxt_decode(const uint8_t *data, int w, int h, int fmt, uint8_t *out) {
    int bw = (w + 3) / 4, bh = (h + 3) / 4;
    const uint8_t *ip = data;
    int is_dxt1 = (fmt == 1);
    for (int by = 0; by < bh; by++) {
        for (int bx = 0; bx < bw; bx++) {
            uint8_t blk[16 * 4];
            if (fmt == 3) ip += 8;
            else if (!is_dxt1) ip += 8;
            /* re-read: block layout is alpha(8 for dxt3/5) then color(8) */
            const uint8_t *start = ip - ((fmt == 3 || !is_dxt1) ? 8 : 0);
            decode_dxt_block(start, fmt, blk);
            ip = start + ((fmt == 1) ? 8 : 16);
            for (int py = 0; py < 4; py++) {
                int yy = by * 4 + py;
                if (yy >= h) break;
                for (int pxx = 0; pxx < 4; pxx++) {
                    int xx = bx * 4 + pxx;
                    if (xx >= w) break;
                    memcpy(out + (yy * w + xx) * 4, blk + (py * 4 + pxx) * 4, 4);
                }
            }
        }
    }
    return w * h * 4;
}

/* Swizzle BGRA <-> RGBA in place. */
__declspec(dllexport)
void bgra_swap(uint8_t *buf, int n_pixels) {
    for (int i = 0; i < n_pixels; i++) {
        uint8_t t = buf[i * 4];
        buf[i * 4] = buf[i * 4 + 2];
        buf[i * 4 + 2] = t;
    }
}

/* Fit one 4x4 RGBA block to DXT1 (opaque 4-color mode, c0 > c1 enforced). */
static void fit_dxt1_block(const uint8_t *px, uint16_t *c0_out, uint16_t *c1_out,
                           uint32_t *bits) {
    int lo[3] = {255, 255, 255}, hi[3] = {0, 0, 0};
    for (int i = 0; i < 16; i++) {
        const uint8_t *p = px + i * 4;
        for (int k = 0; k < 3; k++) {
            int v = p[k];
            if (v < lo[k]) lo[k] = v;
            if (v > hi[k]) hi[k] = v;
        }
    }
    uint16_t c0, c1;
    rgb_to_565(hi[0], hi[1], hi[2], &c0);
    rgb_to_565(lo[0], lo[1], lo[2], &c1);
    if (c0 == c1) c1 = c0 ^ 1;
    if (c0 < c1) { uint16_t t = c0; c0 = c1; c1 = t; }
    int p0[3], p1[3], pal[4][3];
    unpack565(c0, p0);
    unpack565(c1, p1);
    for (int k = 0; k < 3; k++) {
        pal[0][k] = p0[k];
        pal[1][k] = p1[k];
        pal[2][k] = (2 * p0[k] + p1[k]) / 3;
        pal[3][k] = (p0[k] + 2 * p1[k]) / 3;
    }
    uint32_t b = 0;
    for (int i = 0; i < 16; i++) {
        const uint8_t *p = px + i * 4;
        int best = 0, bd = 1 << 30;
        for (int j = 0; j < 4; j++) {
            int dr = pal[j][0] - p[0], dg = pal[j][1] - p[1], db = pal[j][2] - p[2];
            int d = dr * dr + dg * dg + db * db;
            if (d < bd) { bd = d; best = j; }
        }
        b |= (uint32_t)best << (2 * i);
    }
    *c0_out = c0;
    *c1_out = c1;
    *bits = b;
}

/* img: RGBA (w*h*4). out: DXT buffer. fmt: 1=DXT1, 3=DXT3, 5=DXT5.
 * Returns bytes written. */
__declspec(dllexport)
int dxt_encode(const uint8_t *img, int w, int h, int fmt, uint8_t *out) {
    uint8_t *op = out;
    int bw = (w + 3) / 4, bh = (h + 3) / 4;
    for (int by = 0; by < bh; by++) {
        for (int bx = 0; bx < bw; bx++) {
            uint8_t px[16 * 4];
            for (int py = 0; py < 4; py++) {
                int yy = by * 4 + py; if (yy >= h) yy = h - 1;
                for (int pxx = 0; pxx < 4; pxx++) {
                    int xx = bx * 4 + pxx; if (xx >= w) xx = w - 1;
                    memcpy(px + (py * 4 + pxx) * 4, img + (yy * w + xx) * 4, 4);
                }
            }
            if (fmt == 3) {                      /* DXT3: explicit 4-bit alpha */
                uint64_t ab = 0;
                for (int i = 0; i < 16; i++)
                    ab |= (uint64_t)(px[i * 4 + 3] >> 4) << (4 * i);
                memcpy(op, &ab, 8); op += 8;
            } else if (fmt == 5) {               /* DXT5: interpolated alpha */
                int a0 = 0, a1 = 255;
                for (int i = 0; i < 16; i++) {
                    int a = px[i * 4 + 3];
                    if (a > a0) a0 = a;
                    if (a < a1) a1 = a;
                }
                uint64_t ab = 0;
                if (a0 > a1) {
                    int apal[8];
                    apal[0] = a0; apal[1] = a1;
                    for (int i = 0; i < 6; i++) apal[2 + i] = ((6 - i) * a0 + (i + 1) * a1) / 7;
                    for (int i = 0; i < 16; i++) {
                        int a = px[i * 4 + 3], idx = 0, bd = 1 << 30;
                        for (int j = 0; j < 8; j++) {
                            int d = apal[j] - a; if (d < 0) d = -d;
                            if (d < bd) { bd = d; idx = j; }
                        }
                        ab |= (uint64_t)idx << (3 * i);
                    }
                }                                /* a0<=a1: all idx 0 = a0 */
                /* alpha block = a0(1) + a1(1) + 48-bit index (6 bytes) = 8B */
                *op++ = (uint8_t)a0; *op++ = (uint8_t)a1;
                memcpy(op, &ab, 6); op += 6;
            }
            uint16_t c0, c1; uint32_t bits;
            fit_dxt1_block(px, &c0, &c1, &bits);
            memcpy(op, &c0, 2); op += 2;
            memcpy(op, &c1, 2); op += 2;
            memcpy(op, &bits, 4); op += 4;
        }
    }
    return (int)(op - out);
}
