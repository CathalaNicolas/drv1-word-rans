# DRV1 — order-0 word-rANS with a sparse keyframe sketch

One bitstream: near 1-way size, droppable metadata, no machine width on the
wire, and parallel decode faster than sequential 1-way. Parallelism is budgeted
by `n_keys` at encode — not free N-way speedup at decode.

## Claim

| Property | Status |
|---|---|
| Near-ANS at warp-scale framing (`n_keys=64`) | Yes (~1.01× H₀) |
| Metadata droppable (`thin_blob` → 1 key) | Yes |
| No SIMD/warp width in the file | Yes |
| Correct decode at any partition count N | Yes |
| Parallel wall-time speedup | Yes — fused OpenMP over `n_keys`, ~0.26–0.32× vs `ran0` at 8–12 threads |
| Free N-way speedup for arbitrary decode N | No — useful parallelism ≤ `n_keys` |

Full claim and honesty bounds: [`frontier/CLAIM.md`](frontier/CLAIM.md).  
Problem → result: [`PROBLEM.md`](PROBLEM.md).  
Measured tables: [`frontier/RESULTS.md`](frontier/RESULTS.md).

## Layout

```text
frontier/m2_derived/   DRV1 encode, decode, OpenMP C kernels
frontier/CLAIM.md      claim text
frontier/RESULTS.md    size + timing tables
common/                corpus + test harness
rans/                  1-way word-rANS (baseline)
```

## Reproduce

Needs Python 3 and a C compiler with OpenMP (MinGW/gcc on Windows, or clang/gcc
elsewhere). From the repo root:

```text
python run_all.py
python -m frontier.m2_derived.measure
```

Native kernels compile on first import / measure run.
