"""Video keyframe times from a file's own index, so a copy-HLS session starts without reading the whole file.

`stream.keyframes` used to list them with ffprobe, which reads every packet: 7 to 80 s per file over a NAS (the
owner's TV waited that long at the first play of every episode). The index holds the same list in a few hundred KB:

- Matroska: the Cues (the video track's cue points).
- MP4/MOV: the sample tables (stss: which samples are keyframes; stts/ctts: their times; elst: the shift FFmpeg
  applies to them). Only plain edit lists are handled; a fragmented file has no full table.

An index can list fewer keyframes than FFmpeg (which cuts the copy) sees: in one of the owner's mkvmerge files the
container marks every other one, FFmpeg's H.264 parser flagging the I-frames between; another leaves a burst of
keyframes out of its Cues. That's fine: hls.Transcodes joins FFmpeg's extra pieces to the segment they fall in.
A listed time FFmpeg doesn't cut at would not be, so `stream.keyframes` checks a few stretches of the file against
ffprobe before trusting an index.

Times are presentation times in seconds as ffprobe gives them (`pts_time`), before the caller takes the file's
start time off. None when there's no index or it's unusual: the caller reads the packets.
"""

from __future__ import annotations

import logging
import struct
from pathlib import Path

from . import readonly

log = logging.getLogger(__name__)

MAX_ELEMENT = 64 << 20  # an index bigger than this isn't read


def read(path: Path) -> list[float] | None:
    """Keyframe presentation times (s) of the first video stream, from the index; None to read the packets."""
    try:
        with readonly.open_ro(path) as f:
            head = _read(f, 12)
            if head[:4] == b"\x1a\x45\xdf\xa3":
                return _matroska(f)
            if head[4:8] in (b"ftyp", b"moov", b"free", b"skip", b"wide", b"mdat", b"pnot"):
                return _mp4(f)
    except (OSError, ValueError, IndexError, struct.error) as e:
        log.info("keyframe index of %s not used: %s", path.name, e)
    return None


def _read(f, n: int) -> bytes:
    """n bytes (fewer only at the end of the file): the media files are opened unbuffered."""
    out = b""
    while len(out) < n:
        b = f.read(n - len(out))
        if not b:
            break
        out += b
    return out


# ---------------------------------------------------------------- Matroska

EBML_ID, SEGMENT, SEEK_HEAD, SEEK, SEEK_ID, SEEK_POSITION = 0x1A45DFA3, 0x18538067, 0x114D9B74, 0x4DBB, 0x53AB, 0x53AC
INFO, TIMESTAMP_SCALE, TRACKS, TRACK_ENTRY, TRACK_NUMBER, TRACK_TYPE = 0x1549A966, 0x2AD7B1, 0x1654AE6B, 0xAE, 0xD7, 0x83
CUES, CUE_POINT, CUE_TIME, CUE_POSITIONS, CUE_TRACK = 0x1C53BB6B, 0xBB, 0xB3, 0xB7, 0xF7
CLUSTER = 0x1F43B675


def _vint(data: bytes, i: int, marker: bool) -> tuple[int | None, int]:
    """An EBML variable-length number at i: (value, length). Ids keep their length marker; a size of all ones
    (unknown, as in live recordings) is None."""
    first = data[i]
    n = 1
    while n <= 8 and not first & (0x80 >> (n - 1)):
        n += 1
    if n > 8:
        raise ValueError("not EBML")
    v = first if marker else first & (0xFF >> n)
    for b in data[i + 1:i + n]:
        v = (v << 8) | b
    if len(data) < i + n:
        raise ValueError("cut short")
    if not marker and v == (1 << (7 * n)) - 1:
        return None, n
    return v, n


def _header(f) -> tuple[int, int | None, int]:
    """The element header at the file position: (id, size, header length)."""
    data = _read(f, 12)
    if not data:
        raise EOFError
    eid, a = _vint(data, 0, True)
    size, b = _vint(data, a, False)
    f.seek(a + b - len(data), 1)
    return eid, size, a + b


