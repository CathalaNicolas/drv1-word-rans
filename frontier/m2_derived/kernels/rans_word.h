/* Shared word-rANS decode helpers for ILR0 / CHK0 baselines.
 * Matches rans/core.py: RANS_L=2^16, u16 refill, lo|hi init. */
#ifndef BASELINES_RANS_WORD_H
#define BASELINES_RANS_WORD_H

#include <stdint.h>
#include <string.h>

#define RANS_L (1u << 16)

typedef struct {
    const uint8_t *data;
    uint32_t len;
    uint32_t ptr;
} RansSrc;

static inline int rans_read_u16(RansSrc *src, uint32_t *out) {
    if (src->ptr + 2 > src->len) {
        return -1;
    }
    *out = (uint32_t)src->data[src->ptr]
        | ((uint32_t)src->data[src->ptr + 1] << 8);
    src->ptr += 2;
    return 0;
}

static inline int rans_dec_init(RansSrc *src, uint32_t *x) {
    uint32_t lo, hi;
    if (rans_read_u16(src, &lo) != 0) {
        return -1;
    }
    if (rans_read_u16(src, &hi) != 0) {
        return -1;
    }
    *x = lo | (hi << 16);
    return 0;
}

static inline int rans_dec_advance(
    uint32_t x,
    uint32_t start,
    uint32_t freq,
    uint32_t scale_bits,
    RansSrc *src,
    uint32_t *x_out
) {
    uint32_t mask = (1u << scale_bits) - 1u;
    x = freq * (x >> scale_bits) + (x & mask) - start;
    while (x < RANS_L) {
        uint32_t w;
        if (rans_read_u16(src, &w) != 0) {
            return -1;
        }
        x = (x << 16) | w;
    }
    *x_out = x;
    return 0;
}

/* cdf[256] + lut[1<<scale_bits] from wire freqs. 0 ok; -1 bad scale; -2 sum. */
static inline int rans_build_tables(
    const uint16_t *freqs,
    uint32_t scale_bits,
    uint32_t *cdf,
    uint8_t *lut
) {
    uint32_t m, acc = 0, s, f, k;
    if (scale_bits > 16) {
        return -1;
    }
    m = 1u << scale_bits;
    for (s = 0; s < 256; s++) {
        cdf[s] = acc;
        f = freqs[s];
        for (k = 0; k < f; k++) {
            lut[acc + k] = (uint8_t)s;
        }
        acc += f;
    }
    return acc == m ? 0 : -2;
}

static inline uint32_t read_u32_le(const uint8_t *p) {
    return (uint32_t)p[0]
        | ((uint32_t)p[1] << 8)
        | ((uint32_t)p[2] << 16)
        | ((uint32_t)p[3] << 24);
}

static inline uint16_t read_u16_le(const uint8_t *p) {
    return (uint16_t)((uint32_t)p[0] | ((uint32_t)p[1] << 8));
}

#endif /* BASELINES_RANS_WORD_H */
