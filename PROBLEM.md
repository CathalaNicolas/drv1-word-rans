# Problem → result: warp-scale ANS without the framing cliff

**Original ask.** One order-0 word-rANS bitstream: flexible partitions, coalesced
SIMT access, near scalar-ANS size at thousands of lanes, no machine width on
the wire (`P1 ∧ P2 ∧ P3 ∧ P4`).

**What shipped.** [`frontier/CLAIM.md`](frontier/CLAIM.md) — **DRV1 / M2**:
near-ANS size with a sparse sketch, droppable meta, no width on the wire, and
parallel decode several× faster than 1-way. Useful parallelism is **`n_keys`
at encode**, not free arbitrary N at decode. Coalesce-as-throughput (P2) does
not pay on this model and is not claimed.

| | Ship status |
|---|---|
| Near-ANS size (P3) / no width (P4) / droppable meta | **Yes** |
| Correct decode at any N | **Yes** |
| Free N-way wall-time parallelism | **No** — capped at `n_keys` |
| Coalesce that speeds decode (P2) | **Not claimed** |

## Kill criteria (DRV1)

| Gate | Threshold | compact64 (`n_keys=64`) |
|---|---|---|
| **K1** thin vs 1-way | ≤ 1.02 | PASS |
| **K2** @ framing density | ≤ 1.05 tot/H0 | PASS (1.0109) |
| **K5** thin == full decode | bit-identical | PASS |

## Layout

```text
frontier/m2_derived/   DRV1 encode, decode, OpenMP C
frontier/CLAIM.md      claim text
frontier/RESULTS.md    tables
common/                corpus + test harness
rans/                  1-way word-rANS (baseline + tables)
```

Reproduce: `python run_all.py` · `python -m frontier.m2_derived.measure`
