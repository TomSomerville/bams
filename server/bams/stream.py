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
    if exe := os.environ.get("BAMS_FFMPEG"):
        return exe
    if (d := probe.app_ffmpeg_dir()) and (d / "ffmpeg.exe").is_file():
        return str(d / "ffmpeg.exe")
    if exe := shutil.which("ffmpeg"):
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


def remux_start(path: Path, t: float, zero: bool = False) -> float:
    """Where a remux asked to start at `t` really starts.

    Copying video means starting on a keyframe, and FFmpeg's input seek doesn't always pick the
    nearest one (in MKV it can land a keyframe earlier). Rather than predict it, run the very same
    seek as a dry run: keep the original timestamps, stop after one video frame, read its time.
    `zero`: count from the file's start, like the HLS runs (-start_at_zero)."""
    if t <= 0:
        return 0.0
    exe = ffmpeg_path()
    if not exe:
        return t
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-nostdin", "-ss", f"{t:.3f}", "-i", str(path),
           "-map", "0:v:0", "-c:v", "copy", "-copyts", *(["-start_at_zero"] if zero else []),
           "-frames:v", "1", "-f", "framemd5", "pipe:1"]
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


def audio_channels(audio: dict | None, want: int = 2) -> int:
    """Channels of the AAC that conversions make: 5.1 when the viewer asked for surround and the source has
    at least six channels (7.1 is folded to 5.1), else stereo."""
    return 6 if want >= 6 and ((audio or {}).get("channels") or 2) >= 6 else 2


# Audio a remux may copy untouched when the player says its device decodes it (TVs, Safari, Edge, Chromecast
# and set-top boxes often do, and hand it on to an AV receiver). Both go into MP4 cleanly; DTS and TrueHD don't.
PASSTHROUGH_AUDIO = {"AC3", "EAC3"}


def _aac(channels: int = 2, copy: bool = False) -> list[str]:
    if copy:
        return ["-c:a", "copy"]
    return ["-c:a", "aac", "-ac", str(channels), "-b:a", "384k" if channels > 2 else "192k"]


