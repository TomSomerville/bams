"""Subtitles for the player: the file's own subtitle tracks plus sidecar files next to it.

- Text subtitles (SRT, ASS/SSA, WebVTT, mov_text...) are converted to WebVTT, which browsers show natively
  through <track>. Conversions are cached in the data dir (data/cache/subtitles), never next to the media.
- Image subtitles (Blu-ray PGS, DVD VobSub, DVB) can't be turned into text; the player asks the server to
  burn them into the converted video instead (`stream._transcode_parts(burn=...)`).
- Sidecars: `Movie.srt`, `Movie.en.srt`, `Movie.eng.forced.srt`, `Movie.English.sdh.srt`... in the video's
  folder. They're only read (listed, then opened read-only), like everything in a media folder.
- DVD subtitles ripped to a sidecar pair, `Movie.idx` + `Movie.sub` (VobSub), are pictures too: burned in, read
  by FFmpeg as a second input. One .idx often holds several languages; each is a track ("x{n}-{k}").
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

from babelfish import Error as LanguageError, Language

from . import readonly, stream

log = logging.getLogger(__name__)

SIDECAR_EXTS = (".srt", ".vtt", ".ass", ".ssa")
TEXT_CODECS = {"subrip", "srt", "ass", "ssa", "webvtt", "mov_text", "text", "microdvd", "subviewer", "jacosub"}
_FLAGS = {"forced": "forced", "sdh": "sdh", "cc": "sdh", "hi": "sdh", "default": "default"}


def language(code: str | None) -> tuple[str | None, str | None]:
    """('en', 'English') from 'eng', 'en', 'English', 'en-US'...; (None, None) if it isn't a language."""
    if not code or code.casefold() in ("und", "unk", "mis", "zxx"):
        return None, None
    c = code.strip()
    for make in (lambda: Language.fromietf(c), lambda: Language.fromalpha3b(c.lower()),
                 lambda: Language(c.lower()), lambda: Language.fromcode(c.title(), "name")):
        try:
            lang = make()
        except (LanguageError, ValueError, KeyError):
            continue
        try:
            alpha2 = lang.alpha2
        except LanguageError:
            alpha2 = lang.alpha3
        return alpha2, lang.name
    return None, None


def _label(lang_name: str | None, title: str | None, forced: bool, sdh: bool, fallback: str) -> str:
    parts = [lang_name or (title if title else None) or fallback]
    if title and lang_name and title.casefold() not in (lang_name.casefold(), "forced", "sdh"):
        parts.append(title)
    if forced:
        parts.append("forced")
    if sdh:
        parts.append("SDH")
    return " · ".join(parts)


def sidecars(video: Path) -> list[Path]:
    """Subtitle files that belong to `video`, sorted by name. Only the video's own folder is listed. A VobSub
    pair is listed by its .idx, and only when the .sub with the pictures is there too."""
    stem = video.stem.casefold()
    try:
        names = sorted(e.name for e in os.scandir(video.parent) if e.is_file())
    except OSError:
        return []
    lower = {n.casefold() for n in names}
    out = []
    for n in names:
        base, ext = os.path.splitext(n)
        if not (base.casefold() == stem or base.casefold().startswith(stem + ".")):
            continue
        if ext.casefold() in SIDECAR_EXTS or (ext.casefold() == ".idx" and f"{base}.sub".casefold() in lower):
            out.append(video.parent / n)
    return out


_IDX_ID = re.compile(r"^\s*id\s*:\s*([A-Za-z-]*)\s*,\s*index\s*:\s*(\d+)", re.M)


def vobsub_streams(idx: Path) -> list[str | None]:
    """The language code of each subtitle stream in a VobSub .idx, in order (FFmpeg makes one stream per `id:`
    line). Empty if it can't be read."""
    try:
        with readonly.open_ro(idx) as f:
            text = f.read(2_000_000).decode("latin-1")
    except OSError:
        return []
    return [m[1] or None for m in _IDX_ID.finditer(text)]


