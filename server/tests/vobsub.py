"""Writes DVD (VobSub) subtitle sidecars, `.idx` + `.sub`, for tests.

The .sub is an MPEG program stream with one subtitle picture (SPU) per 2048-byte pack, in private stream 1
(substream 0x20 + stream number). The .idx is text: frame size, the 16-colour palette, then per stream a
language and the time + byte position of each picture. A picture is 2 bits per pixel, run-length coded, the
even lines (top field) then the odd ones.
"""

from __future__ import annotations

import struct
from pathlib import Path

PALETTE = ["000000", "ffffff", "808080", "000000"] + ["000000"] * 12


def _rle_line(row: list[int]) -> bytes:
    """One line of 2-bit colour indexes, run-length coded in nibbles, padded to a whole byte."""
    bits = ""
    i = 0
    while i < len(row):
        c, n = row[i], 1
        while i + n < len(row) and row[i + n] == c and n < 255:
            n += 1
        if i + n == len(row):
            bits += "0" * 14 + f"{c:02b}"           # the rest of the line in this colour
        elif n < 4:
            bits += f"{n:02b}{c:02b}"
        elif n < 16:
            bits += f"00{n:04b}{c:02b}"
        elif n < 64:
            bits += f"0000{n:06b}{c:02b}"
        else:
            bits += f"000000{n:08b}{c:02b}"
        i += n
    bits += "0" * (-len(bits) % 8)
    return int(bits, 2).to_bytes(len(bits) // 8, "big")


def spu(bitmap: list[list[int]], x: int, y: int, duration: float) -> bytes:
    """One subtitle picture: shown at its idx time for `duration` seconds. Colour 1 is opaque, 0 transparent."""
    h, w = len(bitmap), len(bitmap[0])
    top = b"".join(_rle_line(r) for r in bitmap[0::2])
    bottom = b"".join(_rle_line(r) for r in bitmap[1::2])
    pix = top + bottom
    first = 4 + len(pix)                            # control sequences follow the pixels
    coords = (x << 36) | ((x + w - 1) << 24) | (y << 12) | (y + h - 1)
    cmds = (b"\x01" + b"\x03" + struct.pack(">H", 0x3210) + b"\x04" + struct.pack(">H", 0x0FF0)
            + b"\x05" + coords.to_bytes(6, "big") + b"\x06" + struct.pack(">HH", 4, 4 + len(top)) + b"\xff")
    second = first + 4 + len(cmds)
    seq1 = struct.pack(">HH", 0, second) + cmds
    seq2 = struct.pack(">HH", round(duration * 90000 / 1024), second) + b"\x02\xff"
    body = pix + seq1 + seq2
    return struct.pack(">HH", 4 + len(body), first) + body


def _pts(t: float) -> bytes:
    v = round(t * 90000)
    return bytes([0x21 | ((v >> 29) & 0x0E), (v >> 22) & 0xFF, 0x01 | ((v >> 14) & 0xFE), (v >> 7) & 0xFF,
                  0x01 | ((v << 1) & 0xFE)])


def _pack(stream: int, t: float, data: bytes) -> bytes:
    """A picture in as many 2048-byte packs as it needs; only the first carries the time (PTS)."""
    scr = b"\x44\x00\x04\x00\x04\x01\x01\x89\xc3\xf8"  # pack header: SCR 0, mux rate, no stuffing
    out = b""
    first = True
    while data or first:
        head = b"\x81\x80\x05" + _pts(t) if first else b"\x81\x00\x00"
        room = 2048 - 14 - 6 - len(head) - 1             # pack header, PES header, substream byte
        chunk, data = data[:room], data[room:]
        pes_body = head + bytes([0x20 + stream]) + chunk
        pack = b"\x00\x00\x01\xba" + scr + b"\x00\x00\x01\xbd" + struct.pack(">H", len(pes_body)) + pes_body
        pad = 2048 - len(pack)
        if pad >= 6:
            pack += b"\x00\x00\x01\xbe" + struct.pack(">H", pad - 6) + b"\xff" * (pad - 6)
        else:  # too little room for a padding packet: stuff the PES header instead
            pes_body = head[:2] + bytes([head[2] + pad]) + head[3:] + b"\xff" * pad + bytes([0x20 + stream]) + chunk
            pack = b"\x00\x00\x01\xba" + scr + b"\x00\x00\x01\xbd" + struct.pack(">H", len(pes_body)) + pes_body
        out += pack
        first = False
    return out


def write(idx: Path, size: tuple[int, int], streams: list[tuple[str, list[tuple[float, float, list[list[int]], int, int]]]],
          palette: list[str] = PALETTE) -> None:
    """`idx` and the .sub next to it. streams: [(language, [(start, end, bitmap, x, y), ...]), ...]."""
    sub = bytearray()
    lines = ["# VobSub index file, v7 (do not modify this line!)", f"size: {size[0]}x{size[1]}",
             "palette: " + ", ".join(palette), ""]
    for n, (lang, cues) in enumerate(streams):
        lines.append(f"id: {lang}, index: {n}")
        for start, end, bitmap, x, y in cues:
            ms = round(start * 1000)
            stamp = f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}:{ms % 1000:03d}"
            lines.append(f"timestamp: {stamp}, filepos: {len(sub):09x}")
            sub += _pack(n, start, spu(bitmap, x, y, end - start))
        lines.append("")
    idx.write_text("\n".join(lines), encoding="ascii")
    idx.with_suffix(".sub").write_bytes(bytes(sub))


def box(w: int, h: int) -> list[list[int]]:
    return [[1] * w for _ in range(h)]