def remux_cmd(path: Path, start: float, video_codec: str | None, audio_index: int = 0, channels: int = 2,
              copy_audio: bool = False) -> list[str]:
    exe = ffmpeg_path()
    if not exe:
        raise RuntimeError("FFmpeg not found")
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-nostdin"]
    if start > 0:
        # input seek: the copied video starts at the keyframe at/before `start`. noaccurate_seek: the converted
        # audio starts there too; by default FFmpeg trims it to `start` exactly and both begin at 0, so the
        # picture ran behind the sound by the distance back to that keyframe (seconds)
        cmd += ["-noaccurate_seek", "-ss", f"{start:.3f}"]
    cmd += ["-i", str(path),
            "-map", "0:v:0", "-map", f"0:a:{audio_index}?",
            "-c:v", "copy"]
    if video_codec == "HEVC":
        cmd += ["-tag:v", "hvc1"]  # the tag browsers expect for HEVC in MP4
    cmd += [*_aac(channels, copy_audio),
            "-sn", "-dn", "-map_metadata", "-1", "-avoid_negative_ts", "make_zero",
            # AC3/EAC3's header box needs its first packet: delay_moov holds the header back until it's seen
            "-f", "mp4", "-movflags", "frag_keyframe+empty_moov+default_base_moof" + ("+delay_moov" if copy_audio else ""),
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
_works: dict[tuple[str, str], bool] = {}  # (ffmpeg path, encoder) -> test encode passed
_preferred: str | None = None          # the admin's choice (Settings → Playback, settings.video_encoder); None = automatic
_filters: dict[str, set[str]] = {}     # ffmpeg path -> filter names
_vaapi_cqp: set[str] = set()           # ffmpeg paths whose VAAPI driver encodes at a constant QP only
VAAPI_QP = 23


def vaapi_device() -> str:
    return os.environ.get("BAMS_VAAPI_DEVICE", "/dev/dri/renderD128")


def _run(cmd: list[str], timeout: float) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _encoder_works(exe: str, enc: str) -> bool:
    """Test-encode two frames with the options conversions really use: a driver can take the encoder but not
    its rate control (Ubuntu's free Intel driver encodes at a constant QP only, and refuses a bitrate). VAAPI
    then falls back to constant QP (`_vaapi_cqp`)."""
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-nostdin"]
    vf = "format=yuv420p"
    if enc == "h264_vaapi":
        cmd += ["-vaapi_device", vaapi_device()]
        vf = "format=nv12,hwupload"
    cmd += ["-f", "lavfi", "-i", "color=black:size=256x256:rate=25:duration=0.2", "-vf", vf, "-frames:v", "2"]

    def ok(args: list[str]) -> bool:
        r = _run([*cmd, *args, "-f", "null", "-"], timeout=15)
        return r is not None and r.returncode == 0

    if ok(_encoder_args(enc, 2500, cqp=False)):
        return True
    if enc == "h264_vaapi" and ok(_encoder_args(enc, 2500, cqp=True)):
        log.info("VAAPI: this driver encodes at a constant QP only (no bitrate cap)")
        _vaapi_cqp.add(exe)
        return True
    return False


def _tested(exe: str, enc: str) -> bool:
    """Whether `enc` works with this FFmpeg here (test-encoded once, then remembered). Call with _detect_lock held."""
    if (exe, enc) not in _works:
        _works[(exe, enc)] = _PLATFORM_ONLY.get(enc, sys.platform) == sys.platform and _encoder_works(exe, enc)
    return _works[(exe, enc)]


def encoder_forced() -> bool:
    """`BAMS_VIDEO_ENCODER` names an encoder: it wins over the Settings choice."""
    return os.environ.get("BAMS_VIDEO_ENCODER") in ENCODERS


def set_preferred(enc: str | None) -> None:
    """The admin's encoder choice (None = automatic). New conversions use it; running ones keep theirs."""
    global _preferred
    _preferred = enc if enc in ENCODERS else None


def preferred() -> str | None:
    return _preferred


def available_encoders() -> list[str]:
    """Every H.264 encoder that works on this machine, best first (each test-encoded once)."""
    exe = ffmpeg_path()
    if not exe:
        return []
    with _detect_lock:
        return [e for e in ENCODERS if _tested(exe, e)]


def video_encoder() -> str | None:
    """The H.264 encoder transcodes use: `BAMS_VIDEO_ENCODER`, else the admin's choice if it works here, else the
    best one detected (once per FFmpeg)."""
    exe = ffmpeg_path()
    if not exe:
        return None
    with _detect_lock:
        if _preferred and not encoder_forced():
            if _tested(exe, _preferred):
                return _preferred  # (one that stopped working, e.g. a removed GPU, falls through to automatic)
        if exe in _detected:
            return _detected[exe]
        forced = os.environ.get("BAMS_VIDEO_ENCODER")
        if forced in ENCODERS:
            found = forced
            _tested(exe, found)  # used either way; the test finds how it encodes here (VAAPI: constant QP only?)
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


def _encoder_args(enc: str, kbps: int, cqp: bool | None = None) -> list[str]:
    """`cqp` (VAAPI): constant QP instead of a capped bitrate; None = what the encoder test found here."""
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
        if cqp is None:
            cqp = ffmpeg_path() in _vaapi_cqp
        if cqp:
            return ["-c:v", enc, "-rc_mode", "CQP", "-qp", str(VAAPI_QP), "-profile:v", "high"]
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


# Codecs the GPU decoders handle on any card that has the matching encoder (newer cards add AV1). Anything
# else, or an all-GPU run that fails anyway (a profile the card can't decode), takes the hybrid path.
GPU_DECODE = {"H.264", "HEVC", "VP9", "AV1", "MPEG-2", "VC-1"}
# How each GPU encoder's all-GPU run decodes: the -hwaccel and the frame format that stays on the card.
# AMF decodes through Direct3D 11 (Windows only); its vpp_amf scaler and encoder take D3D11 frames.
_GPU_DECODER = {"h264_nvenc": ("cuda", "cuda"), "h264_qsv": ("qsv", "qsv"), "h264_vaapi": ("vaapi", "vaapi"),
                "h264_amf": ("d3d11va", "d3d11")}
_GPU_SCALER = {"h264_nvenc": "scale_cuda", "h264_qsv": "vpp_qsv", "h264_vaapi": "scale_vaapi", "h264_amf": "vpp_amf"}
_NEVER_INTERLACED = {"HEVC", "AV1", "VP9"}  # field order doesn't matter: practically always progressive
_gpu_broken: set[tuple] = set()  # (encoder, codec, profile, bit depth) whose all-GPU run failed here


def interlaced(video: dict | None) -> bool | None:
    """Whether the video is interlaced, from the field order ffprobe reports (None: unknown)."""
    v = video or {}
    if v.get("field_order") in ("tt", "bb", "tb", "bt"):
        return True
    if v.get("field_order") == "progressive" or v.get("codec") in _NEVER_INTERLACED:
        return False
    return None


def _gpu_key(encoder: str, video: dict | None) -> tuple:
    v = video or {}
    return encoder, v.get("codec"), v.get("profile"), v.get("bit_depth")


def gpu_failed(encoder: str, video: dict | None) -> None:
    """An all-GPU run of this kind of video failed: use the hybrid path for it until the server restarts, rather
    than failing first every time (a decoder that lacks the profile, a driver without the filter...)."""
    key = _gpu_key(encoder, video)
    if key not in _gpu_broken:
        _gpu_broken.add(key)
        log.warning("all-GPU conversion failed on %s for %s video; using the hybrid path for it from now on",
                    ENCODER_NAMES.get(encoder, encoder), (video or {}).get("codec"))


def gpu_filters(video: dict | None, encoder: str, tonemap: str | None, burn) -> bool:
    """Whether a transcode can stay on the GPU from decode to encode, frames never coming back to system memory:
    NVIDIA (NVDEC -> bwdif_cuda/scale_cuda -> NVENC), Intel Quick Sync (-> vpp_qsv -> QSV), VAAPI on Linux
    (-> deinterlace_vaapi/scale_vaapi -> VAAPI) and AMD on Windows (D3D11 -> vpp_amf -> AMF). Not for HDR (the
    tone-mapping filters run on the CPU or through Vulkan) or burned-in subtitles (overlay is a CPU filter).
    `BAMS_GPU_FILTERS=0` turns it off.

    CUDA's filters work out pixel shape and interlacing per frame; the others are given the output size up front
    and a deinterlacer only when the stream says it's interlaced, so they need the probe's `sar`/`field_order`
    (`probe.video_geometry` for files probed before those were recorded). AMF has no GPU deinterlacer: interlaced
    video takes the hybrid path there, as does video whose scan type nobody knows on Quick Sync."""
    if encoder not in _GPU_DECODER or tonemap or burn is not None or os.environ.get("BAMS_GPU_FILTERS") == "0":
        return False
    if os.environ.get("BAMS_HWACCEL", "auto") not in ("auto", _GPU_DECODER[encoder][0]):
        return False
    v = video or {}
    if v.get("codec") not in GPU_DECODE or (v.get("codec") == "H.264" and (v.get("bit_depth") or 8) > 8):
        return False
    if _gpu_key(encoder, v) in _gpu_broken or not has_filter(_GPU_SCALER[encoder]):
        return False
    if encoder == "h264_nvenc":
        return has_filter("bwdif_cuda")
    if v.get("sar") is None or not v.get("width") or not v.get("height"):
        return False
    scan = interlaced(v)
    if encoder == "h264_vaapi":
        return scan is False or has_filter("deinterlace_vaapi")  # auto=1 passes progressive frames through
    if encoder == "h264_qsv":
        return scan is not None
    return sys.platform == "win32" and scan is False  # AMF


def output_size(video: dict | None, encoder: str, max_height: int | None = None) -> tuple[int, int] | None:
    """The frame size a conversion makes: square pixels, shrunk to fit the box, never enlarged, even sizes. The
    same sum as the scale expression in `transcode_filters`."""
    v = video or {}
    w, h = v.get("width"), v.get("height")
    if not w or not h:
        return None
    sar = v.get("sar") or 1.0
    bw, bh = _box(encoder, max_height)
    k = min(1.0, bw / (w * sar), bh / h)
    return int(w * sar * k / 2) * 2, int(h * k / 2) * 2


def _gpu_filter_chain(video: dict | None, encoder: str, max_height: int | None) -> str:
    if encoder == "h264_nvenc":
        max_w, max_h = _box(encoder, max_height)
        k = f"min(1,min({max_w}/(iw*sar),{max_h}/ih))"
        return ("bwdif_cuda=mode=send_frame:deint=interlaced,"
                f"scale_cuda=w='trunc(iw*sar*{k}/2)*2':h='trunc(ih*{k}/2)*2':format=nv12,setsar=1")
    w, h = output_size(video, encoder, max_height)
    deint = interlaced(video) is not False
    if encoder == "h264_vaapi":
        return f"{'deinterlace_vaapi=auto=1,' if deint else ''}scale_vaapi=w={w}:h={h}:format=nv12,setsar=1"
    if encoder == "h264_qsv":
        return f"vpp_qsv={'deinterlace=advanced:' if deint else ''}w={w}:h={h}:format=nv12,setsar=1"
    return f"vpp_amf=w={w}:h={h}:format=nv12,setsar=1"


def _burn_source(burn, sub_input: list[str] | None) -> str:
    """The filter-graph label of the subtitle stream to paint on. `burn` is the n-th subtitle stream of the video
    itself, or (sidecar file, n): a DVD subtitle (.idx/.sub) next to it, always read as the second input."""
    if isinstance(burn, tuple):
        return f"[1:s:{burn[1]}]"
    return f"[1:s:{burn}]" if sub_input else f"[0:s:{burn}]"


SUB_LEAD = 30.0  # seconds of subtitles read before the start of a burned-in conversion


def _transcode_parts(video: dict | None, encoder: str | None, max_height: int | None, burn=None,
                     gpu: bool = True, sub_input: list[str] | None = None) -> tuple[str, list, list]:
    """What every transcode output shares: (ffmpeg, args before -i, what follows the input: the video map +
    filters + encoder args). `gpu=False` forces the hybrid path (after an all-GPU run failed).
    `burn`: an image subtitle stream painted onto the picture: the n-th subtitle stream, or (sidecar .idx, n).
    A subtitle shows from the moment its event starts, so a run starting mid-line would miss the line on screen:
    `sub_input` (input options + -i of the same file or the sidecar, seeked SUB_LEAD earlier) is a second input
    the subtitles are read from."""
    exe = ffmpeg_path()
    if not exe:
        raise RuntimeError("FFmpeg not found")
    enc = encoder or video_encoder()
    if not enc:
        raise RuntimeError("FFmpeg has no working H.264 encoder")
    tonemap = tonemap_mode(video)
    pre = ["-vaapi_device", vaapi_device()] if enc == "h264_vaapi" else []
    if gpu and gpu_filters(video, enc, tonemap, burn):
        hwaccel, frames = _GPU_DECODER[enc]
        pre += ["-hwaccel", hwaccel, *(["-hwaccel_device", vaapi_device()] if enc == "h264_vaapi" else []),
                "-hwaccel_output_format", frames]
        vmap = ["-map", "0:v:0", "-vf", _gpu_filter_chain(video, enc, max_height)]
    else:
        pre += hwaccel_args(enc)
        vf = transcode_filters(video, enc, tonemap, max_height)
        if burn is None:
            vmap = ["-map", "0:v:0", "-vf", vf]
        else:
            # subtitles go on at the source size, before scaling and tone-mapping (HDR discs' subtitles are
            # HDR too); a subtitle stream that ends early just lets the video through
            src = _burn_source(burn, sub_input)
            vmap = [*(sub_input or []),
                    "-filter_complex", f"[0:v:0]{src}overlay=eof_action=pass:repeatlast=0,{vf}[v]", "-map", "[v]"]
    out = [*vmap, *_encoder_args(enc, quality_bitrate(video, enc, max_height))]
    if tonemap:
        out += ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
    return exe, pre, out


_NO_EXTRAS = ["-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1"]


def transcode_cmd(path: Path, start: float, video: dict | None, audio_index: int = 0,
                  encoder: str | None = None, max_height: int | None = None, channels: int = 2,
                  burn=None) -> list[str]:
    """Video -> H.264, audio -> AAC, as fragmented MP4 on stdout. Re-encoding makes the seek
    frame-accurate: the stream really starts at `start` (no keyframe dance like the remux).
    The player uses HLS (`hls_cmd`) when it can; this is for browsers without it.
    Only NVIDIA's all-GPU path is used here: this stream can't retry on the hybrid path if a GPU run fails."""
    # Burning in from mid-film: both inputs keep the file's own clock (-copyts, like `hls_cmd`), the subtitles
    # read from SUB_LEAD earlier, and the output is moved back to start at 0. (Shifting the subtitle input with
    # -itsoffset instead lost a line that was already on screen.) A sidecar is always the second input.
    sub_file = burn[0] if isinstance(burn, tuple) else path
    clock = burn is not None and start > 0
    sub_input = None
    if clock:
        sub_input = ["-ss", f"{max(0.0, start - SUB_LEAD):.3f}", "-i", str(sub_file)]
    elif isinstance(burn, tuple):
        sub_input = ["-i", str(sub_file)]
    exe, pre, out = _transcode_parts(video, encoder, max_height, burn, sub_input=sub_input,
                                     gpu=(encoder or video_encoder()) == "h264_nvenc")
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-nostdin", *pre]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    if clock:
        cmd += ["-copyts", "-start_at_zero"]
        out = [*out, "-output_ts_offset", f"{-start:.3f}"]
    cmd += ["-i", str(path), *out, "-map", f"0:a:{audio_index}?",
            # a keyframe every 2 s: each one closes an MP4 fragment the browser can play
            "-force_key_frames", "expr:gte(t,n_forced*2)",
            *_aac(channels), *_NO_EXTRAS, "-avoid_negative_ts", "make_zero", "-max_muxing_queue_size", "1024",
            "-f", "mp4", "-movflags", "frag_keyframe+empty_moov+default_base_moof",
            "pipe:1"]
    return cmd


SEGMENT = 4.0  # HLS segment length, seconds


def hls_cmd(path: Path, segment: int, video: dict | None, out_dir: Path, audio_index: int = 0,
            encoder: str | None = None, max_height: int | None = None, channels: int = 2,
            burn=None, gpu: bool = True) -> list[str]:
    """HLS segments `{n}.ts` in `out_dir` (the data dir, never a media folder) from segment `segment` on.

    Segments from different runs must line up, because the player seeks by asking for any segment and
    the server restarts FFmpeg there. So: original timestamps are kept (-copyts, counted from the file's
    start), a keyframe is forced exactly every SEGMENT seconds from the start point (no scene-cut or
    periodic keyframes in between), and the muxer cuts at those keyframes (hls_time a hair under SEGMENT,
    because the first frame can sit a few ms after the start). Segment n always covers n*SEGMENT onwards.
    Every run's timestamps are pushed 10 s later: a run from 0 would otherwise start with negative
    timestamps (B-frames, AAC priming), which the muxer fixes by shifting that run only."""
    start = segment * SEGMENT
    # -copyts keeps both inputs on the file's own clock, so the earlier subtitle input lines up by itself
    # (a sidecar .idx counts from the film's start too, and has no start time for -start_at_zero to take off)
    sub_file = burn[0] if isinstance(burn, tuple) else path
    seek = ["-ss", f"{max(0.0, start - SUB_LEAD):.3f}"] if start > 0 else []
    sub_input = [*seek, "-i", str(sub_file)] if burn is not None and (start > 0 or isinstance(burn, tuple)) else None
    exe, pre, out = _transcode_parts(video, encoder, max_height, burn, gpu, sub_input)
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-nostdin", *pre]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-copyts", "-start_at_zero", "-i", str(path), *out, "-map", f"0:a:{audio_index}?",
            "-g", "9999", "-force_key_frames", f"expr:gte(t,n_forced*{SEGMENT})",  # t counts from `start`
            *_aac(channels), *_NO_EXTRAS, "-avoid_negative_ts", "disabled", "-output_ts_offset", "10",
            "-max_muxing_queue_size", "1024",
            "-f", "hls", "-hls_time", f"{SEGMENT - 0.1}", "-hls_segment_type", "mpegts", "-hls_list_size", "0",
            "-hls_flags", "temp_file",  # a segment appears under its name only once it's complete
            "-start_number", str(segment), "-hls_segment_filename", str(out_dir / "%d.ts"),
            str(out_dir / "ffmpeg.m3u8")]  # FFmpeg's own playlist is ignored; the server writes the real one
    return cmd


