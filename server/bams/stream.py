"""How a file gets to the browser: as-is, remuxed, or transcoded on the fly by FFmpeg.

Browsers decode H.264 (and HEVC on most Windows/Mac machines) and AAC/MP3/Opus audio, but not the
Dolby (AC3/EAC3), DTS or TrueHD audio that most TV/movie releases carry: those play silently.
For such files the server runs FFmpeg to copy the video untouched and convert only the audio to
AAC, streamed as fragmented MP4. That costs a little CPU and loses no video quality.

Video no browser decodes (Xvid, MPEG-2, VC-1, 10-bit H.264...), or HEVC/AV1 on a browser that
can't (the player asks for it), is transcoded to H.264 + AAC, on the GPU when there is one.

FFmpeg only ever READS the media file (input) and writes to a pipe (stdout), never to disk.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from . import probe

log = logging.getLogger(__name__)

BROWSER_AUDIO = {"AAC", "MP3", "Opus", "Vorbis", "FLAC"}
# guessit's names for the same codecs (used before ffprobe has seen a file)
_GUESSIT_AUDIO = {"AAC": "AAC", "MP3": "MP3", "Opus": "Opus", "Dolby Digital": "AC3",
                  "Dolby Digital Plus": "EAC3", "DTS": "DTS", "DTS-HD": "DTS", "Dolby TrueHD": "TrueHD",
                  "Dolby Atmos": "EAC3", "FLAC": "FLAC"}
COPYABLE_VIDEO = {"H.264", "HEVC", "AV1", "VP9", "VP8"}  # browsers may decode these; anything else is transcoded
FILE_OK_CONTAINERS = {"MP4", "MKV", "WebM"}       # Chromium plays these directly when the codecs are fine


def ffmpeg_path() -> str | None:
    if exe := os.environ.get("BAMS_FFMPEG") or shutil.which("ffmpeg"):
        return exe
    fp = probe.ffprobe_path()  # usually installed side by side
    if fp:
        sib = Path(fp).with_name("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
        if sib.is_file():
            return str(sib)
    return None


def plan(probe_info: dict | None, parse_info: dict | None) -> dict:
    """Decide how to play a file in a browser.

    method: direct_play  (MP4 + H.264 + AAC: plays as-is everywhere)
            direct_stream (video is fine; container and/or audio need help)
            transcode     (the video codec itself isn't browser-friendly)
    mode:   "file"      -> stream the original bytes (Range/seeking supported)
            "remux"     -> FFmpeg copies video, converts audio to AAC (seek by restarting at ?t=)
            "transcode" -> FFmpeg converts video to H.264 and audio to AAC (seek by restarting at ?t=)
    HEVC/AV1/VP9 count as browser-friendly here: only the client knows whether it decodes them, so
    a player that can't switches to the transcode stream itself.
    """
    profile = bit_depth = None
    if probe_info and probe_info.get("video"):
        container = probe_info.get("container")
        vcodec = probe_info["video"].get("codec")
        profile, bit_depth = probe_info["video"].get("profile"), probe_info["video"].get("bit_depth")
        audio = [a.get("codec") for a in probe_info.get("audio", [])]
        duration = probe_info.get("duration")
        source = "ffprobe"
    else:  # not probed yet: what the release name claims
        rel = (parse_info or {}).get("release", {})
        container, vcodec, duration, source = None, rel.get("video_codec"), None, "filename"
        vcodec = {"H.265": "HEVC"}.get(vcodec, vcodec)
        a = _GUESSIT_AUDIO.get(rel.get("audio_codec") or "", rel.get("audio_codec"))
        audio = [a] if a else []

    first_audio = audio[0] if audio else None
    audio_ok = first_audio is None or first_audio in BROWSER_AUDIO
    video_ok = vcodec is None or video_copyable(vcodec, profile, bit_depth)  # unknown codec: try the file

    if not video_ok:
        method, mode = "transcode", "transcode"
    elif vcodec == "H.264" and container == "MP4" and audio_ok:
        method, mode = "direct_play", "file"
    elif audio_ok and (container in FILE_OK_CONTAINERS or container is None):
        method, mode = "direct_stream", "file"
    elif vcodec == "VP8":  # VP8 belongs in WebM, not in the MP4 a remux makes
        method, mode = "transcode", "transcode"
    else:
        method, mode = "direct_stream", "remux"
    if mode != "file" and not ffmpeg_path():
        mode = "file"  # best effort: the video may play without sound, or not at all
    return {"method": method, "mode": mode, "source": source, "video_codec": vcodec, "audio_codec": first_audio,
            "audio_ok": audio_ok, "duration": duration}


def remux_start(path: Path, t: float) -> float:
    """Where a remux asked to start at `t` really starts.

    Copying video means starting on a keyframe, and FFmpeg's input seek doesn't always pick the
    nearest one (in MKV it can land a keyframe earlier). Rather than predict it, run the very same
    seek as a dry run: keep the original timestamps, stop after one video frame, read its time."""
    if t <= 0:
        return 0.0
    exe = ffmpeg_path()
    if not exe:
        return t
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-nostdin", "-ss", f"{t:.3f}", "-i", str(path),
           "-map", "0:v:0", "-c:v", "copy", "-copyts", "-frames:v", "1", "-f", "framemd5", "pipe:1"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=20, stdin=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0)
    except (OSError, subprocess.TimeoutExpired):
        return t
    tb = None
    for line in r.stdout.decode(errors="replace").splitlines():
        if line.startswith("#tb 0:"):  # "#tb 0: 1/1000"
            num, den = line.split(":", 1)[1].strip().split("/")
            tb = int(num) / int(den)
        elif line and not line.startswith("#") and tb:
            fields = [f.strip() for f in line.split(",")]  # stream, dts, pts, duration, size, hash
            try:
                return max(0.0, int(fields[2]) * tb)
            except (IndexError, ValueError):
                break
    return t


def remux_cmd(path: Path, start: float, video_codec: str | None, audio_index: int = 0) -> list[str]:
    exe = ffmpeg_path()
    if not exe:
        raise RuntimeError("FFmpeg not found")
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-nostdin"]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]  # input seek: jumps to the keyframe at/before `start`
    cmd += ["-i", str(path),
            "-map", "0:v:0", "-map", f"0:a:{audio_index}?",
            "-c:v", "copy"]
    if video_codec == "HEVC":
        cmd += ["-tag:v", "hvc1"]  # the tag browsers expect for HEVC in MP4
    cmd += ["-c:a", "aac", "-ac", "2", "-b:a", "192k",
            "-sn", "-dn", "-map_metadata", "-1", "-avoid_negative_ts", "make_zero",
            "-f", "mp4", "-movflags", "frag_keyframe+empty_moov+default_base_moof",
            "pipe:1"]
    return cmd


def video_copyable(vcodec: str | None, profile: str | None = None, bit_depth: int | None = None) -> bool:
    """Whether a browser may decode this video as-is. H.264 only in 8-bit 4:2:0: High 10 ("Hi10P"
    anime releases), 4:2:2 and 4:4:4 decode in no browser."""
    if vcodec not in COPYABLE_VIDEO:
        return False
    if vcodec == "H.264":
        prof = (profile or "").casefold()
        return (bit_depth or 8) <= 8 and not any(p in prof for p in ("high 10", "4:2:2", "4:4:4"))
    return True


# ------------------------------------------------------------------ video transcoding

# H.264 encoders, best first. Each is tried once with a tiny test encode and the first that works
# is used. Hardware: NVIDIA NVENC, Intel Quick Sync, AMD AMF, VAAPI (Linux: Intel/AMD). Software:
# libx264, then Windows Media Foundation for FFmpeg builds without libx264.
ENCODERS = ["h264_nvenc", "h264_qsv", "h264_amf", "h264_vaapi", "libx264", "h264_mf"]
ENCODER_NAMES = {"h264_nvenc": "NVIDIA NVENC", "h264_qsv": "Intel Quick Sync", "h264_amf": "AMD AMF",
                 "h264_vaapi": "VAAPI", "libx264": "x264 (CPU)", "h264_mf": "Media Foundation"}
HARDWARE = {"h264_nvenc", "h264_qsv", "h264_amf", "h264_vaapi"}
_PLATFORM_ONLY = {"h264_vaapi": "linux", "h264_mf": "win32"}
_detect_lock = threading.Lock()
_detected: dict[str, str | None] = {}  # ffmpeg path -> encoder
_filters: dict[str, set[str]] = {}     # ffmpeg path -> filter names


def vaapi_device() -> str:
    return os.environ.get("BAMS_VAAPI_DEVICE", "/dev/dri/renderD128")


def _run(cmd: list[str], timeout: float) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _encoder_works(exe: str, enc: str) -> bool:
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-nostdin"]
    vf = "format=yuv420p"
    if enc == "h264_vaapi":
        cmd += ["-vaapi_device", vaapi_device()]
        vf = "format=nv12,hwupload"
    cmd += ["-f", "lavfi", "-i", "color=black:size=256x256:rate=25:duration=0.2",
            "-vf", vf, "-frames:v", "2", "-c:v", enc, "-f", "null", "-"]
    r = _run(cmd, timeout=15)
    return r is not None and r.returncode == 0


def video_encoder() -> str | None:
    """The H.264 encoder transcodes use: detected once per FFmpeg, or forced with `BAMS_VIDEO_ENCODER`."""
    exe = ffmpeg_path()
    if not exe:
        return None
    with _detect_lock:
        if exe in _detected:
            return _detected[exe]
        forced = os.environ.get("BAMS_VIDEO_ENCODER")
        if forced in ENCODERS:
            found = forced
        else:
            if forced:
                log.warning("BAMS_VIDEO_ENCODER=%r is not one of %s; detecting instead", forced, ", ".join(ENCODERS))
            found = next((e for e in ENCODERS if _PLATFORM_ONLY.get(e, sys.platform) == sys.platform
                          and _encoder_works(exe, e)), None)
        log.info("video transcoding encoder: %s", ENCODER_NAMES[found] if found else "none found")
        _detected[exe] = found
        return found


def has_filter(name: str) -> bool:
    exe = ffmpeg_path()
    if not exe:
        return False
    if exe not in _filters:
        r = _run([exe, "-hide_banner", "-filters"], timeout=15)
        names = set()
        for line in r.stdout.decode(errors="replace").splitlines() if r else []:
            parts = line.split()  # " TS bwdif   V->V   Deinterlace the input image."
            if len(parts) >= 3 and "->" in parts[2]:
                names.add(parts[1])
        _filters[exe] = names
    return name in _filters[exe]


_placebo: dict[str, bool] = {}  # ffmpeg path -> libplacebo runs (it needs a Vulkan device)


def has_libplacebo() -> bool:
    """libplacebo is the only FFmpeg filter that applies Dolby Vision metadata. It's in the filter list of
    most builds but needs Vulkan, which a headless server may not have, so it's tried once."""
    exe = ffmpeg_path()
    if not exe or not has_filter("libplacebo"):
        return False
    if exe not in _placebo:
        r = _run([exe, "-hide_banner", "-loglevel", "error", "-nostdin", "-f", "lavfi",
                  "-i", "color=black:size=64x64:duration=0.1", "-vf", "libplacebo=format=yuv420p",
                  "-frames:v", "1", "-f", "null", "-"], timeout=20)
        _placebo[exe] = r is not None and r.returncode == 0
    return _placebo[exe]


def tonemap_mode(video: dict | None) -> str | None:
    """How an HDR source becomes SDR: "libplacebo" (Dolby Vision: profile 5 has no HDR10 base layer and
    comes out green/purple unless its metadata is applied), "zscale" (HDR10/HLG), or None (SDR, or no filter)."""
    hdr = (video or {}).get("hdr")
    if not hdr:
        return None
    if hdr == "Dolby Vision" and has_libplacebo():
        return "libplacebo"
    if has_filter("zscale") and has_filter("tonemap"):
        return "zscale"
    return "libplacebo" if has_libplacebo() else None


def hwaccel_args(encoder: str) -> list[str]:
    """Decode on the GPU too when the encoder is a GPU one (`BAMS_HWACCEL=none` turns it off, or names a
    method). Frames come back to system memory for the filters, so a codec the GPU can't decode
    (Xvid...) quietly falls back to the CPU decoder."""
    mode = os.environ.get("BAMS_HWACCEL", "auto")
    if mode == "none" or (mode == "auto" and encoder not in HARDWARE):
        return []
    if mode != "auto":
        return ["-hwaccel", mode]
    if encoder == "h264_nvenc":
        return ["-hwaccel", "cuda"]
    if encoder == "h264_vaapi":
        return ["-hwaccel", "vaapi", "-hwaccel_device", vaapi_device()]
    return ["-hwaccel", "d3d11va" if sys.platform == "win32" else "vaapi"]  # Quick Sync, AMF


QUALITIES = (2160, 1440, 1080, 720, 480, 360)  # heights the player offers


def _box(encoder: str, max_height: int | None = None) -> tuple[int, int]:
    """Largest output frame: 4K on a GPU encoder, 1080p on the CPU (4K x264 isn't real-time), smaller if
    the viewer picked a lower quality."""
    w, h = (3840, 2160) if encoder in HARDWARE else (1920, 1080)
    if max_height and max_height < h:
        w, h = (max_height * 16 // 9 + 1) // 2 * 2, max_height
    return w, h


def _max_bitrate(width: int, height: int) -> int:
    """Peak video bitrate (kbit/s) for an output size. Encoders aim for a quality, below this cap."""
    px = width * height
    for limit, kbps in ((640 * 360, 1500), (854 * 480, 2500), (1280 * 720, 5000), (1920 * 1080, 10000),
                        (2560 * 1440, 16000)):
        if px <= limit * 1.15:
            return kbps
    return 25000


def quality_bitrate(video: dict | None, encoder: str, max_height: int | None) -> int:
    """The peak bitrate (kbit/s) a transcode of this video at this quality gets."""
    max_w, max_h = _box(encoder, max_height)
    w, h = (video or {}).get("width") or 1920, (video or {}).get("height") or 1080
    fit = min(1.0, max_w / w, max_h / h)
    return _max_bitrate(int(w * fit), int(h * fit))


def _encoder_args(enc: str, kbps: int) -> list[str]:
    cap = ["-maxrate", f"{kbps}k", "-bufsize", f"{kbps * 2}k"]
    target = ["-b:v", f"{kbps * 6 // 10}k"]
    if enc == "h264_nvenc":
        return ["-c:v", enc, "-preset", "p4", "-rc", "vbr", "-cq", "23", "-b:v", "0", *cap,
                "-profile:v", "high", "-forced-idr", "1", "-no-scenecut", "1"]
    if enc == "h264_qsv":
        return ["-c:v", enc, "-preset", "veryfast", *target, *cap, "-profile:v", "high"]
    if enc == "h264_amf":
        return ["-c:v", enc, "-usage", "transcoding", "-quality", "speed", "-rc", "vbr_peak", *target, *cap,
                "-profile:v", "high"]
    if enc == "h264_vaapi":
        return ["-c:v", enc, *target, *cap, "-profile:v", "high"]
    if enc == "libx264":
        return ["-c:v", enc, "-preset", "veryfast", "-crf", "22", *cap, "-profile:v", "high", "-sc_threshold", "0"]
    return ["-c:v", enc, *target]  # h264_mf


def transcode_filters(video: dict | None, encoder: str, tonemap: str | None, max_height: int | None = None) -> str:
    """The -vf chain: deinterlace, square pixels + size cap, HDR -> SDR, the encoder's pixel format."""
    max_w, max_h = _box(encoder, max_height)
    k = f"min(1,min({max_w}/(iw*sar),{max_h}/ih))"  # shrink to fit the box, never enlarge
    chain = [
        # only frames flagged interlaced (DVD/broadcast MPEG-2, 1080i) are touched; progressive ones pass
        "bwdif=mode=send_frame:deint=interlaced",
        # anamorphic DVDs (720x480 shown 16:9) become square pixels; H.264 4:2:0 needs even sizes
        f"scale=w='trunc(iw*sar*{k}/2)*2':h='trunc(ih*{k}/2)*2'",
        "setsar=1",
    ]
    hdr = (video or {}).get("hdr")
    if hdr and tonemap == "libplacebo":
        # applies Dolby Vision metadata (if any), then tone-maps to BT.709 on the GPU (Vulkan)
        chain += ["libplacebo=tonemapping=bt.2390:colorspace=bt709:color_primaries=bt709:color_trc=bt709"
                  ":range=tv:format=yuv420p"]
    elif hdr and tonemap == "zscale":
        # PQ/HLG -> linear light -> BT.709 primaries, tone-mapped so it isn't washed out on SDR screens
        chain += ["zscale=t=linear:npl=100", "format=gbrpf32le", "zscale=p=bt709",
                  "tonemap=tonemap=hable:desat=0", "zscale=t=bt709:m=bt709:r=tv"]
    if encoder == "h264_vaapi":
        chain += ["format=nv12", "hwupload"]
    elif encoder == "h264_qsv":
        chain += ["format=nv12"]
    else:
        chain += ["format=yuv420p"]
    return ",".join(chain)


def _transcode_parts(video: dict | None, encoder: str | None, max_height: int | None) -> tuple[str, list, list]:
    """What both transcode outputs share: (ffmpeg, args before -i, video encoding args after the maps)."""
    exe = ffmpeg_path()
    if not exe:
        raise RuntimeError("FFmpeg not found")
    enc = encoder or video_encoder()
    if not enc:
        raise RuntimeError("FFmpeg has no working H.264 encoder")
    tonemap = tonemap_mode(video)
    pre = ["-vaapi_device", vaapi_device()] if enc == "h264_vaapi" else []
    pre += hwaccel_args(enc)
    out = ["-vf", transcode_filters(video, enc, tonemap, max_height),
           *_encoder_args(enc, quality_bitrate(video, enc, max_height))]
    if tonemap:
        out += ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
    return exe, pre, out


_AUDIO = ["-c:a", "aac", "-ac", "2", "-b:a", "192k", "-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1"]


def transcode_cmd(path: Path, start: float, video: dict | None, audio_index: int = 0,
                  encoder: str | None = None, max_height: int | None = None) -> list[str]:
    """Video -> H.264, audio -> AAC stereo, as fragmented MP4 on stdout. Re-encoding makes the seek
    frame-accurate: the stream really starts at `start` (no keyframe dance like the remux).
    The player uses HLS (`hls_cmd`) when it can; this is for browsers without it."""
    exe, pre, out = _transcode_parts(video, encoder, max_height)
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-nostdin", *pre]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(path), "-map", "0:v:0", "-map", f"0:a:{audio_index}?", *out,
            # a keyframe every 2 s: each one closes an MP4 fragment the browser can play
            "-force_key_frames", "expr:gte(t,n_forced*2)",
            *_AUDIO, "-avoid_negative_ts", "make_zero", "-max_muxing_queue_size", "1024",
            "-f", "mp4", "-movflags", "frag_keyframe+empty_moov+default_base_moof",
            "pipe:1"]
    return cmd


SEGMENT = 4.0  # HLS segment length, seconds


def hls_cmd(path: Path, segment: int, video: dict | None, out_dir: Path, audio_index: int = 0,
            encoder: str | None = None, max_height: int | None = None) -> list[str]:
    """HLS segments `{n}.ts` in `out_dir` (the data dir, never a media folder) from segment `segment` on.

    Segments from different runs must line up, because the player seeks by asking for any segment and
    the server restarts FFmpeg there. So: original timestamps are kept (-copyts, counted from the file's
    start), a keyframe is forced exactly every SEGMENT seconds from the start point (no scene-cut or
    periodic keyframes in between), and the muxer cuts at those keyframes (hls_time a hair under SEGMENT,
    because the first frame can sit a few ms after the start). Segment n always covers n*SEGMENT onwards.
    Every run's timestamps are pushed 10 s later: a run from 0 would otherwise start with negative
    timestamps (B-frames, AAC priming), which the muxer fixes by shifting that run only."""
    exe, pre, out = _transcode_parts(video, encoder, max_height)
    start = segment * SEGMENT
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-nostdin", *pre]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-copyts", "-start_at_zero", "-i", str(path), "-map", "0:v:0", "-map", f"0:a:{audio_index}?", *out,
            "-g", "9999", "-force_key_frames", f"expr:gte(t,n_forced*{SEGMENT})",  # t counts from `start`
            *_AUDIO, "-avoid_negative_ts", "disabled", "-output_ts_offset", "10", "-max_muxing_queue_size", "1024",
            "-f", "hls", "-hls_time", f"{SEGMENT - 0.1}", "-hls_segment_type", "mpegts", "-hls_list_size", "0",
            "-hls_flags", "temp_file",  # a segment appears under its name only once it's complete
            "-start_number", str(segment), "-hls_segment_filename", str(out_dir / "%d.ts"),
            str(out_dir / "ffmpeg.m3u8")]  # FFmpeg's own playlist is ignored; the server writes the real one
    return cmd