def _children(data: bytes):
    i = 0
    while i < len(data):
        eid, a = _vint(data, i, True)
        size, b = _vint(data, i + a, False)
        if size is None:
            raise ValueError("unknown size inside an element")
        start = i + a + b
        yield eid, data[start:start + size]
        i = start + size


def _uint(b: bytes) -> int:
    return int.from_bytes(b, "big")


def _matroska(f) -> list[float] | None:
    f.seek(0)
    eid, size, _ = _header(f)
    if eid != EBML_ID or size is None:
        return None
    f.seek(size, 1)
    eid, _, _ = _header(f)
    if eid != SEGMENT:
        return None
    base = f.tell()  # SeekHead positions count from here
    found: dict[int, bytes] = {}
    where: dict[int, int] = {}
    # the elements before the first cluster (the Cues are usually at the end: the SeekHead says where)
    while True:
        try:
            at = f.tell()
            eid, size, _ = _header(f)
        except (EOFError, ValueError):
            break
        if eid == CLUSTER or size is None:
            break
        if eid in (SEEK_HEAD, INFO, TRACKS, CUES) and eid not in found and size <= MAX_ELEMENT:
            found[eid] = _read(f, size)
            if eid == SEEK_HEAD:
                where.update(_seek_head(found[eid], base))
        else:
            f.seek(size, 1)
        if f.tell() <= at:
            break
    for eid in (INFO, TRACKS, CUES):
        if eid not in found and eid in where:
            f.seek(where[eid])
            got, size, _ = _header(f)
            if got == eid and size is not None and size <= MAX_ELEMENT:
                found[eid] = _read(f, size)
    if TRACKS not in found or CUES not in found:
        return None
    scale = 1_000_000
    for eid, b in _children(found.get(INFO, b"")):
        if eid == TIMESTAMP_SCALE:
            scale = _uint(b)
    video = None
    for eid, b in _children(found[TRACKS]):
        if eid == TRACK_ENTRY:
            t = dict(_children(b))
            if _uint(t.get(TRACK_TYPE, b"")) == 1:
                video = _uint(t.get(TRACK_NUMBER, b""))
                break
    if not video:
        return None
    cues = set()  # times in ticks
    for eid, b in _children(found[CUES]):
        if eid != CUE_POINT:
            continue
        t, ours = None, False
        for k, v in _children(b):
            if k == CUE_TIME:
                t = _uint(v)
            elif k == CUE_POSITIONS:
                p = dict(_children(v))
                ours = ours or _uint(p.get(CUE_TRACK, b"")) == video
        if t is not None and ours:
            cues.add(t)
    if not cues:
        return None
    return [t * scale / 1e9 for t in sorted(cues)]


def _seek_head(data: bytes, base: int) -> dict[int, int]:
    out = {}
    for eid, b in _children(data):
        if eid == SEEK:
            s = dict(_children(b))
            if SEEK_ID in s and SEEK_POSITION in s:
                out.setdefault(_uint(s[SEEK_ID]), base + _uint(s[SEEK_POSITION]))
    return out


# ---------------------------------------------------------------- MP4 / MOV

def _boxes(data: bytes, i: int = 0, end: int | None = None):
    end = len(data) if end is None else end
    while i + 8 <= end:
        size, kind = struct.unpack_from(">I4s", data, i)
        head = 8
        if size == 1:
            size, head = struct.unpack_from(">Q", data, i + 8)[0], 16
        elif size == 0:
            size = end - i
        if size < head or i + size > end:
            return
        yield kind, data[i + head:i + size]
        i += size


