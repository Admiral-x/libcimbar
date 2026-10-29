"""ctypes declarations for the libcimbar C API (src/lib/cimbar_js/cimbar_js.h, cimbar_recv_js.h)."""

import ctypes
import sys
import threading
from ctypes import POINTER, c_bool, c_char_p, c_float, c_int, c_int64, c_uint, c_uint32, c_ubyte
from pathlib import Path

_LIB_NAMES = {
    "win32": "cimbar.dll",
    "darwin": "libcimbar.dylib",
}


def _load():
    path = Path(__file__).with_name(_LIB_NAMES.get(sys.platform, "libcimbar.so"))
    if not path.exists():
        raise ImportError(f"pycimbar: native library not found at {path}")
    return ctypes.CDLL(str(path))


lib = _load()

# the C API keeps one encoder and one decoder as global state, so every call goes through this lock
lock = threading.RLock()

_u8p = POINTER(c_ubyte)

_SIGNATURES = {
    # encoder
    "cimbare_configure": (c_int, [c_int, c_int]),
    "cimbare_init_encode": (c_int, [c_char_p, c_uint, c_int]),
    "cimbare_encode_bufsize": (c_int, []),
    "cimbare_encode": (c_int, [_u8p, c_uint]),
    "cimbare_next_frame": (c_int, [c_bool]),
    "cimbare_get_frame_buff": (c_int, [POINTER(_u8p)]),
    "cimbare_get_frame_dims": (c_int, [POINTER(c_int), POINTER(c_int), POINTER(c_int)]),
    "cimbare_get_aspect_ratio": (c_float, []),
    # decoder
    "cimbard_configure_decode": (c_int, [c_int]),
    "cimbard_get_bufsize": (c_int, []),
    "cimbard_scan_extract_decode": (c_int, [_u8p, c_uint, c_uint, c_int, _u8p, c_uint]),
    "cimbard_fountain_decode": (c_int64, [_u8p, c_uint]),
    "cimbard_get_filesize": (c_uint, [c_uint32]),
    "cimbard_get_filename": (c_int, [c_uint32, c_char_p, c_uint]),
    "cimbard_get_decompress_bufsize": (c_int, []),
    "cimbard_decompress_read": (c_int, [c_uint32, _u8p, c_uint]),
    "cimbard_get_report": (c_uint, [_u8p, c_uint]),
    "cimbard_reset": (c_int, []),
}

for _name, (_restype, _argtypes) in _SIGNATURES.items():
    _fn = getattr(lib, _name)
    _fn.restype = _restype
    _fn.argtypes = _argtypes
