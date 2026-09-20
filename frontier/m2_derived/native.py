"""Compile/load M2 DRV1 C decoder."""
from __future__ import annotations

import ctypes
import glob
import os
import subprocess
import sys
import time
from ctypes import POINTER, byref, c_double, c_int, c_uint32, c_uint8, c_void_p

_DIR = os.path.dirname(os.path.abspath(__file__))
_KERNEL_DIR = os.path.join(_DIR, "kernels")
_MINGW = os.path.join(
    os.environ.get("LOCALAPPDATA", ""), "Programs", "mingw64", "bin"
)

_LIB = None
_TRIED = False


def reset_lib() -> None:
    global _LIB, _TRIED
    _LIB = None
    _TRIED = False


def _source_inputs() -> list[str]:
    return sorted(
        glob.glob(os.path.join(_KERNEL_DIR, "*.c"))
        + glob.glob(os.path.join(_KERNEL_DIR, "*.h"))
    )


def _is_fresh(dll_path: str) -> bool:
    try:
        dll_mtime = os.path.getmtime(dll_path)
    except OSError:
        return False
    for src in _source_inputs():
        try:
            if os.path.getmtime(src) > dll_mtime:
                return False
        except OSError:
            return False
    return True


def _compiler_base() -> list[str] | None:
    if os.path.isdir(_MINGW):
        which = os.path.join(_MINGW, "gcc.exe" if sys.platform == "win32" else "gcc")
        if os.path.isfile(which):
            return [which]
    return ["gcc"]


def _existing_dll() -> str | None:
    ext = ".dll" if sys.platform == "win32" else ".so"
    stable = os.path.join(_KERNEL_DIR, "m2_kernel" + ext)
    if os.path.isfile(stable):
        return stable
    matches = sorted(
        glob.glob(os.path.join(_KERNEL_DIR, f"m2_kernel_*{ext}")),
        key=os.path.getmtime,
        reverse=True,
    )
    return matches[0] if matches else None


def _ensure_mingw_on_path() -> None:
    """OpenMP builds need MinGW runtime DLLs visible to the loader."""
    if not os.path.isdir(_MINGW):
        return
    path = os.environ.get("PATH", "")
    if _MINGW.lower() not in path.lower():
        os.environ["PATH"] = _MINGW + os.pathsep + path
    # Python 3.8+ on Windows: PATH alone is often not enough for dependent DLLs
    add = getattr(os, "add_dll_directory", None)
    if add is not None:
        try:
            add(_MINGW)
        except (OSError, FileNotFoundError):
            pass


def _load(path: str) -> ctypes.CDLL:
    _ensure_mingw_on_path()
    # Prefer LoadLibraryEx semantics that search add_dll_directory
    lib = ctypes.CDLL(path, winmode=0) if sys.platform == "win32" else ctypes.CDLL(path)
    lib.m2_peek.argtypes = [c_void_p, c_uint32, POINTER(c_uint32)]
    lib.m2_peek.restype = c_int
    lib.m2_decode.argtypes = [c_void_p, c_uint32, c_void_p]
    lib.m2_decode.restype = c_int
    lib.m2_decode_parallel.argtypes = [c_void_p, c_uint32, c_uint32, c_void_p]
    lib.m2_decode_parallel.restype = c_int
    lib.m2_decode_parallel_timed.argtypes = [
        c_void_p,
        c_uint32,
        c_uint32,
        c_void_p,
        POINTER(c_double),
        POINTER(c_double),
    ]
    lib.m2_decode_parallel_timed.restype = c_int
    lib.ran0_peek.argtypes = [c_void_p, c_uint32, POINTER(c_uint32)]
    lib.ran0_peek.restype = c_int
    lib.ran0_decode.argtypes = [c_void_p, c_uint32, c_void_p]
    lib.ran0_decode.restype = c_int
    return lib


