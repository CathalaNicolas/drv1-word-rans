# DRV1 — sparse-keyframe word-rANS

One order-0 word-rANS bitstream with a sparse keyframe sketch: near
1-way size, droppable metadata, no machine width on the wire, and
parallel decode faster than sequential 1-way. Useful parallelism is
budgeted by `n_keys` at encode — not free N-way speedup at decode.

**Read the experience report first:** [`PAPER.md`](PAPER.md)

| | |
|---|---|
| Measured tables | [`frontier/RESULTS.md`](frontier/RESULTS.md) |
| Wire / mechanism | [`frontier/m2_derived/DESIGN.md`](frontier/m2_derived/DESIGN.md) |

## Reproduce

Needs Python 3 and a C compiler with OpenMP (MinGW/gcc on Windows, or
clang/gcc elsewhere). From the repo root:

```text
python run_all.py
python -m frontier.m2_derived.measure
```

Native kernels compile on first import / measure run.

## Layout

```text
PAPER.md                 experience report (start here)
frontier/RESULTS.md      size + timing appendix
frontier/m2_derived/     DRV1 encode, decode, OpenMP C kernels
frontier/m2_derived/DESIGN.md   wire format appendix
rans/                    1-way word-rANS baseline
common/                  corpora + test harness
```
