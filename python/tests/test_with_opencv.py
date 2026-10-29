"""pycimbar next to opencv-python in one process, with camera-like distortions."""
import os
from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
import pycimbar  # noqa: E402  (imported after cv2 on purpose)


def photograph(frame_bgr, rng):
    """Roughly what a phone sees: the code tilted on a bigger canvas, slightly blurred, saved as JPEG."""
    h, w = frame_bgr.shape[:2]
    canvas = np.full((h + 400, w + 600, 3), 30, dtype=np.uint8)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    jitter = rng.uniform(-25, 25, size=(4, 2)).astype(np.float32)
    dst = src + np.float32([300, 200]) + jitter
    warped = cv2.warpPerspective(frame_bgr, cv2.getPerspectiveTransform(src, dst), (canvas.shape[1], canvas.shape[0]),
                                 dst=canvas, borderMode=cv2.BORDER_TRANSPARENT)
    warped = cv2.GaussianBlur(warped, (3, 3), 0)
    ok, jpg = cv2.imencode(".jpg", warped, [cv2.IMWRITE_JPEG_QUALITY, 85])
    assert ok
    return cv2.imdecode(jpg, cv2.IMREAD_COLOR)


def test_png_roundtrip_through_opencv():
    data = os.urandom(25_000)
    enc = pycimbar.Encoder(data, filename="a.bin")
    dec = pycimbar.Decoder()
    for _ in range(200):
        ok, png = cv2.imencode(".png", enc.next_frame(bgr=True))
        assert ok
        if dec.decode(cv2.imdecode(png, cv2.IMREAD_COLOR), bgr=True) is not None:
            break
    assert dec.data == data


def test_decodes_photographed_frames():
    rng = np.random.default_rng(1)
    data = os.urandom(25_000)
    enc = pycimbar.Encoder(data, filename="photo.bin")
    dec = pycimbar.Decoder()
    for _ in range(300):
        if dec.decode(photograph(enc.next_frame(bgr=True), rng), bgr=True) is not None:
            break
    assert dec.data == data, f"{dec.frames_decoded}/{dec.frames_seen} frames readable"


def test_decodes_upstream_encoder_samples():
    # frames made by libcimbar's own encoder (git submodule update --init samples)
    samples = sorted((Path(__file__).parents[2] / "samples" / "b").glob("tr_*.png"))
    if not samples:
        pytest.skip("samples submodule not checked out")
    dec = pycimbar.Decoder(mode="B")
    for path in samples:
        dec.decode(cv2.imread(str(path)), bgr=True)
    assert dec.done
    assert dec.data.startswith(b"\x89PNG")
