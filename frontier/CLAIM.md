# Frontier claim — DRV1 / M2

**One sentence.** One order-0 word-rANS blob with a **sparse keyframe sketch**
gives near-1-way size, droppable metadata, no machine width on the wire, and
parallel decode ~3× faster than sequential 1-way — with parallelism budget
`n_keys` chosen at encode (not free N-way speedup at decode).

Measured 2026-09-19 (Windows, MinGW -O3). Reproduce:
`python -m frontier.m2_derived.measure`.

---

## Delivered

| Property | Status |
|---|---|
| Near-ANS at warp-scale framing (`n_keys=64`, tot/H0 **1.0109**) | **Yes** (K1/K2/K3) |
| Metadata droppable (`thin_blob` → 1 key) | **Yes** (K5) |
| No SIMD/warp width in the file | **Yes** (P4) |
| Correct decode at any partition count N | **Yes** (Python / derive path) |
| Parallel wall-time speedup | **Yes** — fused OpenMP over **`n_keys`**, ~**0.26×** vs `ran0` at 8 threads |
| Free N-way speedup for arbitrary decode N | **No** — useful parallelism ≤ `n_keys` |
| Coalesce that speeds decode (old P2) | **No** — dependency-bound on this model; retired |

Wire: **DRV1** in [`m2_derived/`](m2_derived/). Design notes:
[`m2_derived/DESIGN.md`](m2_derived/DESIGN.md). Tables:
[`RESULTS.md`](RESULTS.md).

---

## Honest P1

The original problem asked for partition count chosen freely at decode.
What ships:

> Encode chooses sketch density `n_keys` (parallelism budget + size).
> Decode may use any N for **correctness**; the fast native path parallelizes
> over keyframe intervals (`n_keys` ways). Raising parallelism without a size
> cliff means raising `n_keys` at encode, not N alone at decode.

That is weaker than “any N is free at decode,” and stronger than independent
streams where N is both parallelism and framing cost (O(N) meta). DRV1
compact64 pays **768 B** of sketch for ~same parallel speed as dense keys=N.

---

## What we are not claiming

- Solved `P1 ∧ P2 ∧ P3 ∧ P4` under the original PROBLEM success sentence.
- That coalesce is impossible in general — only that it does not bind for
  order-0 word-rANS on this harness (dependency-bound hot loop).
- An LZ / zlib ratio result.

---

## Reproduce

```text
python run_all.py
python -m frontier.m2_derived.measure
```
