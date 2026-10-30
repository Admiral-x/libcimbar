"""Crafted streams: what a hostile video could make the decoder reassemble.

wirehair is systematic, so fountain blocks 0..n-1 are the raw stream; feeding them straight to the C API stands in
for frames that decode to exactly these bytes. The stream is a zstd skippable frame with the file name, then zstd
data."""
import ctypes
import struct

import pytest

import pycimbar
from pycimbar._native import lib, lock

MODE_B = pycimbar.MODES["B"]


def _header(encode_id, size, block):
    return bytes([(encode_id & 0x7F) | ((size >> 17) & 0x80), (size >> 16) & 0xFF, (size >> 8) & 0xFF, size & 0xFF,
                  block >> 8, block & 0xFF])


def _chunk_size():
    for size in range(50, 3000):  # the smallest size that is not "not a multiple of the chunk size" (-5)
        buf = (ctypes.c_ubyte * size).from_buffer_copy(_header(1, 100_000, 60_000).ljust(size, b"\0"))
        if lib.cimbard_fountain_decode(buf, size) != -5:
            return size
    raise AssertionError("no chunk size found")


def _skippable(content):
    return struct.pack("<II", 0x184D2A50, len(content)) + content


def _rle_frame(blocks, last=True):
    """A zstd frame of RLE blocks, 128 KiB of 'A' each, from 4 bytes each."""
    out = b"\x28\xb5\x2f\xfd" + bytes([0x00, 0x38])
    for i in range(blocks):
        is_last = last and i == blocks - 1
        out += ((131072 << 3) | (1 << 1) | is_last).to_bytes(3, "little") + b"A"
    return out


def _decode_stream(name, body, **decoder_args):
    """Decode a stream of a name frame, padding (wirehair needs a few blocks), then `body`."""
    dec = pycimbar.Decoder(**decoder_args)
    stream = _skippable(b"\x01" + name) + _skippable(bytes(700)) + body
    with lock:
        lib.cimbard_configure_decode(MODE_B)
        lib.cimbard_reset()
        size = _chunk_size()
        lib.cimbard_reset()
        payload = size - 6
        file_id = 0
        for i in range(-(-len(stream) // payload)):
            chunk = _header(5, len(stream), i) + stream[i * payload:(i + 1) * payload].ljust(payload, b"\0")
            file_id = lib.cimbard_fountain_decode((ctypes.c_ubyte * size).from_buffer_copy(chunk), size)
            if file_id:
                break
        assert file_id > 0
        try:
            dec._finish(file_id)
        except pycimbar.CimbarError as exc:
            return dec, str(exc)
    return dec, None


def test_a_valid_crafted_stream_decodes():
    dec, err = _decode_stream(b"x.bin", _rle_frame(3))
    assert err is None and dec.data == b"A" * 3 * 131072 and dec.filename == "x.bin"


def test_decompression_bomb_stops_at_max_size():
    dec, err = _decode_stream(b"x.bin", _rle_frame(100), max_size=1 << 20)  # 420 B -> 13 MB
    assert err and "max_size" in err and dec.data is None


def test_truncated_compressed_data_is_an_error():
    dec, err = _decode_stream(b"x.bin", _rle_frame(20, last=False))
    assert err and "ends early" in err and dec.data is None


def test_garbage_after_the_data_is_an_error():
    dec, err = _decode_stream(b"x.bin", _rle_frame(3) + b"\xde\xad\xbe\xef" * 400)
    assert err and "corrupt" in err and dec.data is None


@pytest.mark.parametrize("name, expected", [
    (b"..", None), (b".", None), (b"a/../../b.txt", "b.txt"), (b"..\\..\\x.dll", "x.dll"), (b"C:evil", "evil"),
    (b"bad\x00name\x1b[2J.txt", "badname[2J.txt"), (b"trailing. . ", "trailing"),
    (b"\xff\xfe.bin", "��.bin"),
])
def test_file_names_are_reduced_to_a_plain_name(name, expected):
    dec, err = _decode_stream(name, _rle_frame(1))
    assert err is None and dec.filename == expected


def test_a_failed_stream_resets_the_decoder():
    enc = pycimbar.Encoder(bytes(3_000_000), filename="zeros.bin")  # compresses to almost nothing
    dec = pycimbar.Decoder(max_size=1 << 20)
    for _ in range(50):
        dec.decode(enc.next_frame())
        if dec.files_failed:
            break
    assert dec.files_failed == 1 and "max_size" in dec.error and not dec.done and dec.progress == 0.0
    # and it goes on: the same transfer, now within the limit
    dec.max_size = None
    for _ in range(50):
        if dec.decode(enc.next_frame()) is not None:
            break
    assert dec.data == bytes(3_000_000)


def test_encoder_rejects_what_would_break_the_stream():
    with pytest.raises(TypeError):
        pycimbar.Encoder(10**6)
    with pytest.raises(ValueError, match="filename"):
        pycimbar.Encoder(b"x", filename="n" * 300)
    with pytest.raises(ValueError, match="encode_id"):
        pycimbar.Encoder(b"x", encode_id=200)
