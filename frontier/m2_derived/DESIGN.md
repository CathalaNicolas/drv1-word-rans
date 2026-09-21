# Appendix — DRV1 wire format and mechanism

Companion to [`../../PAPER.md`](../../PAPER.md). Implementation:
`frontier/m2_derived/`.

## Mechanism

Encode once as a **single 1-way word-rANS** payload plus a **sparse
keyframe sketch** (`n_keys` full resume points, uniform in symbol index).

| Client | File | Decode |
|---|---|---|
| Narrow | `thin_blob` → keep **1** key | Sequential `decode` |
| Wide | Dense sketch (`n_keys` keys) | Parallel over key intervals |

Default scorecard: **`n_keys=64`**, vary correctness-N at decode.
Control `n_keys=N` shows the framing cliff.

## Parallelism

- **Correctness:** any partition count N (Python derive + segments).
- **Native fast path:** OpenMP over **keyframe intervals** — ways =
  `n_keys`. Requested N does not change the fused C schedule.
- Raising parallel speed without a framing cliff means raising `n_keys`
  at encode (more meta), not N alone at decode.

## Sketch accounting

Each keyframe is 12 bytes: `symbol_index:u32`, `byte_offset:u32`,
`state:u32`.

```text
meta = 12 * n_keys
```

## Wire (`DRV1`)

```text
magic[4] = "DRV1"
orig_len:u32
scale_bits:u8
n_keys:u16
pad:u8
freqs: u16[256]
payload_len:u32
payload: word-rANS bytes
keys: n_keys × (symbol_index:u32, byte_offset:u32, state:u32)
```

## Cost notes

- Fused native decode: one pass over the payload, split by keys.
- Sequential path ≈ 1-way `ran0`.
- Parallel compact64 ≈ dense `keys=N` wall time at high thread counts
  while staying near entropy (see [`../RESULTS.md`](../RESULTS.md)).
