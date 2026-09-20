/* RAN0 1-way word-rANS decode — fair C baseline for M2 native timings. */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "rans_word.h"

int ran0_peek(const uint8_t *blob, uint32_t blob_len, uint32_t *orig_out) {
    uint32_t orig_len;
    if (blob_len < 9u + 512u) {
        return -1;
    }
    if (blob[0] != 'R' || blob[1] != 'A' || blob[2] != 'N' || blob[3] != '0') {
        return -2;
    }
    orig_len = read_u32_le(blob + 4);
    if (orig_out) {
        *orig_out = orig_len;
    }
    return 0;
}

int ran0_decode(const uint8_t *blob, uint32_t blob_len, uint8_t *out) {
    uint32_t orig_len, scale_bits, i, mask;
    const uint16_t *freqs;
    const uint8_t *payload;
    uint32_t payload_len;
    uint32_t *cdf = NULL;
    uint8_t *lut = NULL;
    RansSrc src;
    uint32_t x;
    int rc = 0;

    if (blob_len < 9u + 512u) {
        return -1;
    }
    if (blob[0] != 'R' || blob[1] != 'A' || blob[2] != 'N' || blob[3] != '0') {
        return -2;
    }
    orig_len = read_u32_le(blob + 4);
    scale_bits = blob[8];
    if (scale_bits > 16u) {
        return -3;
    }
    if (orig_len == 0) {
        return 0;
    }
    if (out == NULL) {
        return -4;
    }
    freqs = (const uint16_t *)(blob + 9);
    payload = blob + 9u + 512u;
    payload_len = blob_len - (9u + 512u);

    cdf = (uint32_t *)malloc(256 * sizeof(uint32_t));
    lut = (uint8_t *)malloc(1u << scale_bits);
    if (cdf == NULL || lut == NULL) {
        rc = -5;
        goto done;
    }
    if (rans_build_tables(freqs, scale_bits, cdf, lut) != 0) {
        rc = -6;
        goto done;
    }
    src.data = payload;
    src.len = payload_len;
    src.ptr = 0;
    if (rans_dec_init(&src, &x) != 0) {
        rc = -7;
        goto done;
    }
    mask = (1u << scale_bits) - 1u;
    for (i = 0; i < orig_len; i++) {
        uint8_t sym = lut[x & mask];
        out[i] = sym;
        if (rans_dec_advance(x, cdf[sym], freqs[sym], scale_bits, &src, &x) != 0) {
            rc = -8;
            goto done;
        }
    }

done:
    free(cdf);
    free(lut);
    return rc;
}
