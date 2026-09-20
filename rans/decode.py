from __future__ import annotations

import struct

from .core import (
    SCALE_BITS,
    ByteSource,
    RansError,
    cdf_and_lut,
    dec_advance,
    dec_init,
)
from .encode import HEADER, MAGIC


def decode(blob: bytes) -> bytes:
    if len(blob) < HEADER.size + 256 * 2:
        raise RansError("header too short")
    magic, orig_len, scale_bits = HEADER.unpack_from(blob)
    if magic != MAGIC:
        raise RansError(f"bad magic {magic!r}")
    if orig_len == 0:
        return b""
    freq_off = HEADER.size
    freqs = [
        struct.unpack_from("<H", blob, freq_off + 2 * i)[0] for i in range(256)
    ]
    payload = blob[freq_off + 512 :]
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
