/* DRV1 sequential + partitioned decode (M2). Word-rANS via rans_word.h */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#if defined(_OPENMP)
#include <omp.h>
#endif

#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#endif

#include "rans_word.h"
#include "m2_blob.h"

#define DRV1_MAGIC_0 'D'
#define DRV1_MAGIC_1 'R'
#define DRV1_MAGIC_2 'V'
#define DRV1_MAGIC_3 '1'
#define KEY_SIZE 12u

static double m2_now_s(void) {
#if defined(_WIN32)
    static LARGE_INTEGER freq;
    static int init;
    LARGE_INTEGER t;
    if (!init) {
        QueryPerformanceFrequency(&freq);
        init = 1;
    }
    QueryPerformanceCounter(&t);
    return (double)t.QuadPart / (double)freq.QuadPart;
#elif defined(_OPENMP)
    return omp_get_wtime();
#else
    return 0.0;
#endif
}

typedef struct {
    uint32_t symbol_index;
    uint32_t byte_offset;
    uint32_t state;
} M2Key;

typedef struct {
    uint32_t orig_len;
    uint32_t scale_bits;
    uint32_t n_keys;
    const uint16_t *freqs;
    const uint8_t *payload;
    uint32_t payload_len;
    const uint8_t *keys_raw; /* n_keys * 12 */
} M2View;

static int m2_parse(const uint8_t *blob, uint32_t blob_len, M2View *v) {
    uint32_t ptr, payload_len, need;
    if (blob_len < 12u + 512u + 4u) {
        return -1;
    }
    if (blob[0] != DRV1_MAGIC_0 || blob[1] != DRV1_MAGIC_1
        || blob[2] != DRV1_MAGIC_2 || blob[3] != DRV1_MAGIC_3) {
        return -2;
    }
    v->orig_len = read_u32_le(blob + 4);
    v->scale_bits = blob[8];
    v->n_keys = read_u16_le(blob + 9);
    /* pad at blob[11] */
    if (v->n_keys < 1u || v->scale_bits > 16u) {
        return -3;
    }
    ptr = 12;
    v->freqs = (const uint16_t *)(blob + ptr);
    ptr += 512;
    payload_len = read_u32_le(blob + ptr);
    ptr += 4;
    if (ptr + payload_len < ptr) {
        return -4;
    }
    need = ptr + payload_len + v->n_keys * KEY_SIZE;
    if (need != blob_len) {
        return -5;
    }
    v->payload = blob + ptr;
    v->payload_len = payload_len;
    v->keys_raw = blob + ptr + payload_len;
    return 0;
}

static M2Key key_at(const M2View *v, uint32_t i) {
    M2Key k;
    const uint8_t *p = v->keys_raw + i * KEY_SIZE;
    k.symbol_index = read_u32_le(p);
    k.byte_offset = read_u32_le(p + 4);
    k.state = read_u32_le(p + 8);
    return k;
}

int m2_peek(const uint8_t *blob, uint32_t blob_len, uint32_t *orig_out) {
    M2View v;
    int rc = m2_parse(blob, blob_len, &v);
    if (rc != 0) {
        return rc;
    }
    if (orig_out) {
        *orig_out = v.orig_len;
    }
    return 0;
}

int m2_decode(const uint8_t *blob, uint32_t blob_len, uint8_t *out) {
    M2View v;
    uint32_t *cdf = NULL;
    uint8_t *lut = NULL;
    RansSrc src;
    uint32_t x, mask, i;
    int rc;

    rc = m2_parse(blob, blob_len, &v);
    if (rc != 0) {
        return rc;
    }
    if (v.orig_len == 0) {
        return 0;
    }
    if (out == NULL) {
        return -6;
    }
    cdf = (uint32_t *)malloc(256 * sizeof(uint32_t));
    lut = (uint8_t *)malloc(1u << v.scale_bits);
    if (cdf == NULL || lut == NULL) {
        free(cdf);
        free(lut);
        return -7;
    }
    if (rans_build_tables(v.freqs, v.scale_bits, cdf, lut) != 0) {
        free(cdf);
        free(lut);
        return -8;
    }
    src.data = v.payload;
    src.len = v.payload_len;
    src.ptr = 0;
    if (rans_dec_init(&src, &x) != 0) {
        free(cdf);
        free(lut);
        return -9;
    }
    mask = (1u << v.scale_bits) - 1u;
    for (i = 0; i < v.orig_len; i++) {
        uint8_t sym = lut[x & mask];
        out[i] = sym;
        if (rans_dec_advance(x, cdf[sym], v.freqs[sym], v.scale_bits, &src, &x)
            != 0) {
            free(cdf);
            free(lut);
            return -10;
        }
    }
    free(cdf);
    free(lut);
    return 0;
}

