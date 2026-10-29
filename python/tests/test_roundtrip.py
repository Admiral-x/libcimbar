import os

import numpy as np
import pytest

import pycimbar


def roundtrip(data, mode="B", filename="payload.bin", transform=lambda f: f, max_frames=200):
    enc = pycimbar.Encoder(data, filename=filename, mode=mode)
    dec = pycimbar.Decoder(mode=mode)
    for _ in range(max_frames):
        if dec.decode(transform(enc.next_frame())) is not None:
            return dec, enc.frames
    pytest.fail(f"not decoded after {max_frames} frames ({dec.frames_decoded}/{dec.frames_seen} frames readable)")


@pytest.mark.parametrize("mode", ["B", "4C"])
def test_roundtrip_random_bytes(mode):
    data = os.urandom(50_000)  # incompressible, so it spans several frames
    dec, frames = roundtrip(data, mode=mode)
    assert dec.data == data
    assert dec.filename == "payload.bin"
    assert frames > 1


def test_roundtrip_small_and_compressible():
    data = b"hello cimbar " * 100
    dec, _ = roundtrip(data, filename="")
    assert dec.data == data
    assert dec.filename is None


def test_frame_is_rgb_image():
    frame = pycimbar.Encoder(b"x" * 1000).next_frame()
    assert frame.dtype == np.uint8
    assert frame.ndim == 3 and frame.shape[2] == 3
    assert frame.shape[0] > 500 and frame.shape[1] > 500


def test_decodes_bgr_frame_inside_a_larger_image():
    # roughly what a screenshot looks like: the code somewhere on a bigger canvas
    def place(frame):
        canvas = np.full((frame.shape[0] + 300, frame.shape[1] + 500, 3), 40, dtype=np.uint8)
        canvas[120:120 + frame.shape[0], 260:260 + frame.shape[1]] = frame
        return np.ascontiguousarray(canvas[..., ::-1])  # as BGR

    data = os.urandom(20_000)
    enc = pycimbar.Encoder(data, filename="x.bin")
    dec = pycimbar.Decoder()
    for _ in range(200):
        if dec.decode(place(enc.next_frame()), bgr=True) is not None:
            break
    assert dec.data == data


def test_skipping_frames_still_decodes():
    data = os.urandom(30_000)
    enc = pycimbar.Encoder(data)
    dec = pycimbar.Decoder()
    for i in range(400):
        frame = enc.next_frame()
        if i % 3 != 0:  # drop two out of three frames
            continue
        if dec.decode(frame) is not None:
            break
    assert dec.data == data


def test_blank_image_is_not_a_frame():
    dec = pycimbar.Decoder()
    assert dec.decode(np.zeros((600, 800, 3), dtype=np.uint8)) is None
    assert dec.frames_seen == 1 and dec.frames_decoded == 0


def test_only_one_active_encoder():
    first = pycimbar.Encoder(b"a" * 100)
    pycimbar.Encoder(b"b" * 100)
    with pytest.raises(pycimbar.CimbarError):
        first.next_frame()


def test_bad_mode():
    with pytest.raises(ValueError):
        pycimbar.Decoder(mode="nope")