# ------------------------------------------------------------------ HLS without re-encoding the video

def keyframes(path: Path, timeout: float = 900) -> list[float] | None:
    """Times (s, from the file's start) of every video keyframe, or None if they can't be read.

    An HLS version of the audio-only remux copies the video, so its segments can only start on the file's own
    keyframes, and the playlist (made up front) has to know them all. ffprobe lists packets without decoding,
    but has to read the whole file to do it: a second for an MP4 (its index), up to a minute or so for a large
    MKV on a slow disk. Callers cache the result (`hls.Keyframes`)."""
    exe = probe.ffprobe_path()
    if not exe:
        return None
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    try:
        st = subprocess.run([exe, "-v", "error", "-show_entries", "format=start_time", "-of", "csv=p=0", str(path)],
                            capture_output=True, timeout=60, stdin=subprocess.DEVNULL, creationflags=flags)
        start = float(st.stdout.decode().strip() or 0)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        start = 0.0
    try:
        r = subprocess.run([exe, "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time,flags",
                            "-of", "csv=p=0", str(path)], capture_output=True, timeout=timeout,
                           stdin=subprocess.DEVNULL, creationflags=flags)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    out = set()
    for line in r.stdout.decode(errors="replace").splitlines():
        pts, _, fl = line.partition(",")
        if "K" in fl:
            try:
                out.add(round(float(pts) - start, 3))
            except ValueError:
                pass  # pts N/A
    times = sorted(t for t in out if t >= 0)
    return times or None


