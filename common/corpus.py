"""Deterministic test corpora. Never use os.urandom in tests."""

from __future__ import annotations

import os
import random


def rnd(n: int, seed: int = 0xC0FFEE) -> bytes:
    """Deterministic pseudo-random bytes."""
    return random.Random(seed).randbytes(n)


def skewed(n: int, seed: int = 1, p_common: float = 0.9) -> bytes:
    """Low-entropy: mostly b'a', occasionally random."""
    r = random.Random(seed)
    return bytes(
        0x61 if r.random() < p_common else r.randrange(256) for _ in range(n)
    )


def text(n: int) -> bytes:
    """Real-ish structured bytes: this repo's own source, tiled to n."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parts: list[bytes] = []
    for rel in (
        os.path.join("rans", "encode.py"),
        os.path.join("rans", "core.py"),
        os.path.join("frontier", "m2_derived", "encode.py"),
        os.path.join("frontier", "m2_derived", "decode.py"),
    ):
        path = os.path.join(root, rel)
        with open(path, "rb") as f:
            parts.append(f.read())
    src = b"\n".join(parts) or b"x"
    return (src * (n // len(src) + 1))[:n]
