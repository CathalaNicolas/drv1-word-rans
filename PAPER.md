# Parallel decode of one ANS bitstream without a framing cliff

**An experience report on order-0 word-rANS with a sparse keyframe sketch (DRV1).**

Measured 2026-09-19 on Windows (MinGW `-O3`, OpenMP). Reproduce from the repo root:

```text
python run_all.py
python -m frontier.m2_derived.measure
```

---

## 1. Abstract

We wanted a single order-0 word-rANS bitstream that (1) stays near
scalar ANS size, (2) carries no SIMD/warp width on the wire, (3) can be
decoded correctly under any partition count chosen at decode time, and
(4) runs faster in parallel than a one-way decoder.

Independent per-partition streams (or one keyframe per partition) close
the parallelism door but open a **framing cliff**: metadata grows as
O(N) and total size blows past entropy once N reaches warp-like counts
(thousands). Coalesced SIMT layouts we tried did not buy throughput on
this dependency-bound decode loop, so that line of work was retired.

What shipped is **DRV1**: one scalar rANS payload plus a **sparse
keyframe sketch** of `n_keys` resume points. Correctness supports any
decode partition count N. Useful parallel speed is budgeted by `n_keys`
at encode — not free arbitrary N at decode. At `n_keys=64` on a 200 KB
source corpus we measure total size ≈ **1.01×** zero-order entropy and
parallel decode about **3.9×** faster than sequential 1-way rANS at 8
threads, with 768 bytes of sketch metadata.

---

## 2. Background (one paragraph)

**rANS** (asymmetric numeral systems) is an entropy coder. *Order-0
word-rANS* here means: byte alphabet, fixed frequency table, 32-bit
coder state, 16-bit renormalization words (the usual “word” rANS
layout). A normal decoder is strictly sequential: each symbol updates
state, so you cannot start in the middle of the payload without a
**resume point** (byte offset + coder state at a known symbol index).

---

## 3. The ask

Original success criteria, written as four properties:

| Id | Property |
|---|---|
| **P1** | Partition count N chosen freely at **decode** (flexible work split). |
| **P2** | Coalesced SIMT-friendly body access that actually speeds decode. |
| **P3** | Near scalar-ANS size (no large framing overhead). |
| **P4** | No machine width (SIMD width / warp size) stored in the file. |

Informally: one bitstream, warp-scale framing without paying O(N) meta,
and real parallel wall time.

**Platform note.** The problem was framed in GPU/SIMT language (warps,
coalesce). What this repository measures is a **CPU OpenMP** decoder
with the same algorithmic constraints. Lessons about framing vs
parallelism transfer; absolute GPU timings are not claimed.

---

## 4. Why the obvious designs fail

### 4.1 The framing cliff

Put one full resume keyframe at every partition boundary (`n_keys = N`).
Each keyframe is 12 bytes (`symbol_index`, `byte_offset`, `state`). At
N = 3125 on 200 KB source text:

| Form | Meta | Total / H₀ |
|---|---:|---:|
| Sparse sketch (`n_keys=64`) | 768 B | **1.0109** |
| Dense keys (`n_keys=N=3125`) | 37 500 B | **1.3119** |

Same payload; the dense sketch alone is a large fraction of the file.
That is the cliff: **N is both parallelism and framing cost**.

### 4.2 Coalesce (P2) did not pay here

Layouts aimed at coalesced wide loads were explored under working names
(DTC1, BND1, M3, DRV2, …) and removed from this tree. On order-0
word-rANS the hot loop is **state-dependent**: the next symbol’s decode
needs the previous state. Reordering bytes for nicer memory traffic did
not unlock wall-time wins on this harness. We do **not** claim coalesce
is impossible in general — only that it was not the binding constraint
for this coder on these measurements, and it is not part of the ship
claim.

---

## 5. What we shipped: sparse keyframes (DRV1)

Encode once as a normal 1-way word-rANS payload, then attach `n_keys`
resume points spaced uniformly in symbol index.

```text
┌──────────────────────────────────────────────────────────┐
│  header + frequency table                                 │
│  payload: one word-rANS byte stream                       │
│  keys[0 .. n_keys): (symbol_index, byte_offset, state)    │
└──────────────────────────────────────────────────────────┘
         │
         ├── thin client: keep 1 key → sequential decode
         └── wide client: parallelize over key intervals
```

| Client | File | Decode |
|---|---|---|
| Narrow | `thin_blob` → keep **1** key | Sequential |
| Wide | Full sketch (`n_keys` keys) | Parallel over key intervals |