def hls_copy_cmd(path: Path, segment: int, seek: float, video_codec: str | None, out_dir: Path,
                 audio_index: int = 0, channels: int = 2, copy_audio: bool = False, ts: bool = False) -> list[str]:
    """The audio-only remux as HLS: video copied, audio -> AAC (or copied too: `copy_audio`, Dolby pass-through),
    one fMP4 segment per source keyframe (`{n}.m4s`, with `init_{segment}.mp4`), numbered from `segment`.

    `seek` is the time asked of FFmpeg's input seek. Copying can only start where the file's index allows,
    which (in MKV) is often a keyframe or two before the target, so the caller first asks `remux_start` where
    this very seek lands and passes that keyframe's number as `segment`.
    Like `hls_cmd`, timestamps are kept so runs line up (`frag_discont`: fMP4 fragments carry the real decode
    time instead of counting from 0 in every run). The cuts come from the source: a tiny hls_time makes the
    muxer cut at every keyframe, which are exactly the boundaries the playlist lists. fMP4 rather than
    MPEG-TS so HEVC/AV1 copy cleanly for MSE. `ts`: MPEG-TS segments (`{n}.ts`, no init file) for players that
    take no fMP4 HLS (Samsung's AVPlay); TS packets carry their own timestamps, so runs line up without
    frag_discont."""
    exe = ffmpeg_path()
    if not exe:
        raise RuntimeError("FFmpeg not found")
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-nostdin"]
    if seek > 0:
        cmd += ["-ss", f"{seek:.3f}"]
    cmd += ["-copyts", "-start_at_zero", "-i", str(path), "-map", "0:v:0", "-map", f"0:a:{audio_index}?",
            "-c:v", "copy"]
    if video_codec == "HEVC" and not ts:
        cmd += ["-tag:v", "hvc1"]  # the MP4 tag browsers expect; TS has no such tag
    cmd += [*_aac(channels, copy_audio), *_NO_EXTRAS, "-avoid_negative_ts", "disabled", "-output_ts_offset", "10",
            "-max_muxing_queue_size", "1024", "-f", "hls", "-hls_time", "0.1"]
    if ts:
        return [*cmd, "-hls_segment_type", "mpegts", "-hls_list_size", "0", "-hls_flags", "temp_file",
                "-start_number", str(segment), "-hls_segment_filename", str(out_dir / "%d.ts"),
                str(out_dir / f"ffmpeg_{segment}.m3u8")]
    # The init file name is bare and FFmpeg runs in out_dir (`spawn(cwd=)`): FFmpeg 6.1 and older put the
    # playlist's folder in front of it (an absolute name doubled the path: ENOENT), newer ones use the working dir.
    cmd += ["-hls_segment_type", "fmp4",
            "-hls_segment_options", "movflags=+frag_discont", "-hls_fmp4_init_filename", f"init_{segment}.mp4",
            "-hls_list_size", "0", "-hls_flags", "temp_file",  # a segment appears under its name once complete
            "-start_number", str(segment), "-hls_segment_filename", str(out_dir / "%d.m4s"),
            str(out_dir / f"ffmpeg_{segment}.m3u8")]
    return cmd


