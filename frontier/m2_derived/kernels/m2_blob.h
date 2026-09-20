#ifndef M2_BLOB_H
#define M2_BLOB_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

int m2_peek(const uint8_t *blob, uint32_t blob_len, uint32_t *orig_out);
int m2_decode(const uint8_t *blob, uint32_t blob_len, uint8_t *out);

/* Parallel decode: OpenMP over keyframe intervals (parallelism = n_keys).
 * n_parts>1 selects this path; the fast fused kernel ignores n_parts for
 * work-splitting (see DESIGN.md). Output is always the full plaintext.
 */
int m2_decode_parallel(
    const uint8_t *blob,
    uint32_t blob_len,
    uint32_t n_parts,
    uint8_t *out
);

/* Same as m2_decode_parallel. Optional timers:
 *   derive_s_out   — fused key-interval decode wall (sole hot phase)
 *   segments_s_out — always 0 (no second pass)
 */
int m2_decode_parallel_timed(
    const uint8_t *blob,
    uint32_t blob_len,
    uint32_t n_parts,
    uint8_t *out,
    double *derive_s_out,
    double *segments_s_out
);

/* Fair 1-way C baseline (RAN0 wire format). */
int ran0_peek(const uint8_t *blob, uint32_t blob_len, uint32_t *orig_out);
int ran0_decode(const uint8_t *blob, uint32_t blob_len, uint8_t *out);

#ifdef __cplusplus
}
#endif

#endif
