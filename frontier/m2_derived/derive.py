from __future__ import annotations

from dataclasses import dataclass

from rans.core import (
    ByteSource,
    RansError,
    cdf_and_lut,
    dec_advance,
)


@dataclass(frozen=True)
class DerivedStart:
    symbol_index: int
    byte_offset: int
    state: int


@dataclass
class DeriveStats:
    """Work done by derive_starts (batched forward pass)."""

    symbols_replayed: int = 0
    key_jumps: int = 0
    exact_key_hits: int = 0


def _part_bounds(orig_len: int, n_parts: int) -> list[int]:
    if n_parts < 1:
        raise ValueError("n_parts must be >= 1")
    if orig_len == 0:
        return [0, 0]
    bounds = [(i * orig_len) // n_parts for i in range(n_parts)]
    bounds.append(orig_len)
    out = [bounds[0]]
    for b in bounds[1:]:
        if b > out[-1]:
            out.append(b)
    return out


def _rightmost_key_at_or_before(
    keys: list[tuple[int, int, int]], symbol_index: int
) -> tuple[int, int, int]:
    """Binary search; keys sorted by symbol_index."""
    lo, hi = 0, len(keys)
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if keys[mid][0] <= symbol_index:
            lo = mid
        else:
            hi = mid
    if keys[lo][0] > symbol_index:
        raise RansError("no keyframe at or before boundary")
    return keys[lo]


def _advance(
    payload: bytes,
    freqs: list[int],
    scale_bits: int,
    start_sym: int,
    start_off: int,
    start_state: int,
    target_sym: int,
    cdf: list[int] | None = None,
    lut: list[int] | None = None,
) -> tuple[int, int, int]:
    if target_sym < start_sym:
        raise RansError("advance target before start")
    if target_sym == start_sym:
        return start_sym, start_off, start_state
    if cdf is None or lut is None:
        cdf, lut = cdf_and_lut(freqs, scale_bits)
    src = ByteSource(payload, start_off)
    x = start_state
    mask = (1 << scale_bits) - 1
    for _ in range(target_sym - start_sym):
        slot = x & mask
        symbol = lut[slot]
        x = dec_advance(x, cdf[symbol], freqs[symbol], scale_bits, src)
    return target_sym, src.ptr, x


def derive_starts(
    payload: bytes,
    orig_len: int,
    freqs: list[int],
    scale_bits: int,
    n_parts: int,
    keys: list[tuple[int, int, int]],
    stats: DeriveStats | None = None,
    cdf: list[int] | None = None,
    lut: list[int] | None = None,
) -> list[DerivedStart]:
    """Batched derive: one forward pass with keyframe jumps + short stretches."""
    if orig_len == 0:
        return []
    if not keys:
        raise RansError("keys required for derive_starts")
    keys = sorted(keys, key=lambda k: k[0])
    if keys[0][0] != 0:
        raise RansError("first keyframe must be at symbol 0")
    if cdf is None or lut is None:
        cdf, lut = cdf_and_lut(freqs, scale_bits)

    bounds = _part_bounds(orig_len, n_parts)
    out: list[DerivedStart] = []
    st = stats if stats is not None else DeriveStats()

    cur_sym, cur_off, cur_state = keys[0]
    for b in bounds[:-1]:
        k_sym, k_off, k_state = _rightmost_key_at_or_before(keys, b)
        if k_sym > cur_sym:
            cur_sym, cur_off, cur_state = k_sym, k_off, k_state
            st.key_jumps += 1
        elif k_sym == b and (cur_sym != b or cur_off != k_off):
            cur_sym, cur_off, cur_state = k_sym, k_off, k_state
            st.exact_key_hits += 1
        elif k_sym == b and cur_sym == b:
            st.exact_key_hits += 1

        if b > cur_sym:
            gap = b - cur_sym
            cur_sym, cur_off, cur_state = _advance(
                payload,
                freqs,
                scale_bits,
                cur_sym,
                cur_off,
                cur_state,
                b,
                cdf=cdf,
                lut=lut,
            )
            st.symbols_replayed += gap
        elif b < cur_sym:
            raise RansError("cursor past boundary")

        out.append(DerivedStart(b, cur_off, cur_state))

    if len(out) != len(bounds) - 1:
        raise RansError("derive_starts count mismatch")
    return out


def decode_segment(
    payload: bytes,
    start: DerivedStart,
    count: int,
    freqs: list[int],
    scale_bits: int,
    cdf: list[int] | None = None,
    lut: list[int] | None = None,
) -> bytes:
    if count < 0:
        raise ValueError("count must be >= 0")
    if count == 0:
        return b""
    if cdf is None or lut is None:
        cdf, lut = cdf_and_lut(freqs, scale_bits)
    src = ByteSource(payload, start.byte_offset)
    x = start.state
    mask = (1 << scale_bits) - 1
    out = bytearray(count)
    for i in range(count):
        slot = x & mask
        symbol = lut[slot]
        out[i] = symbol
        x = dec_advance(x, cdf[symbol], freqs[symbol], scale_bits, src)
    return bytes(out)


part_bounds = _part_bounds
