from __future__ import annotations

import struct

from rans.core import (
    RANS_L,
    SCALE_BITS,
    ByteSink,
    ByteSource,
    RansError,
    cdf_and_lut,
    dec_advance,
    dec_init,
    enc_flush,
    enc_put,
    quantize_freqs,
)

MAGIC = b"DRV1"
HEADER = struct.Struct("<4sIBHB")  # magic, orig_len, scale_bits, n_keys, pad
KEY = struct.Struct("<III")  # symbol_index, byte_offset, state
KEY_SIZE = KEY.size  # 12


def default_n_keys(n_parts_hint: int) -> int:
    """Compact sketch density: ~sqrt(hint), at least 1."""
    if n_parts_hint < 1:
        raise ValueError("n_parts_hint must be >= 1")
    k = int(round(n_parts_hint**0.5))
    return max(1, k)


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


def _take_keyframes(
    payload: bytes,
    orig_len: int,
    freqs: list[int],
    scale_bits: int,
    n_keys: int,
) -> list[tuple[int, int, int]]:
    """Sequential decode; snapshot at n_keys uniform symbol starts."""
    if orig_len == 0 or n_keys < 1:
        return []
    bounds = _part_bounds(orig_len, n_keys)
    want = set(bounds[:-1])
    cdf, lut = cdf_and_lut(freqs, scale_bits)
    src = ByteSource(payload)
    x = dec_init(src)
    mask = (1 << scale_bits) - 1
    keys: list[tuple[int, int, int]] = []
    if 0 in want:
        keys.append((0, src.ptr, x))
    for i in range(orig_len):
        if i in want and i != 0:
            keys.append((i, src.ptr, x))
        slot = x & mask
        symbol = lut[slot]
        x = dec_advance(x, cdf[symbol], freqs[symbol], scale_bits, src)
    if len(keys) != len(bounds) - 1:
        raise RansError(f"expected {len(bounds) - 1} keys, got {len(keys)}")
    return keys


def encode(
    data: bytes,
    n_keys: int | None = None,
    n_parts_hint: int | None = None,
    scale_bits: int = SCALE_BITS,
) -> bytes:
    """1-way word-rANS + sparse keyframe sketch.

    n_keys: explicit sketch size. If omitted, uses default_n_keys(n_parts_hint)
    or 1 when no hint is given.
    """
    if n_keys is None:
        n_keys = default_n_keys(n_parts_hint) if n_parts_hint is not None else 1
    if n_keys < 1:
        raise ValueError("n_keys must be >= 1")

    if not data:
        body = HEADER.pack(MAGIC, 0, scale_bits, 1, 0) + bytes(512)
        body += struct.pack("<I", 0)  # payload_len
        body += KEY.pack(0, 0, 0)  # dummy key 0 (unused for empty)
        return body

    counts = [0] * 256
    for b in data:
        counts[b] += 1
    freqs = quantize_freqs(counts, scale_bits)
    cdf, _ = cdf_and_lut(freqs, scale_bits)

    sink = ByteSink(len(data) * 8 + 16)
    x = RANS_L
    for symbol in reversed(data):
        x = enc_put(x, cdf[symbol], freqs[symbol], scale_bits, sink)
    enc_flush(x, sink)
    payload = sink.bytes()

    n_keys_eff = min(n_keys, len(data))
    keys = _take_keyframes(payload, len(data), freqs, scale_bits, n_keys_eff)

    freq_bytes = b"".join(struct.pack("<H", f) for f in freqs)
    parts = [
        HEADER.pack(MAGIC, len(data), scale_bits, len(keys), 0),
        freq_bytes,
        struct.pack("<I", len(payload)),
        payload,
    ]
    for sym_i, off, st in keys:
        parts.append(KEY.pack(sym_i, off, st))
    return b"".join(parts)


def parse(
    blob: bytes,
) -> tuple[int, int, int, list[int], bytes, list[tuple[int, int, int]]]:
    """orig_len, scale_bits, n_keys, freqs, payload, keys."""
    if len(blob) < HEADER.size + 512 + 4:
        raise RansError("DRV1 header too short")
    magic, orig_len, scale_bits, n_keys, _pad = HEADER.unpack_from(blob)
    if magic != MAGIC:
        raise RansError(f"bad magic {magic!r}")
    if n_keys < 1:
        raise RansError("n_keys must be >= 1")
    freq_off = HEADER.size
    freqs = [
        struct.unpack_from("<H", blob, freq_off + 2 * i)[0] for i in range(256)
    ]
    plen_off = freq_off + 512
    (payload_len,) = struct.unpack_from("<I", blob, plen_off)
    pay_off = plen_off + 4
    end = pay_off + payload_len
    if end + n_keys * KEY_SIZE > len(blob):
        raise RansError("truncated DRV1 key table")
    if end + n_keys * KEY_SIZE != len(blob):
        raise RansError("DRV1 trailing garbage or size mismatch")
    payload = blob[pay_off:end]
    keys: list[tuple[int, int, int]] = []
    ptr = end
    for _ in range(n_keys):
        keys.append(KEY.unpack_from(blob, ptr))
        ptr += KEY_SIZE
    return orig_len, scale_bits, n_keys, freqs, payload, keys


def thin_blob(blob: bytes) -> bytes:
    """Narrow client: keep only keyframe 0; payload unchanged."""
    orig_len, scale_bits, n_keys, freqs, payload, keys = parse(blob)
    if not keys:
        raise RansError("no keys")
    k0 = keys[0]
    freq_bytes = b"".join(struct.pack("<H", f) for f in freqs)
    return b"".join(
        [
            HEADER.pack(MAGIC, orig_len, scale_bits, 1, 0),
            freq_bytes,
            struct.pack("<I", len(payload)),
            payload,
            KEY.pack(*k0),
        ]
    )


def size_breakdown(blob: bytes) -> dict[str, int]:
    orig_len, scale_bits, n_keys, freqs, payload, keys = parse(blob)
    meta = n_keys * KEY_SIZE
    header = HEADER.size + 512 + 4
    return {
        "tot": len(blob),
        "header_freqs": header,
        "payload": len(payload),
        "meta": meta,
        "n_keys": n_keys,
        "orig_len": orig_len,
        "scale_bits": scale_bits,
    }
