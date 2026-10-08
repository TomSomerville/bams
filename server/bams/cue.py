"""CUE sheets: one audio file holding a whole album (a CD image), split into tracks by a `.cue` text file.

    PERFORMER "Pink Floyd"
    TITLE "The Wall"
    REM DATE 1979
    FILE "The Wall.flac" WAVE
      TRACK 01 AUDIO
        TITLE "In the Flesh?"
        INDEX 01 00:00:00
      TRACK 02 AUDIO
        TITLE "The Thin Ice"
        INDEX 00 03:17:20       <- pregap: stays at the end of track 1 (how CD players and foobar2000 play it)
        INDEX 01 03:19:40       <- mm:ss:ff, 75 frames a second

The sheet sits next to the audio file (read-only, like everything in a media folder) or is embedded in a FLAC
file's tags (CUESHEET, which ffprobe reports). A track runs from its INDEX 01 to the next track's INDEX 01 in
the same file; the last one runs to the end of the file.
"""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass, field

_INDEX_RE = re.compile(r"^(\d+):(\d{1,2}):(\d{1,2})$")


@dataclass
class CueTrack:
    number: int
    title: str | None = None
    performer: str | None = None
    start: float = 0.0              # seconds into the file
    end: float | None = None        # None = the end of the file


@dataclass
class CueFile:
    name: str                       # as written in the sheet, '/'-separated (often a stale .wav name for a .flac)
    tracks: list[CueTrack] = field(default_factory=list)


@dataclass
class CueSheet:
    title: str | None = None
    performer: str | None = None
    date: str | None = None
    genre: str | None = None
    files: list[CueFile] = field(default_factory=list)


def _time(v: str) -> float | None:
    m = _INDEX_RE.match(v.strip())
    if not m:
        return None
    mm, ss, ff = (int(x) for x in m.groups())
    return mm * 60 + ss + ff / 75


def _args(rest: str) -> list[str]:
    try:
        return shlex.split(rest, posix=True)
    except ValueError:  # an unbalanced quote: take the rest as it is
        return [rest.strip().strip('"')]


def parse(text: str) -> CueSheet:
    """Never raises: a damaged sheet gives whatever could be read (maybe no tracks)."""
    sheet = CueSheet()
    cur_file: CueFile | None = None
    cur: CueTrack | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        cmd, _, rest = line.partition(" ")
        cmd = cmd.upper()
        if cmd == "FILE":
            a = _args(rest.replace("\\", "/"))  # a backslash would be an escape to shlex
            # FILE "name with spaces.flac" WAVE -> the name is everything but the trailing type
            name = " ".join(a[:-1]) if len(a) > 1 else (a[0] if a else "")
            cur_file, cur = CueFile(name), None
            sheet.files.append(cur_file)
        elif cmd == "TRACK":
            a = rest.split()
            if cur_file is None or not a or not a[0].isdigit():
                cur = None
                continue
            is_audio = len(a) < 2 or a[1].upper() == "AUDIO"
            cur = CueTrack(int(a[0])) if is_audio else None
            if cur:
                cur_file.tracks.append(cur)
        elif cmd in ("TITLE", "PERFORMER"):
            v = " ".join(_args(rest)).strip() or None
            target = cur if cur is not None else (sheet if cur_file is None else None)
            if target is not None:
                setattr(target, cmd.lower(), v)
        elif cmd == "INDEX" and cur is not None:
            a = rest.split()
            if len(a) == 2 and a[0].isdigit() and int(a[0]) == 1 and (t := _time(a[1])) is not None:
                cur.start = t
        elif cmd == "REM" and cur_file is None:
            key, _, v = rest.partition(" ")
            v = " ".join(_args(v)).strip() or None
            if key.upper() == "DATE":
                sheet.date = v
            elif key.upper() == "GENRE":
                sheet.genre = v
    for f in sheet.files:
        f.tracks.sort(key=lambda t: t.start)
        for a, b in zip(f.tracks, f.tracks[1:]):
            a.end = b.start
    return sheet


def file_for(sheet: CueSheet, audio_name: str, *, only_audio_file: bool = False) -> CueFile | None:
    """The sheet's FILE block for this audio file: the same name, else the same name with another extension
    (the sheet was made for a .wav that was then compressed to .flac/.ape), else, when this is the only audio
    file next to a single-FILE sheet, that one."""
    if not sheet.files:
        return None
    def base(name: str) -> str:
        return name.rsplit("/", 1)[-1]

    want, want_stem = audio_name.casefold(), os.path.splitext(audio_name)[0].casefold()
    for f in sheet.files:
        if base(f.name).casefold() == want:
            return f
    for f in sheet.files:
        if os.path.splitext(base(f.name))[0].casefold() == want_stem:
            return f
    if only_audio_file and len(sheet.files) == 1:
        return sheet.files[0]
    return None


def splits(f: CueFile | None) -> bool:
    """Does this FILE block really cut the file into tracks? (A sheet describing one track per file doesn't.)"""
    return f is not None and len(f.tracks) >= 2
