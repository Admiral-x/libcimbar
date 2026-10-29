# pycimbar

Python bindings for [libcimbar](https://github.com/sz3/libcimbar), the color icon matrix barcode.
They call libcimbar's own encoder and decoder, the code behind [cimbar.org](https://cimbar.org)
and the [CFC](https://github.com/sz3/cfc) Android app. Mode B frames from libcimbar's encoder
(the samples in `samples/b`) decode with `pycimbar.Decoder`.

The only runtime dependency is numpy. Each wheel holds one native library with OpenCV
(core, imgproc, calib3d) linked in statically. It exports only the libcimbar C API, so it can be
loaded next to `opencv-python`.

```python
import pycimbar

# encode: an endless stream of frames (fountain coded, so any "enough" of them will do)
enc = pycimbar.Encoder(open("report.pdf", "rb").read(), filename="report.pdf", mode="B")
frame = enc.next_frame()            # HxWx3 uint8, RGB  (next_frame(bgr=True) for OpenCV)

# decode: feed camera frames, screenshots or encoder output until it returns the file
dec = pycimbar.Decoder(mode="B")
for image in frames:                # e.g. from cv2.VideoCapture: dec.decode(image, bgr=True)
    if dec.decode(image) is not None:
        break
print(dec.filename, len(dec.data))
```

Modes: `B` (default), `Bm`, `Bu`, `4C` (the 0.5.x format) and `8C`. The encoder and decoder must use the same mode.

libcimbar's C API keeps global state: there is one active `Encoder` and one active `Decoder` per process.
Creating a new one makes the previous one raise `CimbarError`. Calls are serialized with a lock.

## Building

```
pip install .
```

This needs CMake ≥ 3.21 and a C++17 compiler (MSVC 2022, gcc ≥ 9, clang). The first build downloads
and compiles a minimal static OpenCV 4.10, which takes a few minutes. Set `CIMBAR_OPENCV_PREFIX` to a
directory to keep that build and reuse it.

Wheels for Linux (x86_64, aarch64), Windows (x86_64) and macOS (arm64, x86_64) are built by
`.github/workflows/python-wheels.yml` with cibuildwheel.
