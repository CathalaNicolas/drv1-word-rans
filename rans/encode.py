from __future__ import annotations

import struct

from .core import (
    RANS_L,
    SCALE_BITS,
    ByteSink,
    cdf_and_lut,
    enc_flush,
    enc_put,
    quantize_freqs,
)

MAGIC = b"RAN0"
HEADER = struct.Struct("<4sIB")


def encode(data: bytes, scale_bits: int = SCALE_BITS) -> bytes:
    if not data:
        return HEADER.pack(MAGIC, 0, scale_bits) + bytes(256 * 2)

    counts = [0] * 256
    for b in data:
        counts[b] += 1
    freqs = quantize_freqs(counts, scale_bits)
    cdf, _ = cdf_and_lut(freqs, scale_bits)

    # Worst case: every symbol spills a few bytes plus 4-byte flush.
    sink = ByteSink(len(data) * 8 + 16)
    x = RANS_L
    for symbol in reversed(data):
        x = enc_put(x, cdf[symbol], freqs[symbol], scale_bits, sink)
    enc_flush(x, sink)

    freq_bytes = b"".join(struct.pack("<H", f) for f in freqs)
    return HEADER.pack(MAGIC, len(data), scale_bits) + freq_bytes + sink.bytes()