def _mp4(f) -> list[float] | None:
    f.seek(0)
    moov = None
    while True:
        head = _read(f, 16)
        if len(head) < 8:
            break
        size, kind = struct.unpack_from(">I4s", head)
        hl = 8
        if size == 1:
            size, hl = struct.unpack_from(">Q", head, 8)[0], 16
        if kind == b"moov":
            if size < hl or size > MAX_ELEMENT:
                return None
            f.seek(hl - len(head), 1)
            moov = _read(f, size - hl)
            break
        if size < hl:  # 0 = to the end of the file: no moov after it
            break
        f.seek(size - len(head), 1)
    if moov is None:
        return None
    boxes = list(_boxes(moov))
    if any(k == b"mvex" for k, _ in boxes):
        return None  # fragmented: the samples are described in the fragments
    movie_scale = 0
    for k, b in boxes:
        if k == b"mvhd":
            movie_scale = struct.unpack_from(">I", b, 20 if b[0] == 1 else 12)[0]
    for k, b in boxes:
        if k == b"trak":
            t = _video_track(b, movie_scale)
            if t is not False:
                return t  # the first video track (ffprobe's v:0), or None if it can't be read
    return None


def _video_track(trak: bytes, movie_scale: int):
    """Keyframe times of a video track, None if its tables can't be used, False if it isn't video."""
    parts = dict(_boxes(trak))
    mdia = dict(_boxes(parts.get(b"mdia", b"")))
    hdlr = mdia.get(b"hdlr", b"")
    if hdlr[8:12] != b"vide":
        return False
    mdhd = mdia.get(b"mdhd", b"")
    scale = struct.unpack_from(">I", mdhd, 20 if mdhd[0] == 1 else 12)[0]
    stbl = dict(_boxes(dict(_boxes(mdia.get(b"minf", b""))).get(b"stbl", b"")))
    if not scale or b"stts" not in stbl:
        return None
    # the shift FFmpeg's demuxer applies: an empty edit delays the track, a media time drops what's before it
    empty, media_time = 0, 0
    elst = dict(_boxes(parts.get(b"edts", b""))).get(b"elst")
    if elst:
        v1 = elst[0] == 1
        n = struct.unpack_from(">I", elst, 4)[0]
        entries = [struct.unpack_from(">QqhH" if v1 else ">IihH", elst, 8 + i * (20 if v1 else 12)) for i in range(n)]
        if entries and entries[0][1] == -1:
            empty = entries[0][0]
            entries = entries[1:]
        if len(entries) > 1 or any(rate != 1 or frac for _, _, rate, frac in entries):
            return None  # several edits or another speed: let ffprobe work it out
        if entries:
            media_time = entries[0][1]
        if empty:
            if not movie_scale:
                return None
            empty = empty * scale // movie_scale
    stts = stbl[b"stts"]
    deltas = []
    for i in range(struct.unpack_from(">I", stts, 4)[0]):
        count, delta = struct.unpack_from(">II", stts, 8 + i * 8)
        deltas.append((count, delta))
    total = sum(c for c, _ in deltas)
    offsets = None
    if b"ctts" in stbl:
        ctts = stbl[b"ctts"]
        offsets = []
        for i in range(struct.unpack_from(">I", ctts, 4)[0]):
            offsets.append(struct.unpack_from(">Ii", ctts, 8 + i * 8))
    if b"stss" in stbl:
        stss = stbl[b"stss"]
        keys = sorted(struct.unpack_from(">I", stss, 8 + i * 4)[0] - 1 for i in range(struct.unpack_from(">I", stss, 4)[0]))
    else:
        keys = list(range(total))  # no table: every sample is a keyframe
    out = []
    want = iter(keys)
    k = next(want, None)
    sample, dts = 0, 0
    run = iter(offsets or [])
    left, off = 0, 0
    for count, delta in deltas:
        for _ in range(count):
            if offsets is not None:
                while left == 0:
                    left, off = next(run, (None, 0))
                    if left is None:
                        return None  # fewer offsets than samples
                left -= 1
            while k is not None and k < sample:
                k = next(want, None)
            if k == sample:
                out.append((dts + off - media_time + empty) / scale)
            sample += 1
            dts += delta
    return out or None
