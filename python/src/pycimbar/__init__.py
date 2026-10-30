"""Python bindings for libcimbar: color icon matrix barcodes.

Encode a file into a stream of cimbar frames, and decode it back from camera images of those frames::

    enc = pycimbar.Encoder(data, filename="report.pdf")
    frames = [enc.next_frame() for _ in range(20)]     # RGB numpy arrays

    dec = pycimbar.Decoder()
    for frame in frames:
        if dec.decode(frame) is not None:
            break
    dec.data, dec.filename

Frames are fountain coded: the decoder needs *enough* frames, in any order, not all of them.
The underlying C API keeps global state, so there is one active Encoder and one active Decoder per process;
creating a new one makes the previous one unusable.
"""

import ctypes

import numpy as np

from . import _native
from ._native import lib, lock

__all__ = ["MODES", "Encoder", "Decoder", "CimbarError"]
__version__ = "0.6.7"

# libcimbar's mode ids. B is the default, 4C is the 0.5.x format.
MODES = {"B": 68, "Bm": 67, "Bu": 66, "4C": 4, "8C": 8}

_active_encoder = None
_active_decoder = None


class CimbarError(RuntimeError):
    pass


def _mode_value(mode):
    try:
        return MODES[mode]
    except KeyError:
        raise ValueError(f"unknown cimbar mode {mode!r}, expected one of {list(MODES)}") from None


def _ptr(arr):
    return arr.ctypes.data_as(_native._u8p)


def _report_progress():
    """After a fountain decode, the C API's report is the progress of each file in flight: "[ 0.25,0.5 ]"."""
    buf = ctypes.create_string_buffer(256)
    n = lib.cimbard_get_report(ctypes.cast(buf, _native._u8p), len(buf))
    try:
        values = [float(v) for v in buf.raw[:n].decode("ascii").strip("[] ").split(",") if v.strip()]
    except (UnicodeDecodeError, ValueError):
        return 0.0
    return min(1.0, max(values, default=0.0))


class Encoder:
    """Encodes `data` into an endless stream of cimbar frames.

    `compression` is the zstd level (0-22); None uses libcimbar's default.
    """

    def __init__(self, data, filename="", mode="B", compression=None, encode_id=None):
        global _active_encoder
        self.mode = mode
        self._mode_val = _mode_value(mode)
        self._compression = -1 if compression is None else int(compression)
        self.frames = 0

        buf = np.frombuffer(bytes(data), dtype=np.uint8)
        name = filename.encode("utf-8") if filename else b""
        with lock:
            _active_encoder = self
            self._check(lib.cimbare_configure(self._mode_val, self._compression), "configure")
            self._check(lib.cimbare_init_encode(name or None, len(name), -1 if encode_id is None else encode_id), "init_encode")

            # feed the data in chunks of encode_bufsize; a short (or empty) chunk finishes the encode
            chunk = lib.cimbare_encode_bufsize()
            offset = 0
            while True:
                part = buf[offset:offset + chunk]
                res = self._check(lib.cimbare_encode(_ptr(part) if len(part) else None, len(part)), "encode")
                if res == 0:
                    break
                offset += len(part)

    @staticmethod
    def _check(res, what):
        if res < 0:
            raise CimbarError(f"cimbare_{what} failed ({res})")
        return res

    def next_frame(self, bgr=False):
        """Returns the next frame as an HxWx3 uint8 array (RGB, or BGR for OpenCV when `bgr` is set)."""
        with lock:
            if _active_encoder is not self:
                raise CimbarError("this Encoder was replaced by a newer one (only one can be active)")
            self._check(lib.cimbare_configure(self._mode_val, self._compression), "configure")
            self._check(lib.cimbare_next_frame(False), "next_frame")

            w, h, c = ctypes.c_int(), ctypes.c_int(), ctypes.c_int()
            self._check(lib.cimbare_get_frame_dims(ctypes.byref(w), ctypes.byref(h), ctypes.byref(c)), "get_frame_dims")
            ptr = _native._u8p()
            self._check(lib.cimbare_get_frame_buff(ctypes.byref(ptr)), "get_frame_buff")
            frame = np.ctypeslib.as_array(ptr, shape=(h.value, w.value, c.value)).copy()

        self.frames += 1
        if bgr:
            frame = np.ascontiguousarray(frame[..., ::-1])
        return frame

    def __iter__(self):
        while True:
            yield self.next_frame()


class Decoder:
    """Reassembles a file from cimbar frames (camera images, screenshots or encoder output)."""

    def __init__(self, mode="B"):
        global _active_decoder
        self.mode = mode
        self._mode_val = _mode_value(mode)
        self.data = None
        self.filename = None
        self.frames_seen = 0
        self.frames_decoded = 0  # frames where a cimbar code was found and read
        self.frames_rejected = 0  # ... of those, frames whose data didn't fit the transfer
        self.progress = 0.0  # share of the file's fountain blocks received so far (1.0 once done)
        with lock:
            _active_decoder = self
            lib.cimbard_configure_decode(self._mode_val)
            lib.cimbard_reset()

    @property
    def done(self):
        return self.data is not None

    def decode(self, image, bgr=False):
        """Feeds one image (HxWx3 or HxWx4 uint8, RGB(A); BGR when `bgr` is set).

        Returns the file's bytes once enough frames were decoded, None until then.
        """
        if self.data is not None:
            return self.data

        img = np.asarray(image)
        if img.dtype != np.uint8 or img.ndim != 3 or img.shape[2] not in (3, 4):
            raise ValueError(f"expected an HxWx3 or HxWx4 uint8 image, got {img.dtype} {img.shape}")
        if bgr:
            img = img[..., [2, 1, 0]] if img.shape[2] == 3 else img[..., [2, 1, 0, 3]]
        img = np.ascontiguousarray(img)
        height, width, channels = img.shape

        with lock:
            if _active_decoder is not self:
                raise CimbarError("this Decoder was replaced by a newer one (only one can be active)")
            lib.cimbard_configure_decode(self._mode_val)

            self.frames_seen += 1
            buf = np.empty(lib.cimbard_get_bufsize(), dtype=np.uint8)
            size = lib.cimbard_scan_extract_decode(_ptr(img), width, height, channels, _ptr(buf), len(buf))
            if size <= 0:
                return None  # no cimbar code found in this image
            self.frames_decoded += 1

            file_id = lib.cimbard_fountain_decode(_ptr(buf), size)
            if file_id < 0:
                # the frame's chunks didn't fit the transfer (garbled header, another file's size, ...)
                self.frames_rejected += 1
                return None
            if file_id == 0:
                self.progress = max(self.progress, _report_progress())
                return None  # need more frames
            self._finish(file_id)
            self.progress = 1.0
        return self.data

    def _finish(self, file_id):
        name = ctypes.create_string_buffer(1024)
        res = lib.cimbard_get_filename(file_id, name, len(name))
        if res < 0:
            raise CimbarError(f"cimbard_get_filename failed ({res})")
        self.filename = name.raw[:res].decode("utf-8", "replace") or None

        out = np.empty(lib.cimbard_get_decompress_bufsize(), dtype=np.uint8)
        parts = []
        while True:
            res = lib.cimbard_decompress_read(file_id, _ptr(out), len(out))
            if res < 0:
                raise CimbarError(f"cimbard_decompress_read failed ({res})")
            if res == 0:
                break
            parts.append(out[:res].tobytes())
        self.data = b"".join(parts)
