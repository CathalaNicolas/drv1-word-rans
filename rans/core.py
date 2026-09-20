from __future__ import annotations

# Word rANS: state lives in [RANS_L, 2^32). Encoder writes u16 downward;
# decoder reads them forward. L = 2^16 so each symbol needs at most one
# 16-bit refill (vectorisable predicated load). Matches ryg rans_word.

RANS_L = 1 << 16
SCALE_BITS = 12
M = 1 << SCALE_BITS


class RansError(Exception):
    """Invalid frequencies, unknown symbol, or truncated rANS payload."""


def quantize_freqs(counts: list[int], scale_bits: int = SCALE_BITS) -> list[int]:
    """Map raw histogram onto freqs that sum to 2^scale_bits.

    Every byte that appeared at least once keeps freq >= 1. Bytes that
    never appeared stay 0 and cannot be encoded.
    """
    m = 1 << scale_bits
    total = sum(counts)
    if total == 0:
        return [0] * 256
    present = [s for s, c in enumerate(counts) if c > 0]
    if len(present) > m:
        raise RansError(f"{len(present)} symbols cannot fit in M={m}")
    freqs = [0] * 256
    for s in present:
        freqs[s] = max(1, (counts[s] * m) // total)
    delta = sum(freqs) - m
    if delta > 0:
        for s in sorted(present, key=lambda s: freqs[s], reverse=True):
            give = min(delta, freqs[s] - 1)
            freqs[s] -= give
            delta -= give
            if delta == 0:
                break
    elif delta < 0:
        for s in sorted(present, key=lambda s: counts[s], reverse=True):
            freqs[s] += -delta
            delta = 0
            break
    if sum(freqs) != m:
        raise RansError(f"freq table does not sum to {m}: {sum(freqs)}")
    return freqs


def cdf_and_lut(freqs: list[int], scale_bits: int = SCALE_BITS) -> tuple[list[int], list[int]]:
    """cdf[s] = start of s; lut[slot] = symbol owning that slot."""
    m = 1 << scale_bits
    cdf = [0] * 256
    lut = [0] * m
    acc = 0
    for s, f in enumerate(freqs):
        cdf[s] = acc
        if f:
            lut[acc : acc + f] = [s] * f
            acc += f
    if acc != m:
        raise RansError(f"cdf coverage {acc} != {m}")
    return cdf, lut


class ByteSink:
    """Pre-sized buffer written from the end toward the front."""

    def __init__(self, capacity: int) -> None:
        self.buf = bytearray(capacity)
        self.ptr = capacity

    def write_byte(self, byte: int) -> None:
        if self.ptr <= 0:
            raise RansError("rANS sink overflow")
        self.ptr -= 1
        self.buf[self.ptr] = byte & 0xFF

    def write_u16(self, v: int) -> None:
        if self.ptr < 2:
            raise RansError("rANS sink overflow")
        self.ptr -= 2
        self.buf[self.ptr] = v & 0xFF
        self.buf[self.ptr + 1] = (v >> 8) & 0xFF

    def bytes(self) -> bytes:
        return bytes(self.buf[self.ptr :])


class ByteSource:
    def __init__(self, data: bytes, ptr: int = 0) -> None:
        self.data = data
        self.ptr = ptr

    def read_byte(self) -> int:
        if self.ptr >= len(self.data):
            raise RansError("truncated rANS payload")
        b = self.data[self.ptr]
        self.ptr += 1
        return b

    def read_u16(self) -> int:
        if self.ptr + 2 > len(self.data):
            raise RansError("truncated rANS payload")
        lo = self.data[self.ptr]
        hi = self.data[self.ptr + 1]
        self.ptr += 2
        return lo | (hi << 8)

    def remaining(self) -> int:
        return len(self.data) - self.ptr


def enc_put(x: int, start: int, freq: int, scale_bits: int, sink: ByteSink) -> int:
    if freq <= 0:
        raise RansError("cannot encode a zero-frequency symbol")
    # At most one 16-bit renorm per symbol when L = 2^16 and scale_bits <= 16.
    x_max = ((RANS_L >> scale_bits) << 16) * freq
    while x >= x_max:
        sink.write_u16(x & 0xFFFF)
        x >>= 16
    return ((x // freq) << scale_bits) + (x % freq) + start


def enc_flush(x: int, sink: ByteSink) -> None:
    # Write high word first so downward growth yields [lo, hi] when read forward.
    sink.write_u16((x >> 16) & 0xFFFF)
    sink.write_u16(x & 0xFFFF)


def dec_init(src: ByteSource) -> int:
    lo = src.read_u16()
    hi = src.read_u16()
    return lo | (hi << 16)


def dec_advance(x: int, start: int, freq: int, scale_bits: int, src: ByteSource) -> int:
    mask = (1 << scale_bits) - 1
    x = freq * (x >> scale_bits) + (x & mask) - start
    while x < RANS_L:
        x = (x << 16) | src.read_u16()
    return x
