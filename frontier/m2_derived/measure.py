"""M2 finished scorecard. Run: python -m frontier.m2_derived.measure"""
from __future__ import annotations

import math
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from common.corpus import skewed, text
from frontier.compare import K1_THIN_H0_MAX, K2_DENSE_H0_MAX_N3125, WAYS
from frontier.m2_derived.decode import decode, decode_parallel, decode_thin
from frontier.m2_derived.derive import DeriveStats
from frontier.m2_derived.encode import encode, size_breakdown, thin_blob
from rans import encode as rans_encode

COMPACT_KEYS = 64  # primary M2 bet: fixed sketch, vary decode N


def _h0_bytes(data: bytes) -> float:
    if not data:
        return 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    n = len(data)
    h = 0.0
    for c in counts:
        if c:
            p = c / n
            h -= p * math.log2(p)
    return h * n / 8.0


def _best_s(fn, reps: int = 5) -> float:
    fn()
    samples = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)
    return min(samples)


def _row(
    corpus: str,
    data: bytes,
    n_parts: int,
    n_keys: int,
    label: str,
) -> dict:
    blob = encode(data, n_keys=n_keys)
    thin = thin_blob(blob)
    br = size_breakdown(blob)
    h0 = _h0_bytes(data)
    rans1 = len(rans_encode(data))
    stats = DeriveStats()
    out_p = decode_parallel(blob, n_parts, stats=stats, via_segments=True)
    drop_ok = decode_thin(thin) == data and out_p == data and decode(blob) == data
    tot_h0 = br["tot"] / h0 if h0 else float("nan")
    thin_h0 = len(thin) / h0 if h0 else float("nan")
    # K1/K2 (see PAPER.md) are defined on source text; skew is reported separately.
    k1 = (corpus != "source-200k") or (thin_h0 <= K1_THIN_H0_MAX)
    k2 = (
        (corpus != "source-200k")
        or (n_parts != 3125)
        or (tot_h0 <= K2_DENSE_H0_MAX_N3125)
    )
    return {
        "label": label,
        "mechanism": "m2_derived",
        "corpus": corpus,
        "N": n_parts,
        "n_keys": n_keys,
        "tot": br["tot"],
        "tot/H0": tot_h0,
        "tot/rans1": br["tot"] / rans1 if rans1 else float("nan"),
        "thin/rans1": len(thin) / rans1 if rans1 else float("nan"),
        "payload": br["payload"],
        "meta": br["meta"],
        "thin_tot": len(thin),
        "thin/H0": thin_h0,
        "drop_ok": drop_ok,
        "replay_syms": stats.symbols_replayed,
        "key_jumps": stats.key_jumps,
        "K1": k1,
        "K2": k2,
        "rans1": rans1,
    }


def measure() -> list[dict]:
    rows: list[dict] = []
    corpora = (
        ("source-200k", text(200_000)),
        ("skew-200k", skewed(200_000, seed=7, p_common=0.9)),
    )
    for name, data in corpora:
        # Primary: compact fixed sketch, decode N varies
        for n in WAYS:
            rows.append(_row(name, data, n, COMPACT_KEYS, "compact64"))
        # Control: key every partition (M1-shaped cliff)
        for n in WAYS:
            rows.append(_row(name, data, n, n, "keys=N"))
    return rows


def format_table(rows: list[dict]) -> str:
    lines = [
        "| label | corpus | N | n_keys | tot | tot/H0 | tot/rans1 | meta | "
        "thin/rans1 | replay | drop_ok | K1 | K2 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|:---:|:---:|:---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['label']} | {r['corpus']} | {r['N']} | {r['n_keys']} | "
            f"{r['tot']} | {r['tot/H0']:.4f} | {r['tot/rans1']:.4f} | {r['meta']} | "
            f"{r['thin/rans1']:.4f} | {r['replay_syms']} | "
            f"{str(r['drop_ok']).lower()} | "
            f"{'Y' if r['K1'] else 'N'} | {'Y' if r['K2'] else 'N'} |"
        )
    return "\n".join(lines)


