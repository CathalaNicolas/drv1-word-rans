# Frontier results — M2 / DRV1

Ship artifact only. Retired P2 packages (DTC1, BND1, M3, DRV2, …) are not in
this tree; see git history if needed.

Reproduce: `python -m frontier.m2_derived.measure` (2026-09-19, MinGW -O3).

## Size (source / skew, 200 KB)

Primary: `n_keys=64` compact sketch. Control: `n_keys=N` (size cliff).

| corpus | form | N | tot/H0 | meta | K1 | K2 |
|---|---|---:|---:|---:|:---:|:---:|
| source-200k | compact64 | 3125 | **1.0109** | 768 | Y | Y |
| source-200k | keys=N | 3125 | **1.3119** | 37500 | Y | **N** |
| skew-200k | compact64 | 3125 | **1.0529** | 768 | — | — |

Thin (`keep=1` key): thin/rans1 ≈ **1.0002**. K5 pass. K3 (skew) pass vs CHK0.

## Decode timing (C + OpenMP vs `ran0`)

Native parallel path = **fused key-interval decode**; ways = `n_keys`, not
requested N.

| path | threads | ms | vs ran0 |
|---|---:|---:|---:|
| ran0 (1-way) | 1 | 1.09 | 1.00× |
| m2 seq compact64 | 1 | 1.15 | 1.06× |
| m2 parallel compact64 (ways=64) | 8 | 0.28 | **0.26×** |
| m2 parallel compact64 (ways=64) | 12 | 0.46 | 0.42× |
| m2 parallel keys=N (ways=3125) | 12 | 0.39 | **0.36×** |

Size-safe compact64 matches (and can beat) dense-key wall time. Parallelism
ways = `n_keys`, not requested N.

## Reading

Framing cliff closed for a practical parallelism budget (`n_keys`). Coalesce
as a throughput win is not part of this claim. See [`CLAIM.md`](CLAIM.md).