**Honest split of P1.** Decode may use any N for **correctness**
(Python derive path jumps to the nearest prior key and replays forward).
The fast native OpenMP path parallelizes over **keyframe intervals**, so
useful ways ≤ `n_keys`. Raising parallel speed without a size cliff
means raising `n_keys` at encode, not N alone at decode.

That is weaker than “any N is free speedup at decode,” and stronger than
independent streams where N is both parallelism and O(N) framing.

Default scorecard uses **`n_keys=64`** (“compact64”). Control
`n_keys=N` shows the cliff still exists if you ask for it.

Wire layout and byte accounting: [`frontier/m2_derived/DESIGN.md`](frontier/m2_derived/DESIGN.md).

---

## 6. Kill criteria and results

Gates on **source-200k** (200 KB English-like corpus). H₀ is zero-order
empirical entropy of the plaintext in bytes. “Thin” means the blob with
all but one keyframe dropped.

| Gate | Meaning | Threshold | compact64 |
|---|---|---|---|
| **K1** | Thin blob vs 1-way size | thin/H₀ ≤ 1.02 | PASS |
| **K2** | Full blob at warp-ish N | tot/H₀ ≤ 1.05 at N=3125 | PASS (**1.0109**) |
| **K5** | Thin decode == full decode | bit-identical | PASS |

Skewed corpus (90% one symbol): tot/H₀ ≈ 1.05 with the same 768 B sketch
(meta dominates more when the payload is tiny).

### Decode timing (C + OpenMP vs 1-way `ran0`)

Times are wall milliseconds, best of five. **Speedup** = ran0_ms /
path_ms (larger is better).

| Path | Threads | ms | Speedup vs ran0 |
|---|---:|---:|---:|
| ran0 (1-way) | 1 | 1.09 | 1.0× |
| m2 sequential compact64 | 1 | 1.15 | 0.95× |
| m2 parallel compact64 (ways=64) | 8 | 0.28 | **~3.9×** |
| m2 parallel compact64 (ways=64) | 12 | 0.46 | ~2.4× |
| m2 parallel keys=N (ways=3125) | 12 | 0.39 | ~2.8× |

Size-safe compact64 matches (and can beat) dense-key wall time at high
thread counts while keeping K2. Parallel ways follow `n_keys`, not the
requested correctness-N.

Full tables: [`frontier/RESULTS.md`](frontier/RESULTS.md).

---

## 7. What we are not claiming

- Solved `P1 ∧ P2 ∧ P3 ∧ P4` under the original success sentence.
- Free N-way wall-time speedup for arbitrary decode N.
- That coalesce is impossible — only that it did not bind here.
- An LZ / zlib ratio result, or GPU timing numbers.

---

## 8. Lessons (the experience)

1. **Separate correctness partitioning from parallelism budget.**
   Letting N mean both “how I split work” and “how much meta I pay”
   forces the framing cliff. DRV1 pays meta for `n_keys` and treats N as
   a correctness parameter.

2. **Droppable meta is a product feature.** Narrow clients strip the
   sketch and still decode; wide clients keep it for speed. Same payload.

3. **Do not put machine width on the wire.** Parallelism policy stays a
   decoder choice (and an encode-time sketch density), not a file-format
   constant.

4. **Retire throughput ideas that the hot loop cannot use.** Memory
   layout tricks that ignore the state dependency burn schedule time;
   write them down, then cut them from the ship artifact.

5. **Measure the control.** Always keep a `keys=N` row next to the sparse
   sketch so the cliff stays visible in the paper, not only in memory.

---

## 9. Repository map

| Path | Role |
|---|---|
| [`PAPER.md`](PAPER.md) | This experience report (canonical narrative) |
| [`frontier/RESULTS.md`](frontier/RESULTS.md) | Measured size + timing appendix |
| [`frontier/m2_derived/DESIGN.md`](frontier/m2_derived/DESIGN.md) | Wire format + mechanism appendix |
| `frontier/m2_derived/` | DRV1 encode / decode / OpenMP C kernels |
| `rans/` | 1-way word-rANS baseline |
| `common/` | Corpora + test harness |
| `run_all.py` | Correctness cases |

---

## Glossary

| Term | Meaning |
|---|---|
| **H₀** | Zero-order empirical entropy of the plaintext (bytes). |
| **tot/H₀** | Encoded file size divided by H₀. |
| **n_keys** | Number of keyframes stored in the sketch (parallelism budget). |
| **N** | Partition count requested at decode (correctness split). |
| **compact64** | Scorecard setting `n_keys=64`. |
| **thin_blob** | Same file with sketch reduced to a single keyframe. |
| **DRV1 / M2** | Ship format name / package name for this design. |
| **ran0** | Sequential 1-way word-rANS baseline decoder. |
| **Framing cliff** | Size blow-up when meta grows as O(N) with partition count. |