def timing_block(data: bytes) -> str:
    """C-vs-C only, including OpenMP thread sweeps."""
    import os

    from frontier.m2_derived.native import (
        decode_ran0_native,
        get_lib,
        reset_lib,
    )
    from rans import encode as rans_encode_py

    reset_lib()
    if get_lib() is None:
        return "### Decode timing\n\nM2 native lib UNAVAILABLE — cannot run fair C compare.\n"

    rans_blob = rans_encode_py(data)
    compact = encode(data, n_keys=COMPACT_KEYS)
    dense = encode(data, n_keys=3125)

    assert decode_ran0_native(rans_blob) == data
    assert decode(compact, engine="native") == data
    assert decode_parallel(dense, 3125, engine="native") == data

    prev = os.environ.get("OMP_NUM_THREADS")
    cpus = os.cpu_count() or 4
    thread_sets = [1]
    for t in (2, 4, 8, cpus):
        if t > 1 and t not in thread_sets:
            thread_sets.append(t)

    lines = [
        "### Fair decode timing — all C + OpenMP (source 200 KB, best of 5)",
        "",
        "Baseline: `ran0_decode`. Native parallel path = fused OpenMP over "
        f"**n_keys** (compact={COMPACT_KEYS}); not over requested N.",
        "Speedup = ran0_ms / path_ms (larger is better).",
        "",
        "| path | OMP_NUM_THREADS | ms | speedup vs ran0 |",
        "|---|---:|---:|---:|",
    ]

    def _set_threads(n: int) -> None:
        os.environ["OMP_NUM_THREADS"] = str(n)

    try:
        _set_threads(1)
        t0 = _best_s(lambda: decode_ran0_native(rans_blob))
        lines.append(f"| ran0_decode (C, 1-way) | 1 | {t0 * 1e3:.2f} | 1.00x |")

        t_seq = _best_s(lambda: decode(compact, engine="native"))
        lines.append(
            f"| m2_decode seq compact64 | 1 | {t_seq * 1e3:.2f} | {t0 / t_seq:.2f}x |"
        )

        for thr in thread_sets:
            _set_threads(thr)
            t_p = _best_s(
                lambda: decode_parallel(compact, 3125, engine="native")
            )
            lines.append(
                f"| m2 parallel compact64 (ways={COMPACT_KEYS}) | {thr} | "
                f"{t_p * 1e3:.2f} | {t0 / t_p:.2f}x |"
            )
        for thr in thread_sets:
            _set_threads(thr)
            t_d = _best_s(lambda: decode_parallel(dense, 3125, engine="native"))
            lines.append(
                f"| m2 parallel keys=N (ways=3125) | {thr} | "
                f"{t_d * 1e3:.2f} | {t0 / t_d:.2f}x |"
            )
    finally:
        if prev is None:
            os.environ.pop("OMP_NUM_THREADS", None)
        else:
            os.environ["OMP_NUM_THREADS"] = prev

    # Phase split: derive vs segments at N=3125 compact64 (1 and max threads)
    from frontier.m2_derived.native import decode_parallel_timed_native

    lines.extend(
        ["", f"Phase wall (compact64 fused, ways={COMPACT_KEYS}, best of 5):", ""]
    )
    for thr in (1, thread_sets[-1]):
        _set_threads(thr)
        os.environ["OMP_NUM_THREADS"] = str(thr)
        phases = []
        for _ in range(5):
            got = decode_parallel_timed_native(compact, 3125)
            if got is None:
                break
            out, d_s, s_s = got
            assert out == data
            phases.append((d_s, s_s))
        if phases:
            d_ms = min(p[0] for p in phases) * 1e3
            s_ms = min(p[1] for p in phases) * 1e3
            lines.append(
                f"- OMP={thr}: fused={d_ms:.2f} ms, second_pass={s_ms:.2f} ms "
                f"(speedup vs ran0={ (t0 * 1e3) / d_ms:.2f}x fused)."
            )
    if prev is None:
        os.environ.pop("OMP_NUM_THREADS", None)
    else:
        os.environ["OMP_NUM_THREADS"] = prev

    return "\n".join(lines)


def main() -> int:
    rows = measure()
    print(format_table(rows))
    print()
    data = text(200_000)
    print(timing_block(data))
    src_c = [
        r
        for r in rows
        if r["corpus"] == "source-200k" and r["label"] == "compact64"
    ]
    r3125 = next(r for r in src_c if r["N"] == 3125)
    print()
    print(
        f"compact64 K1(source thin)={all(r['K1'] for r in src_c)}  "
        f"K2@3125={r3125['K2']} tot/H0={r3125['tot/H0']:.4f} meta={r3125['meta']}"
    )
    print(f"drop_ok all: {all(r['drop_ok'] for r in rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