# ------------------------------------------------------------------ music

# (container, codec) pairs every current browser plays straight from the file. Anything else
# (ALAC, AIFF, WMA, APE, WavPack, DSD, MKA, AC3/DTS, MP2...) is converted to AAC on the fly.
BROWSER_AUDIO_FILES = {
    ("MP3", "MP3"), ("MP4", "AAC"), ("MP4", "MP3"), ("AAC", "AAC"), ("FLAC", "FLAC"),
    ("OGG", "Vorbis"), ("OGG", "Opus"), ("OGG", "FLAC"), ("WAV", "PCM"),
}
_BROWSER_AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wav"}  # before ffprobe


def plan_audio(probe_info: dict | None, rel_path: str) -> dict:
    """How to play a music file in a browser.

    mode: "file"      -> the original bytes (Range/seeking supported)
          "transcode" -> FFmpeg converts it to AAC (seek by restarting at ?t=)"""
    audio = (probe_info or {}).get("audio") or []
    if audio:
        container, codec, source = probe_info.get("container"), audio[0].get("codec"), "ffprobe"
        ok = (container, codec) in BROWSER_AUDIO_FILES
    else:  # not probed yet: go by the extension (an .m4a could still turn out to be ALAC)
        container = codec = None
        source = "filename"
        ok = os.path.splitext(rel_path)[1].casefold() in _BROWSER_AUDIO_EXTS
    mode = "file" if ok or not ffmpeg_path() else "transcode"
    return {"method": "direct_play" if ok else "transcode", "mode": mode, "source": source, "container": container,
            "audio_codec": codec, "video_codec": None, "audio_ok": ok,
            "duration": (probe_info or {}).get("duration")}


