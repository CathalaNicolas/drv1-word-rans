from __future__ import annotations

from common.cases import Case
from common.corpus import rnd

from frontier.m2_derived.decode import decode, decode_parallel, decode_thin
from frontier.m2_derived.derive import DeriveStats, derive_starts
from frontier.m2_derived.encode import (
    default_n_keys,
    encode,
    parse,
    size_breakdown,
    thin_blob,
)
from frontier.m2_derived.native import get_lib, reset_lib

SAMPLES = [
    b"",
    b"a",
    b"abracadabra" * 80,
    rnd(4096, seed=11),
    rnd(20000, seed=12),
]


def _rt(data: bytes) -> None:
    for n_keys in (1, 4, 16):
        if data and n_keys > len(data):
            continue
        blob = encode(data, n_keys=n_keys)
        assert decode(blob) == data
        assert decode_thin(blob) == data
        for n in (1, 2, 7, 64, 256):
            if data and n > len(data):
                continue
            assert decode_parallel(blob, n, via_segments=True) == data


def _thin_drops_keys() -> None:
    data = rnd(3000, seed=3)
    blob = encode(data, n_keys=32)
    thin = thin_blob(blob)
    assert len(thin) < len(blob)
    br = size_breakdown(blob)
    br_t = size_breakdown(thin)
    assert br["payload"] == br_t["payload"]
    assert br["meta"] == 32 * 12
    assert br_t["meta"] == 12
    assert br_t["n_keys"] == 1
    assert decode(thin) == data
    assert decode_parallel(thin, 16, via_segments=True) == data


def _derive_short_replay_stats() -> None:
    data = rnd(10_000, seed=9)
    blob = encode(data, n_keys=16)
    orig_len, scale_bits, _nk, freqs, payload, keys = parse(blob)
    stats = DeriveStats()
    n_parts = 256
    starts = derive_starts(
        payload, orig_len, freqs, scale_bits, n_parts, keys, stats=stats
    )
    assert starts[0].symbol_index == 0
    assert stats.symbols_replayed <= orig_len
    assert stats.symbols_replayed < orig_len
    assert decode_parallel(blob, n_parts, via_segments=True) == data


def _n_chosen_at_decode() -> None:
    data = rnd(8000, seed=4)
    blob = encode(data, n_keys=default_n_keys(1000))
    for n in (1, 8, 64, 128, 1000):
        assert decode_parallel(blob, n, via_segments=True) == data


def _sqrt_default_keys() -> None:
    assert default_n_keys(1) == 1
    assert default_n_keys(100) == 10
    assert default_n_keys(3125) == 56


def _native_matches_python() -> None:
    reset_lib()
    if get_lib() is None:
        raise AssertionError("M2 native lib required for optimization tests")
    for n_keys in (1, 16, 64):
        for data in (b"", b"xyz" * 100, rnd(5000, seed=n_keys)):
            blob = encode(data, n_keys=n_keys)
            assert decode(blob, engine="native") == decode(blob, engine="python")
            for n in (1, 8, 64, 256):
                if data and n > len(data):
                    continue
                assert decode_parallel(
                    blob, n, engine="native"
                ) == decode_parallel(blob, n, engine="python", via_segments=True)


def _fast_full_matches_segments() -> None:
    data = rnd(3000, seed=5)
    blob = encode(data, n_keys=16)
    a = decode_parallel(blob, 64, via_segments=False)
    b = decode_parallel(blob, 64, via_segments=True)
    assert a == b == data


def _ran0_native_matches_python() -> None:
    from rans import decode as rans_decode
    from rans import encode as rans_encode

    from frontier.m2_derived.native import decode_ran0_native, get_lib, reset_lib

    reset_lib()
    if get_lib() is None:
        raise AssertionError("M2 native lib required")
    for data in (b"", b"hello", rnd(4096, seed=99)):
        blob = rans_encode(data)
        assert decode_ran0_native(blob) == rans_decode(blob) == data


def cases() -> list[Case]:
    out = [
        Case(name=f"roundtrip[{i}]", fn=lambda d=s: _rt(d))
        for i, s in enumerate(SAMPLES)
    ]
    out.append(
        Case(
            name="thin_blob_drops_keyframes",
            fn=_thin_drops_keys,
            why="Narrow client keeps payload + key 0 only; meta shrinks.",
        )
    )
    out.append(
        Case(
            name="derive_batched_short_replay",
            fn=_derive_short_replay_stats,
            why="Sparse keys + batched derive replay each symbol at most once.",
        )
    )
    out.append(
        Case(
            name="n_parts_chosen_at_decode",
            fn=_n_chosen_at_decode,
            why="Any decode N is correct; native speed uses n_keys ways.",
        )
    )
    out.append(
        Case(
            name="default_n_keys_sqrt",
            fn=_sqrt_default_keys,
            why="Compact sketch density defaults to ~sqrt(hint).",
        )
    )
    out.append(
        Case(
            name="native_matches_python",
            fn=_native_matches_python,
            why="C DRV1 decoder must match the Python oracle.",
        )
    )
    out.append(
        Case(
            name="ran0_native_matches_python",
            fn=_ran0_native_matches_python,
            why="C RAN0 baseline must match python rans for fair timings.",
        )
    )
    out.append(
        Case(
            name="fast_full_matches_segments",
            fn=_fast_full_matches_segments,
            why="via_segments=False is a single pass; must equal segment path.",
        )
    )
    return out
