"""Minimal PNG encoding for raw RGB frames, without numpy/opencv.

The streaming pipeline keeps frames in memory as `rgb24` bytes and only writes a few sample
frames for the preview; the AI stack (which brings opencv) is optional, so this must work
with the standard library alone.
"""

from __future__ import annotations

import struct
import zlib

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)


def encode_png_rgb(data: bytes, width: int, height: int, level: int = 1) -> bytes:
    """PNG (8-bit RGB) for `width`x`height` rgb24 pixels."""
    stride = width * 3
    if len(data) != stride * height:
        raise ValueError("Frame size does not match its dimensions.")
    view = memoryview(data)
    # Cada fila lleva delante su byte de filtro (0 = ninguno).
    rows = b"".join(b"\x00" + view[row * stride : (row + 1) * stride] for row in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        PNG_SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(rows, level))
        + _chunk(b"IEND", b"")
    )


def read_png_size(data: bytes) -> tuple[int, int]:
    """Width and height from a PNG header."""
    if len(data) < 24 or not data.startswith(PNG_SIGNATURE) or data[12:16] != b"IHDR":
        raise ValueError("Not a PNG image.")
    width, height = struct.unpack(">II", data[16:24])
    return width, height