def audio_cmd(path: Path, start: float, sample_rate: int | None = None) -> list[str]:
    """Any audio -> AAC 256k stereo in fragmented MP4 on stdout. Audio seeks are sample-accurate,
    so the stream really starts at `start` (no keyframe dance like the video remux)."""
    exe = ffmpeg_path()
    if not exe:
        raise RuntimeError("FFmpeg not found")
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-nostdin"]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(path), "-map", "0:a:0", "-vn", "-sn", "-dn",
            "-c:a", "aac", "-b:a", "256k", "-ac", "2"]
    if not sample_rate or sample_rate > 48000:
        cmd += ["-ar", "48000"]  # hi-res and DSD sources: AAC tops out at 96 kHz and browsers want <= 48
    cmd += ["-map_metadata", "-1", "-f", "mp4", "-movflags", "empty_moov+default_base_moof",
            "-frag_duration", "1000000", "pipe:1"]
    return cmd


def spawn(cmd: list[str]) -> subprocess.Popen:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0)
    threading.Thread(target=_log_stderr, args=(proc,), name="ffmpeg-stderr", daemon=True).start()
    return proc


def _log_stderr(proc: subprocess.Popen) -> None:
    """FFmpeg runs with -loglevel error, so anything it says is worth logging (and the pipe must be drained)."""
    for line in proc.stderr:
        if text := line.decode(errors="replace").strip():
            log.warning("ffmpeg: %s", text[:500])