def _compile() -> ctypes.CDLL | None:
    existing = _existing_dll()
    if existing and _is_fresh(existing):
        try:
            return _load(existing)
        except OSError:
            pass

    ext = ".dll" if sys.platform == "win32" else ".so"
    path = os.path.join(
        _KERNEL_DIR, f"m2_kernel_{os.getpid()}_{int(time.time())}{ext}"
    )
    cc = _compiler_base()
    if cc is None:
        return None
    srcs = [
        os.path.join(_KERNEL_DIR, "m2_blob.c"),
        os.path.join(_KERNEL_DIR, "ran0_blob.c"),
    ]
    cmd = cc + [
        "-O3",
        "-fopenmp",
        "-shared",
        "-o",
        path,
        *srcs,
        f"-I{_KERNEL_DIR}",
    ]
    if sys.platform == "win32":
        cmd.append("-Wl,--out-implib," + path + ".a")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        # Retry without OpenMP if libgomp / -fopenmp unavailable
        cmd_no = [c for c in cmd if c != "-fopenmp"]
        try:
            subprocess.run(cmd_no, check=True, capture_output=True, text=True)
            if os.environ.get("M2_NATIVE_VERBOSE"):
                print("m2 native: built without OpenMP")
        except (OSError, subprocess.CalledProcessError) as exc2:
            err = getattr(exc2, "stderr", None) or getattr(exc, "stderr", None) or str(exc2)
            if os.environ.get("M2_NATIVE_VERBOSE"):
                print("m2 native compile failed:", err)
            return None
    try:
        return _load(path)
    except OSError:
        return None


def get_lib() -> ctypes.CDLL | None:
    global _LIB, _TRIED
    if _LIB is not None:
        return _LIB
    if _TRIED:
        return None
    _TRIED = True
    _LIB = _compile()
    return _LIB


def decode_native(blob: bytes) -> bytes | None:
    lib = get_lib()
    if lib is None:
        return None
    orig = c_uint32()
    buf = (c_uint8 * len(blob)).from_buffer_copy(blob)
    rc = lib.m2_peek(ctypes.cast(buf, c_void_p), len(blob), byref(orig))
    if rc != 0:
        raise RuntimeError(f"m2_peek failed: {rc}")
    if orig.value == 0:
        return b""
    out = (c_uint8 * orig.value)()
    rc = lib.m2_decode(ctypes.cast(buf, c_void_p), len(blob), out)
    if rc != 0:
        raise RuntimeError(f"m2_decode failed: {rc}")
    return bytes(out)


def decode_parallel_native(blob: bytes, n_parts: int) -> bytes | None:
    lib = get_lib()
    if lib is None:
        return None
    orig = c_uint32()
    buf = (c_uint8 * len(blob)).from_buffer_copy(blob)
    rc = lib.m2_peek(ctypes.cast(buf, c_void_p), len(blob), byref(orig))
    if rc != 0:
        raise RuntimeError(f"m2_peek failed: {rc}")
    if orig.value == 0:
        return b""
    out = (c_uint8 * orig.value)()
    rc = lib.m2_decode_parallel(
        ctypes.cast(buf, c_void_p), len(blob), n_parts, out
    )
    if rc != 0:
        raise RuntimeError(f"m2_decode_parallel failed: {rc}")
    return bytes(out)


def decode_parallel_timed_native(
    blob: bytes, n_parts: int
) -> tuple[bytes, float, float] | None:
    """Returns (plaintext, derive_s, segments_s) or None if no native lib."""
    lib = get_lib()
    if lib is None:
        return None
    orig = c_uint32()
    buf = (c_uint8 * len(blob)).from_buffer_copy(blob)
    rc = lib.m2_peek(ctypes.cast(buf, c_void_p), len(blob), byref(orig))
    if rc != 0:
        raise RuntimeError(f"m2_peek failed: {rc}")
    if orig.value == 0:
        return b"", 0.0, 0.0
    out = (c_uint8 * orig.value)()
    derive_s = c_double()
    segments_s = c_double()
    rc = lib.m2_decode_parallel_timed(
        ctypes.cast(buf, c_void_p),
        len(blob),
        n_parts,
        out,
        byref(derive_s),
        byref(segments_s),
    )
    if rc != 0:
        raise RuntimeError(f"m2_decode_parallel_timed failed: {rc}")
    return bytes(out), float(derive_s.value), float(segments_s.value)


def decode_ran0_native(blob: bytes) -> bytes | None:
    """C 1-way RAN0 decode — fair baseline for M2 native timings."""
    lib = get_lib()
    if lib is None:
        return None
    orig = c_uint32()
    buf = (c_uint8 * len(blob)).from_buffer_copy(blob)
    rc = lib.ran0_peek(ctypes.cast(buf, c_void_p), len(blob), byref(orig))
    if rc != 0:
        raise RuntimeError(f"ran0_peek failed: {rc}")
    if orig.value == 0:
        return b""
    out = (c_uint8 * orig.value)()
    rc = lib.ran0_decode(ctypes.cast(buf, c_void_p), len(blob), out)
    if rc != 0:
        raise RuntimeError(f"ran0_decode failed: {rc}")
    return bytes(out)