# ------------------------------------------------------------------ music

# (container, codec) pairs every current browser plays straight from the file. Anything else
# (ALAC, AIFF, WMA, APE, WavPack, DSD, MKA, AC3/DTS, MP2...) is converted to AAC on the fly.
BROWSER_AUDIO_FILES = {
    ("MP3", "MP3"), ("MP4", "AAC"), ("MP4", "MP3"), ("AAC", "AAC"), ("FLAC", "FLAC"),
    ("OGG", "Vorbis"), ("OGG", "Opus"), ("OGG", "FLAC"), ("WAV", "PCM"),
}
_BROWSER_AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wav"}  # before ffprobe
# What music browsers can't play is converted to (admin setting "music_output"): AAC 256k, or lossless FLAC
# (every current browser plays FLAC; about 4x the data of AAC, so meant for home networks).
MUSIC_OUTPUTS = ("aac", "flac")


def plan_audio(probe_info: dict | None, rel_path: str, output: str = "aac") -> dict:
    """How to play a music file in a browser.

    mode: "file"      -> the original bytes (Range/seeking supported)
          "transcode" -> FFmpeg converts it to `output` (AAC or FLAC; seek by restarting at ?t=)"""
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
            "output": output if mode == "transcode" else None,
            "duration": (probe_info or {}).get("duration")}


