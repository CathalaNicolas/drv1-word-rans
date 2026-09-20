from __future__ import annotations

from rans.core import ByteSource, RansError, cdf_and_lut, dec_advance, dec_init

from .derive import (
    DeriveStats,
    decode_segment,
    derive_starts,
    part_bounds,
)
from .encode import parse, thin_blob


def decode(blob: bytes, engine: str = "python") -> bytes:
    """Sequential decode. engine: python | native | auto."""
    if engine in ("native", "auto"):
        from .native import decode_native

        out = decode_native(blob)
        if out is not None:
            return out
        if engine == "native":
            raise RuntimeError("M2 native lib unavailable")
    return _decode_python(blob)


def _decode_python(blob: bytes) -> bytes:
    orig_len, scale_bits, _n_keys, freqs, payload, _keys = parse(blob)
    if orig_len == 0:
        return b""
    cdf, lut = cdf_and_lut(freqs, scale_bits)
    src = ByteSource(payload)
    x = dec_init(src)
    mask = (1 << scale_bits) - 1
    out = bytearray(orig_len)
    for i in range(orig_len):
        slot = x & mask
        symbol = lut[slot]
        out[i] = symbol
        x = dec_advance(x, cdf[symbol], freqs[symbol], scale_bits, src)
    return bytes(out)


def decode_parallel(
    blob: bytes,
    n_parts: int,
    stats: DeriveStats | None = None,
    engine: str = "python",
    via_segments: bool = True,
) -> bytes:
    """Decode with N logical partitions.

    engine: python | native | auto
    via_segments:
      True  — derive starts then decode each segment (exercises M2 machinery).
      False — single sequential pass (fast full-message path; ignores N for work).
    Native always uses derive+segments in C when n_parts>1.
    """
    if n_parts < 1:
        raise ValueError("n_parts must be >= 1")

    if engine in ("native", "auto"):
        from .native import decode_native, decode_parallel_native

        if n_parts == 1:
            out = decode_native(blob)
        else:
            out = decode_parallel_native(blob, n_parts)
        if out is not None:
            return out
        if engine == "native":
            raise RuntimeError("M2 native lib unavailable")

    if not via_segments or n_parts == 1:
        if stats is not None:
            stats.symbols_replayed = 0
        return _decode_python(blob)

    return _decode_parallel_python(blob, n_parts, stats)


def _decode_parallel_python(
    blob: bytes,
    n_parts: int,
    stats: DeriveStats | None,
) -> bytes:
    orig_len, scale_bits, _nk, freqs, payload, keys = parse(blob)
    if orig_len == 0:
        return b""

    cdf, lut = cdf_and_lut(freqs, scale_bits)
    starts = derive_starts(
        payload,
        orig_len,
        freqs,
        scale_bits,
        n_parts,
        keys,
        stats=stats,
        cdf=cdf,
        lut=lut,
    )
    bounds = part_bounds(orig_len, n_parts)
    out = bytearray(orig_len)
    for i, st in enumerate(starts):
        count = bounds[i + 1] - bounds[i]
        if st.symbol_index != bounds[i]:
            raise RansError("derived symbol_index mismatch")
        out[bounds[i] : bounds[i + 1]] = decode_segment(
            payload, st, count, freqs, scale_bits, cdf=cdf, lut=lut
        )
    return bytes(out)


def decode_thin(blob: bytes, engine: str = "python") -> bytes:
    return decode(thin_blob(blob), engine=engine)