def tracks(probe: dict | None, video: Path | None, file_id: int) -> list[dict]:
    """Every subtitle track of a file: embedded ones ("e{n}" = the n-th subtitle stream) then sidecars ("x{n}")."""
    out = []
    for n, s in enumerate((probe or {}).get("subtitles") or []):
        code, name = language(s.get("language"))
        title = s.get("title")
        sdh = bool(title and re.search(r"\b(sdh|cc|hearing)\b", title, re.I))
        image = bool(s.get("image")) or s.get("codec") not in TEXT_CODECS
        out.append({"id": f"e{n}", "index": n, "source": "embedded", "language": code, "codec": s.get("codec"),
                    "label": _label(name, title, s.get("forced", False), sdh, f"Track {n + 1}"),
                    "forced": bool(s.get("forced")), "sdh": sdh, "image": image,
                    "url": None if image else f"/api/files/{file_id}/subtitles/e{n}.vtt"})
    for n, p in enumerate(sidecars(video) if video else []):
        tokens = p.name[len(video.stem):].split(".")[1:-1]  # "Movie.en.forced.srt" -> ["en", "forced"]
        code = name = None
        flags = set()
        for t in tokens:
            if t.casefold() in _FLAGS:
                flags.add(_FLAGS[t.casefold()])
            elif code is None:
                code, name = language(t)
        if p.suffix.casefold() == ".idx":  # DVD pictures: one track per language stream in the index
            langs = vobsub_streams(p)
            for k, lang in enumerate(langs):
                c, nm = language(lang) if lang else (code, name)
                fallback = p.name if len(langs) == 1 else f"{p.name} #{k + 1}"
                out.append({"id": f"x{n}-{k}", "index": n, "stream": k, "source": "file", "language": c,
                            "codec": "vobsub", "label": _label(nm, None, "forced" in flags, "sdh" in flags, fallback),
                            "forced": "forced" in flags, "sdh": "sdh" in flags, "image": True, "file": p.name,
                            "url": None})
            continue
        out.append({"id": f"x{n}", "index": n, "source": "file", "language": code, "codec": p.suffix[1:].lower(),
                    "label": _label(name, None, "forced" in flags, "sdh" in flags, p.name),
                    "forced": "forced" in flags, "sdh": "sdh" in flags, "image": False, "file": p.name,
                    "url": f"/api/files/{file_id}/subtitles/x{n}.vtt"})
    return out


def burn_source(track: dict, video: Path) -> int | tuple[Path, int]:
    """What `stream` paints on for a picture track: the n-th subtitle stream of the video, or (sidecar .idx, n)."""
    if track["source"] == "embedded":
        return track["index"]
    return video.parent / track["file"], track["stream"]


# ------------------------------------------------------------------ conversion

def _run_ffmpeg(args: list[str], timeout: float) -> bytes:
    exe = stream.ffmpeg_path()
    if not exe:
        raise RuntimeError("FFmpeg not found, so subtitles can't be converted")
    r = subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-nostdin", *args], capture_output=True,
                       timeout=timeout, stdin=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode(errors="replace").strip()[:300] or f"FFmpeg exit code {r.returncode}")
    return r.stdout


def _decode(data: bytes) -> str:
    """Sidecar text in whatever encoding it came in: UTF-8 (with or without BOM), UTF-16, else Windows-1252."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def webvtt(video: Path, track: dict, cache: Path, mtime_ns: int) -> str:
    """The track as WebVTT text, converted once and cached (keyed by the file's mtime, so an edited sidecar
    or replaced video is converted again)."""
    src = video if track["source"] == "embedded" else video.parent / track["file"]
    try:
        stamp = src.stat().st_mtime_ns if track["source"] == "file" else mtime_ns
    except OSError:
        stamp = mtime_ns
    key = hashlib.sha1(f"{src}|{track['id']}|{stamp}".encode()).hexdigest()[:20]
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / f"{key}.vtt"
    if out.is_file():
        return out.read_text(encoding="utf-8")
    if track["source"] == "embedded":
        # FFmpeg reads through the whole file to collect one subtitle stream: slow for a big file the first time
        vtt = _run_ffmpeg(["-i", str(video), "-map", f"0:s:{track['index']}", "-f", "webvtt", "pipe:1"],
                          timeout=600).decode("utf-8", errors="replace")
    else:
        with readonly.open_ro(src) as f:
            text = _decode(f.read(20_000_000))
        if track["codec"] == "vtt" and text.lstrip().startswith("WEBVTT"):
            vtt = text
        else:  # FFmpeg reads a UTF-8 copy in the data dir (sidecars come in any encoding)
            tmp = cache / f"{key}.src{src.suffix.lower()}"
            tmp.write_text(text, encoding="utf-8")
            try:
                vtt = _run_ffmpeg(["-i", str(tmp), "-f", "webvtt", "pipe:1"], timeout=120).decode("utf-8", errors="replace")
            finally:
                tmp.unlink(missing_ok=True)
    out.write_text(vtt, encoding="utf-8")
    return vtt


_TIME = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{3})")


def _secs(m: re.Match) -> float:
    return int(m[1] or 0) * 3600 + int(m[2]) * 60 + int(m[3]) + int(m[4]) / 1000


def _fmt(t: float) -> str:
    ms = round(t * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}"


def shift(vtt: str, by: float) -> str:
    """Cue times moved `by` seconds earlier. A live stream (remux / plain transcode) started at `by` counts its
    time from 0, so its subtitles must too. Cues that end before the stream starts are dropped."""
    if not by:
        return vtt
    blocks = re.split(r"\n\s*\n", vtt.replace("\r\n", "\n"))
    out = []
    for b in blocks:
        lines = b.split("\n")
        i = next((k for k, ln in enumerate(lines) if "-->" in ln), None)
        if i is None:
            out.append(b)  # the header, NOTE / STYLE blocks
            continue
        a, rest = lines[i].split("-->", 1)
        ma, mb = _TIME.search(a), _TIME.search(rest)
        if not ma or not mb:
            continue
        start, end = _secs(ma) - by, _secs(mb) - by
        if end <= 0:
            continue
        settings = rest[mb.end():]
        lines[i] = f"{_fmt(max(start, 0))} --> {_fmt(end)}{settings}"
        out.append("\n".join(lines))
    return "\n\n".join(out) + "\n"