int m2_decode_parallel(
    const uint8_t *blob,
    uint32_t blob_len,
    uint32_t n_parts,
    uint8_t *out
) {
    return m2_decode_parallel_timed(blob, blob_len, n_parts, out, NULL, NULL);
}

int m2_decode_parallel_timed(
    const uint8_t *blob,
    uint32_t blob_len,
    uint32_t n_parts,
    uint8_t *out,
    double *derive_s_out,
    double *segments_s_out
) {
    M2View v;
    uint32_t *cdf = NULL;
    uint8_t *lut = NULL;
    int rc;
    double t0, t1;

    /* Timed API: fused_s = key-interval decode wall; segments_s = 0.
     * n_parts>1 selects parallel path; work splits on n_keys (not n_parts).
     */
    if (derive_s_out) {
        *derive_s_out = 0.0;
    }
    if (segments_s_out) {
        *segments_s_out = 0.0;
    }

    if (n_parts < 1u) {
        return -11;
    }
    rc = m2_parse(blob, blob_len, &v);
    if (rc != 0) {
        return rc;
    }
    if (v.orig_len == 0) {
        return 0;
    }
    if (out == NULL) {
        return -6;
    }
    if (n_parts == 1u) {
        return m2_decode(blob, blob_len, out);
    }

    cdf = (uint32_t *)malloc(256 * sizeof(uint32_t));
    lut = (uint8_t *)malloc(1u << v.scale_bits);
    if (!cdf || !lut) {
        rc = -7;
        goto done;
    }
    if (rans_build_tables(v.freqs, v.scale_bits, cdf, lut) != 0) {
        rc = -8;
        goto done;
    }

    /* One pass per keyframe interval: write plaintext while walking the
     * stream. Eliminates the old derive-then-redecode double pass.
     * Intervals [key[j], key[j+1]) are independent → OpenMP over n_keys.
     */
    t0 = m2_now_s();
    {
        int fail = 0;
        int n_keys_i = (int)v.n_keys;
        uint32_t mask = (1u << v.scale_bits) - 1u;
#if defined(_OPENMP)
        {
            const char *e = getenv("OMP_NUM_THREADS");
            if (e != NULL && e[0] != '\0') {
                int t = atoi(e);
                if (t > 0) {
                    omp_set_num_threads(t);
                }
            }
        }
#pragma omp parallel for schedule(static) reduction(| : fail)
#endif
        for (int kj = 0; kj < n_keys_i; kj++) {
            M2Key cur = key_at(&v, (uint32_t)kj);
            uint32_t range_lo = cur.symbol_index;
            uint32_t range_hi =
                ((uint32_t)kj + 1u < v.n_keys)
                    ? key_at(&v, (uint32_t)kj + 1u).symbol_index
                    : v.orig_len;
            RansSrc src;
            uint32_t x;
            uint32_t i;

            if (range_hi < range_lo || range_hi > v.orig_len) {
                fail = 1;
                continue;
            }
            src.data = v.payload;
            src.len = v.payload_len;
            src.ptr = cur.byte_offset;
            x = cur.state;
            for (i = range_lo; i < range_hi; i++) {
                uint8_t sym = lut[x & mask];
                out[i] = sym;
                if (rans_dec_advance(
                        x, cdf[sym], v.freqs[sym], v.scale_bits, &src, &x
                    ) != 0) {
                    fail = 1;
                    break;
                }
            }
        }
        if (fail) {
            rc = -14;
            goto done;
        }
    }
    t1 = m2_now_s();
    if (derive_s_out) {
        *derive_s_out = t1 - t0;
    }
    if (segments_s_out) {
        *segments_s_out = 0.0;
    }
    rc = 0;

done:
    free(cdf);
    free(lut);
    return rc;
}