def audio_cmd(path: Path, start: float, audio: dict | None = None, output: str = "aac") -> list[str]:
    """Any audio -> AAC 256k stereo in fragmented MP4, or (`output="flac"`) lossless FLAC, on stdout. `audio` is
    the source's ffprobe audio stream. Audio seeks are sample-accurate, so the stream really starts at `start`
    (no keyframe dance like the video remux)."""
    exe = ffmpeg_path()
    if not exe:
        raise RuntimeError("FFmpeg not found")
    audio = audio or {}
    rate = audio.get("sample_rate")
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-nostdin"]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(path), "-map", "0:a:0", "-vn", "-sn", "-dn"]
    if output == "flac":
        # 24-bit sources (and DSD, decoded to PCM) stay 24-bit; channels are kept (browsers mix down themselves)
        deep = (audio.get("bit_depth") or 16) > 16 or audio.get("codec") == "DSD"
        cmd += ["-c:a", "flac", "-compression_level", "2",
                *(["-sample_fmt", "s32", "-bits_per_raw_sample", "24"] if deep else ["-sample_fmt", "s16"])]
        if rate and rate > 96000:  # 192 kHz, and DSD (2.8 MHz, decoded to 352.8 kHz): browsers are happiest at <= 96
            cmd += ["-ar", "96000" if rate % 48000 == 0 else "88200"]
        return cmd + ["-map_metadata", "-1", "-f", "flac", "pipe:1"]
    cmd += ["-c:a", "aac", "-b:a", "256k", "-ac", "2"]
    if not rate or rate > 48000:
        cmd += ["-ar", "48000"]  # hi-res and DSD sources: AAC tops out at 96 kHz and browsers want <= 48
    cmd += ["-map_metadata", "-1", "-f", "mp4", "-movflags", "empty_moov+default_base_moof",
            "-frag_duration", "1000000", "pipe:1"]
    return cmd


def spawn(cmd: list[str], cwd: Path | None = None) -> subprocess.Popen:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, cwd=cwd,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0)
    threading.Thread(target=_log_stderr, args=(proc,), name="ffmpeg-stderr", daemon=True).start()
    return proc


def _log_stderr(proc: subprocess.Popen) -> None:
    """FFmpeg runs with -loglevel error, so anything it says is worth logging (and the pipe must be drained)."""
    for line in proc.stderr:
        if text := line.decode(errors="replace").strip():
            log.warning("ffmpeg: %s", text[:500])
