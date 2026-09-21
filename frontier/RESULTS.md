# Appendix — measured results (DRV1 / M2)

Companion to [`../PAPER.md`](../PAPER.md). Ship artifact only.

Reproduce: `python -m frontier.m2_derived.measure`  
Host for the numbers below: 2026-09-19, Windows, MinGW `-O3`.

## Size (200 KB corpora)

Primary: `n_keys=64` compact sketch. Control: `n_keys=N` (framing cliff).
H₀ = zero-order empirical entropy of the plaintext (bytes).

| corpus | form | N | tot/H₀ | meta (B) | K1 | K2 |
|---|---|---:|---:|---:|:---:|:---:|
| source-200k | compact64 | 3125 | **1.0109** | 768 | Y | Y |
| source-200k | keys=N | 3125 | **1.3119** | 37500 | Y | **N** |
| skew-200k | compact64 | 3125 | **1.0529** | 768 | — | — |

Thin blob (`keep=1` key): thin/rans1 ≈ **1.0002**. K5 (thin decode == full
decode) pass.

## Decode timing (C + OpenMP vs `ran0`)

Native parallel path = fused OpenMP over keyframe intervals.
Ways = `n_keys`, not requested correctness-N.

**Speedup** = ran0_ms / path_ms (larger is better).

| path | threads | ms | speedup vs ran0 |
|---|---:|---:|---:|
| ran0 (1-way) | 1 | 1.09 | 1.0× |
| m2 seq compact64 | 1 | 1.15 | 0.95× |
| m2 parallel compact64 (ways=64) | 8 | 0.28 | **~3.9×** |
| m2 parallel compact64 (ways=64) | 12 | 0.46 | ~2.4× |
| m2 parallel keys=N (ways=3125) | 12 | 0.39 | ~2.8× |

Size-safe compact64 matches (and can beat) dense-key wall time while
keeping K2. See the paper for interpretation and limits of the claim.
