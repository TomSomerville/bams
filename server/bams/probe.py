"""Technical info (container, codecs, resolution, HDR, tracks) via ffprobe.

ffprobe is optional: without it BAMS still indexes and matches files, it just doesn't know
their codecs yet (and falls back to what the filename claims). FFmpeg is never bundled;
install it from your OS (apt install ffmpeg / winget install Gyan.FFmpeg).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_CONTAINERS = {"matroska": "MKV", "webm": "WebM", "mov": "MP4", "mp4": "MP4", "avi": "AVI",
               "mpegts": "TS", "asf": "WMV", "mpeg": "MPEG", "flv": "FLV", "ogg": "OGG",
               "mp3": "MP3", "flac": "FLAC", "wav": "WAV", "aiff": "AIFF", "aac": "AAC", "ape": "APE",
               "wv": "WavPack", "dsf": "DSF", "iff": "DFF", "ac3": "AC3", "dts": "DTS"}
_VCODECS = {"h264": "H.264", "hevc": "HEVC", "av1": "AV1", "vp9": "VP9", "vp8": "VP8",
            "mpeg4": "MPEG-4", "mpeg2video": "MPEG-2", "mpeg1video": "MPEG-1", "vc1": "VC-1", "wmv3": "WMV"}
_ACODECS = {"aac": "AAC", "ac3": "AC3", "eac3": "EAC3", "dts": "DTS", "truehd": "TrueHD", "mp3": "MP3",
            "flac": "FLAC", "opus": "Opus", "vorbis": "Vorbis", "pcm_s16le": "PCM", "alac": "ALAC", "mp2": "MP2", "ape": "APE",
            "wavpack": "WavPack", "wmav1": "WMA", "wmav2": "WMA", "wmapro": "WMA Pro", "wmalossless": "WMA Lossless",
            "dsd_lsbf": "DSD", "dsd_msbf": "DSD", "dsd_lsbf_planar": "DSD", "dsd_msbf_planar": "DSD"}
_IMAGE_SUBS = {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub"}

# Music tags kept from ffprobe (it already maps ID3/MP4 names to these), plus spellings other taggers use.
_TAG_ALIASES = {
    "title": "title", "artist": "artist", "album": "album", "genre": "genre", "date": "date",
    "album_artist": "album_artist", "albumartist": "album_artist", "album artist": "album_artist",
    "track": "track", "tracknumber": "track", "disc": "disc", "discnumber": "disc",
    "year": "date", "originaldate": "originaldate", "original_year": "originaldate",
    "compilation": "compilation", "itunescompilation": "compilation",
    "musicbrainz_albumid": "musicbrainz_albumid", "musicbrainz album id": "musicbrainz_albumid",
    "musicbrainz_artistid": "musicbrainz_artistid", "musicbrainz artist id": "musicbrainz_artistid",
    "musicbrainz_albumartistid": "musicbrainz_albumartistid",
    "musicbrainz album artist id": "musicbrainz_albumartistid",
    "musicbrainz_trackid": "musicbrainz_trackid", "musicbrainz release track id": "musicbrainz_releasetrackid",
}


def music_tags(*sources: dict) -> dict:
    """The tags BAMS uses, lower-cased and de-aliased. Containers differ in where tags live
    (format level for MP3/FLAC/MP4, the audio stream for Ogg/Opus), so several sources merge."""
    out: dict = {}
    for src in sources:
        for k, v in (src or {}).items():
            key = _TAG_ALIASES.get(k.casefold())
            if key and key not in out and str(v).strip():
                out[key] = str(v).strip()[:500]
    return out


def _windows_candidates() -> list[str]:
    # winget puts a shim in WinGet\Links; it's only on PATH for terminals opened after the install
    import glob
    local = os.environ.get("LOCALAPPDATA", "")
    winget = os.path.join(local, "Microsoft", "WinGet")
    return [os.path.join(winget, "Links", "ffprobe.exe"),
            *sorted(glob.glob(os.path.join(winget, "Packages", "*FFmpeg*", "*", "bin", "ffprobe.exe")), reverse=True),
            os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "ffmpeg", "bin", "ffprobe.exe"),
            r"C:\ffmpeg\bin\ffprobe.exe"]


def ffprobe_path() -> str | None:
    found = os.environ.get("BAMS_FFPROBE") or shutil.which("ffprobe")
    if not found and sys.platform == "win32":
        found = next((c for c in _windows_candidates() if os.path.isfile(c)), None)
    return found


def _resolution(w: int, h: int) -> str:
    # by width too, so 1920x800 scope films still count as 1080p
    if w >= 3200 or h >= 1800:
        return "4K"
    if w >= 1800 or h >= 1000:
        return "1080p"
    if w >= 1200 or h >= 700:
        return "720p"
    return "SD" if h < 500 else f"{h}p"


def summarize(data: dict) -> dict:
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    names = (fmt.get("format_name") or "").split(",")
    container = next((_CONTAINERS[n] for n in names if n in _CONTAINERS), names[0].upper() if names[0] else None)
    out: dict = {
        "container": container,
        "duration": round(float(fmt["duration"]), 1) if fmt.get("duration") else None,
        "bitrate": int(fmt["bit_rate"]) if fmt.get("bit_rate") else None,
        "video": None, "audio": [], "subtitles": [], "cover": False,
    }
    for s in streams:
        tags = s.get("tags", {})
        lang = tags.get("language")
        disp = s.get("disposition", {})
        t = s.get("codec_type")
        if t == "video" and disp.get("attached_pic"):
            out["cover"] = True  # a picture embedded in the file (album art)
        elif t == "video" and out["video"] is None:
            codec = s.get("codec_name", "")
            label = _VCODECS.get(codec, codec.upper())
            if codec == "mpeg4" and (s.get("codec_tag_string", "").lower() in ("xvid", "divx", "dx50")):
                label = s["codec_tag_string"].capitalize()
            w, h = s.get("width") or 0, s.get("height") or 0
            hdr = dv_profile = None
            dovi = next((sd for sd in s.get("side_data_list", []) if sd.get("side_data_type", "").startswith("DOVI")), None)
            if dovi:
                hdr = "Dolby Vision"
                dv_profile = dovi.get("dv_profile")  # 5 = no HDR10 base layer: needs the DV metadata applied
            elif s.get("color_transfer") == "smpte2084":
                hdr = "HDR10"
            elif s.get("color_transfer") == "arib-std-b67":
                hdr = "HLG"
            out["video"] = {
                "codec": label, "profile": s.get("profile"), "width": w, "height": h,
                "resolution": _resolution(w, h) if w and h else None, "hdr": hdr, "dv_profile": dv_profile,
                "bit_depth": 10 if "10" in (s.get("pix_fmt") or "") else 8,
                "fps": s.get("avg_frame_rate"),
            }
        elif t == "audio":
            codec = s.get("codec_name", "")
            if codec.startswith("pcm_"):
                codec = "pcm_s16le"  # any PCM: the container decides whether browsers take it
            out["audio"].append({
                "codec": _ACODECS.get(codec, codec.upper()), "channels": s.get("channels"),
                "layout": s.get("channel_layout"), "language": lang, "title": tags.get("title"),
                "default": bool(disp.get("default")),
                "sample_rate": int(s["sample_rate"]) if s.get("sample_rate") else None,
                "bit_depth": int(s["bits_per_raw_sample"]) if s.get("bits_per_raw_sample") else None,
            })
        elif t == "subtitle":
            codec = s.get("codec_name", "")
            out["subtitles"].append({
                "codec": codec, "language": lang, "title": tags.get("title"),
                "forced": bool(disp.get("forced")), "image": codec in _IMAGE_SUBS,
            })
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    tags = music_tags(fmt.get("tags") or {}, (audio_streams[0].get("tags") or {}) if audio_streams else {})
    if tags:
        out["tags"] = tags
    return out


def probe(path: Path, timeout: float = 90) -> dict | None:
    exe = ffprobe_path()
    if not exe:
        return None
    cmd = [exe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("ffprobe failed on %s: %s", path, e)
        return None
    if r.returncode != 0:
        log.warning("ffprobe error on %s: %s", path, r.stderr.decode(errors="replace").strip()[:300])
        return None
    try:
        return summarize(json.loads(r.stdout))
    except (ValueError, KeyError, TypeError) as e:
        log.warning("ffprobe output unreadable for %s: %s", path, e)
        return None
