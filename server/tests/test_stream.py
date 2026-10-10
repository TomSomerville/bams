import json
import re
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import signed_in
from bams import jobs, probe, readonly, stream
from bams.app import create_app
from bams.config import Paths


def P(container, vcodec, *acodecs):
    return {"container": container, "duration": 100.0, "video": {"codec": vcodec},
            "audio": [{"codec": a} for a in acodecs], "subtitles": []}


@pytest.mark.parametrize("info,method,mode", [
    (P("MP4", "H.264", "AAC"), "direct_play", "file"),
    (P("MKV", "H.264", "AAC"), "direct_stream", "file"),     # Family Guy: plays as-is in Chromium
    (P("MKV", "H.264", "AC3"), "direct_stream", "remux"),    # Bob's Burgers: silent unless audio converted
    (P("MKV", "H.264", "EAC3"), "direct_stream", "remux"),
    (P("MKV", "HEVC", "EAC3"), "direct_stream", "remux"),    # The Simpsons
    (P("AVI", "Xvid", "MP3"), "transcode", "transcode"),     # no browser decodes MPEG-4 ASP
    (P("MPEG", "MPEG-2", "AC3"), "transcode", "transcode"),  # DVD rip
    (P("WMV", "VC-1", "WMA"), "transcode", "transcode"),
    (P("WebM", "VP8", "Vorbis"), "direct_stream", "file"),
    (P("MKV", "VP8", "AC3"), "transcode", "transcode"),      # VP8 can't go in the remux's MP4
])
def test_plan(info, method, mode, monkeypatch):
    monkeypatch.setattr(stream, "ffmpeg_path", lambda: "ffmpeg")
    pb = stream.plan(info, None)
    assert (pb["method"], pb["mode"]) == (method, mode)


def test_plan_h264_hi10p_is_transcoded(monkeypatch):
    monkeypatch.setattr(stream, "ffmpeg_path", lambda: "ffmpeg")
    info = P("MKV", "H.264", "AAC")
    info["video"].update(profile="High 10", bit_depth=10)
    assert stream.plan(info, None)["mode"] == "transcode"
    info["video"].update(codec="HEVC", profile="Main 10")  # HEVC 10-bit: up to the browser, not the server
    assert stream.plan(info, None)["mode"] == "file"


def test_plan_without_ffmpeg_falls_back_to_the_file(monkeypatch):
    monkeypatch.setattr(stream, "ffmpeg_path", lambda: None)
    assert stream.plan(P("AVI", "Xvid", "MP3"), None)["mode"] == "file"
    assert stream.plan(None, {"release": {}})["mode"] == "file"  # codec unknown: just try the file


@pytest.fixture
def fake_ffmpeg(monkeypatch):
    """FFmpeg 'installed', encoders answering from a set; detection cache cleared."""
    works: set[str] = set()
    tried: list[str] = []
    monkeypatch.setattr(stream, "ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(stream, "_detected", {})
    monkeypatch.setattr(stream, "_works", {})
    monkeypatch.setattr(stream, "_preferred", None)
    monkeypatch.setattr(stream, "_vaapi_cqp", set())
    monkeypatch.setattr(stream, "_encoder_works", lambda exe, enc: tried.append(enc) or enc in works)
    monkeypatch.delenv("BAMS_VIDEO_ENCODER", raising=False)
    return works, tried


def test_encoder_choice_cpu_or_gpu(fake_ffmpeg, monkeypatch):
    """Tester request: pick CPU or GPU. The choice is used if it works here; else automatic; the env var wins."""
    works, _ = fake_ffmpeg
    monkeypatch.setattr(stream.sys, "platform", "win32")
    works.update({"h264_nvenc", "libx264"})
    assert stream.available_encoders() == ["h264_nvenc", "libx264"]
    assert stream.video_encoder() == "h264_nvenc"
    stream.set_preferred("libx264")
    assert stream.video_encoder() == "libx264"
    stream.set_preferred("h264_qsv")  # doesn't work here: automatic
    assert stream.video_encoder() == "h264_nvenc"
    stream.set_preferred("bogus")
    assert stream.preferred() is None
    stream.set_preferred("libx264")
    monkeypatch.setenv("BAMS_VIDEO_ENCODER", "h264_nvenc")
    assert stream.encoder_forced() and stream.video_encoder() == "h264_nvenc"


def test_encoder_choice_api(fake_ffmpeg, monkeypatch, tmp_path):
    works, _ = fake_ffmpeg
    monkeypatch.setattr(stream.sys, "platform", "win32")
    works.update({"h264_nvenc", "libx264"})
    paths = Paths(tmp_path / "data")
    c = signed_in(create_app(paths, start_scheduler=False))
    e = c.get("/api/settings/encoders").json()
    assert (e["choice"], e["active"], e["automatic"]) == (None, "h264_nvenc", "h264_nvenc")
    assert [(o["id"], o["hardware"]) for o in e["options"]] == [("h264_nvenc", True), ("libx264", False)]
    assert c.put("/api/settings/encoder", json={"encoder": "h264_qsv"}).status_code == 400
    e = c.put("/api/settings/encoder", json={"encoder": "libx264"}).json()
    assert (e["choice"], e["active"]) == ("libx264", "libx264")
    assert c.get("/api/status").json()["video_encoder"]["hardware"] is False
    stream.set_preferred(None)
    create_app(paths, start_scheduler=False)  # a restart reads the saved choice
    assert stream.preferred() == "libx264"
    assert c.put("/api/settings/encoder", json={"encoder": None}).json()["active"] == "h264_nvenc"


def test_encoder_detection_prefers_hardware_and_caches(fake_ffmpeg, monkeypatch):
    works, tried = fake_ffmpeg
    monkeypatch.setattr(stream.sys, "platform", "win32")
    works.update({"h264_amf", "libx264"})
    assert stream.video_encoder() == "h264_amf"
    assert tried == ["h264_nvenc", "h264_qsv", "h264_amf"]
    assert stream.video_encoder() == "h264_amf" and len(tried) == 3  # detected once


def test_encoder_detection_platform_and_override(fake_ffmpeg, monkeypatch):
    works, tried = fake_ffmpeg
    monkeypatch.setattr(stream.sys, "platform", "win32")
    works.add("h264_vaapi")  # Linux-only: never tried on Windows
    assert stream.video_encoder() is None and "h264_vaapi" not in tried and "h264_mf" in tried

    monkeypatch.setattr(stream, "_detected", {})
    monkeypatch.setenv("BAMS_VIDEO_ENCODER", "libx264")
    assert stream.video_encoder() == "libx264"

    monkeypatch.setattr(stream, "_detected", {})
    monkeypatch.setenv("BAMS_VIDEO_ENCODER", "bogus")  # ignored, detection runs
    monkeypatch.setattr(stream.sys, "platform", "linux")
    assert stream.video_encoder() == "h264_vaapi"


def test_encoder_test_uses_the_real_options_and_vaapi_falls_back_to_constant_qp(monkeypatch):
    """Ubuntu's free Intel driver (owner's HD 630) takes h264_vaapi at a constant QP only: with a bitrate every
    conversion failed ("Driver does not support any RC mode"), while a test without one passed."""
    monkeypatch.setattr(stream, "ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(stream, "_vaapi_cqp", set())
    cqp_only = [True]
    runs = []

    def run(cmd, timeout):
        runs.append(cmd)
        return subprocess.CompletedProcess(cmd, 0 if "-rc_mode" in cmd or not cqp_only[0] else 1)

    monkeypatch.setattr(stream, "_run", run)
    assert stream._encoder_works("ffmpeg", "h264_vaapi")
    assert "-maxrate" in runs[0] and runs[1][runs[1].index("-rc_mode") + 1] == "CQP"
    args = stream._encoder_args("h264_vaapi", 5000)
    assert args[args.index("-qp") + 1] == str(stream.VAAPI_QP) and "-maxrate" not in args and "-b:v" not in args

    stream._vaapi_cqp.clear()
    cqp_only[0] = False  # a driver with bitrate modes keeps the cap
    runs.clear()
    assert stream._encoder_works("ffmpeg", "h264_vaapi") and len(runs) == 1
    assert "-maxrate" in stream._encoder_args("h264_vaapi", 5000)

    cqp_only[0] = True  # other encoders are tested with their real options too, and have no fallback
    runs.clear()
    assert not stream._encoder_works("ffmpeg", "h264_qsv") and len(runs) == 1 and "-maxrate" in runs[0]


def test_transcode_filters():
    sd = {"codec": "MPEG-2", "width": 720, "height": 480, "hdr": None}
    f = stream.transcode_filters(sd, "libx264", tonemap="zscale")
    assert f.startswith("bwdif=") and "1920/(iw*sar)" in f and f.endswith("format=yuv420p")
    assert "tonemap" not in f  # SDR source
    uhd = {"codec": "HEVC", "width": 3840, "height": 2160, "hdr": "HDR10"}
    assert "tonemap=tonemap=hable" in stream.transcode_filters(uhd, "h264_nvenc", tonemap="zscale")
    assert "libplacebo=tonemapping" in stream.transcode_filters(uhd, "h264_nvenc", tonemap="libplacebo")
    assert "tonemap" not in stream.transcode_filters(uhd, "h264_nvenc", tonemap=None)  # FFmpeg lacks the filters
    assert "3840/(iw*sar)" in stream.transcode_filters(uhd, "h264_nvenc", None)  # GPU: keep 4K
    assert "1280/(iw*sar)" in stream.transcode_filters(uhd, "h264_nvenc", None, max_height=720)  # quality picker
    assert stream.transcode_filters(uhd, "h264_qsv", None).endswith("format=nv12")
    assert stream.transcode_filters(uhd, "h264_vaapi", None).endswith("format=nv12,hwupload")


def test_tonemap_mode(monkeypatch):
    filters = {"zscale", "tonemap"}
    placebo = [True]
    monkeypatch.setattr(stream, "has_filter", lambda name: name in filters)
    monkeypatch.setattr(stream, "has_libplacebo", lambda: placebo[0])
    assert stream.tonemap_mode({"hdr": None}) is None
    assert stream.tonemap_mode({"hdr": "HDR10"}) == "zscale"
    assert stream.tonemap_mode({"hdr": "Dolby Vision", "dv_profile": 5}) == "libplacebo"  # applies the DV metadata
    placebo[0] = False  # no Vulkan: DV falls back to plain HDR10 tone-mapping (right for profile 8, not 5)
    assert stream.tonemap_mode({"hdr": "Dolby Vision"}) == "zscale"
    filters.clear()
    assert stream.tonemap_mode({"hdr": "HDR10"}) is None


def test_hwaccel_args(monkeypatch):
    monkeypatch.delenv("BAMS_HWACCEL", raising=False)
    assert stream.hwaccel_args("libx264") == []  # CPU encoder: CPU decoder too
    assert stream.hwaccel_args("h264_nvenc") == ["-hwaccel", "cuda"]
    assert stream.hwaccel_args("h264_vaapi")[:2] == ["-hwaccel", "vaapi"]
    monkeypatch.setenv("BAMS_HWACCEL", "none")
    assert stream.hwaccel_args("h264_nvenc") == []
    monkeypatch.setenv("BAMS_HWACCEL", "d3d11va")
    assert stream.hwaccel_args("h264_nvenc") == ["-hwaccel", "d3d11va"]


def test_transcode_cmd(monkeypatch, tmp_path):
    monkeypatch.setattr(stream, "ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(stream, "has_filter", lambda name: True)
    monkeypatch.setattr(stream, "has_libplacebo", lambda: False)
    monkeypatch.delenv("BAMS_HWACCEL", raising=False)
    uhd = {"codec": "HEVC", "width": 3840, "height": 2160, "hdr": "HDR10"}
    cmd = stream.transcode_cmd(tmp_path / "a.mkv", 12.5, uhd, 1, encoder="libx264")
    assert cmd[cmd.index("-ss") + 1] == "12.500" and cmd.index("-ss") < cmd.index("-i")
    assert "0:a:1?" in cmd and cmd[cmd.index("-c:v") + 1] == "libx264" and "-hwaccel" not in cmd
    assert cmd[cmd.index("-maxrate") + 1] == "10000k"  # CPU: scaled to 1080p, bitrate to match
    assert cmd[cmd.index("-color_trc") + 1] == "bt709"  # tone-mapped output is tagged SDR
    assert cmd[-1] == "pipe:1"
    va = stream.transcode_cmd(tmp_path / "a.mkv", 0, uhd, 0, encoder="h264_vaapi")
    assert "-ss" not in va and va.index("-vaapi_device") < va.index("-i") and va.index("-hwaccel") < va.index("-i")
    assert va[va.index("-maxrate") + 1] == "25000k"  # GPU: stays 4K
    nv = stream.transcode_cmd(tmp_path / "a.mkv", 0, uhd, 0, encoder="h264_nvenc", max_height=480)
    assert nv[nv.index("-maxrate") + 1] == "2500k"  # the viewer picked 480p
    monkeypatch.setattr(stream, "video_encoder", lambda: None)
    with pytest.raises(RuntimeError):
        stream.transcode_cmd(tmp_path / "a.mkv", 0, uhd)


def test_hls_cmd(monkeypatch, tmp_path):
    monkeypatch.setattr(stream, "ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(stream, "has_filter", lambda name: True)
    monkeypatch.setattr(stream, "has_libplacebo", lambda: False)
    out = tmp_path / "data" / "transcode" / "abc"
    cmd = stream.hls_cmd(tmp_path / "media" / "a.avi", 75, {"codec": "Xvid", "width": 640, "height": 480},
                         out, encoder="libx264")
    i = cmd.index("-i")
    assert cmd[cmd.index("-ss") + 1] == "300.000" and cmd.index("-copyts") < i and cmd.index("-start_at_zero") < i
    assert cmd[cmd.index("-start_number") + 1] == "75"  # segment numbers = position / SEGMENT
    assert cmd[cmd.index("-force_key_frames") + 1] == "expr:gte(t,n_forced*4.0)"
    assert cmd[cmd.index("-hls_segment_filename") + 1] == str(out / "%d.ts")  # data dir, never the media folder
    assert "-sc_threshold" in cmd and cmd[cmd.index("-avoid_negative_ts") + 1] == "disabled"
    assert "-ss" not in stream.hls_cmd(tmp_path / "a.avi", 0, None, out, encoder="libx264")


def test_probe_records_dolby_vision_profile():
    data = {"format": {"format_name": "matroska,webm", "duration": "10"}, "streams": [{
        "codec_type": "video", "codec_name": "hevc", "width": 3840, "height": 2160, "pix_fmt": "yuv420p10le",
        "side_data_list": [{"side_data_type": "DOVI configuration record", "dv_profile": 5,
                            "dv_bl_signal_compatibility_id": 0}]}]}
    v = probe.summarize(data)["video"]
    assert v["hdr"] == "Dolby Vision" and v["dv_profile"] == 5


def test_plan_from_filename_before_probe(monkeypatch):
    monkeypatch.setattr(stream, "ffmpeg_path", lambda: "ffmpeg")
    pb = stream.plan(None, {"release": {"video_codec": "H.264", "audio_codec": "Dolby Digital Plus"}})
    assert pb["mode"] == "remux" and pb["source"] == "filename"


@pytest.mark.skipif(not stream.ffmpeg_path(), reason="FFmpeg not installed")
def test_remux_outputs_aac_and_copies_video(tmp_path):
    media = tmp_path / "media" / "Show"
    media.mkdir(parents=True)
    src = media / "Show - S01E01.mkv"
    subprocess.run([stream.ffmpeg_path(), "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=6",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "25",
                    "-c:a", "ac3", "-ac", "6", str(src)], check=True)
    before = src.read_bytes()
    paths = Paths(tmp_path / "data")
    c = signed_in(create_app(paths, start_scheduler=False))
    try:
        lib = c.post("/api/libraries", json={"name": "TV", "type": "show", "paths": [str(tmp_path / "media")]}).json()
        jobs.run_scan(paths, lib["id"], do_match=False)
        show = c.get(f"/api/libraries/{lib['id']}/items").json()[0]
        season = c.get(f"/api/items/{show['id']}").json()["children"][0]
        ep = c.get(f"/api/items/{season['id']}").json()["children"][0]
        f = c.get(f"/api/items/{ep['id']}").json()["files"][0]
        assert f["playback"]["mode"] == "remux" and f["playback"]["url"].endswith("/remux")

        start = c.get(f"/api/files/{f['id']}/seek", params={"t": 2.5}).json()["t"]
        assert 0.5 <= start <= 2.5  # a keyframe at or before 2.5s (one every second in this clip)
        r = c.get(f["playback"]["url"], params={"t": 2.5})  # what the player requests: the same seek
        assert r.status_code == 200 and r.headers["content-type"] == "video/mp4"
        out = tmp_path / "out.mp4"
        out.write_bytes(r.content)
        info = probe.summarize(json.loads(subprocess.run(
            [probe.ffprobe_path(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(out)],
            capture_output=True, check=True).stdout))
        assert info["video"]["codec"] == "H.264" and info["audio"][0]["codec"] == "AAC"
        assert info["audio"][0]["channels"] == 2
        assert abs(info["duration"] - (6 - start)) < 0.3  # starts exactly at the keyframe the player was told
        assert src.read_bytes() == before      # the media file is untouched
    finally:
        readonly.set_protected_roots([])


@pytest.mark.skipif(not stream.ffmpeg_path(), reason="FFmpeg not installed")
def test_live_remux_keeps_sound_with_picture_after_a_seek(tmp_path):
    """The copied video starts at the keyframe before the seek; the converted audio must start there too.
    (FFmpeg trimmed it to the seek point and both began at 0: the picture ran seconds behind the sound.)"""
    import array
    ff = stream.ffmpeg_path()
    src = tmp_path / "clip.mkv"
    # keyframes every 4 s, 5.1 noise (a tone or mostly-silent audio didn't show the trim)
    subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=40",
                    "-f", "lavfi", "-i", "anoisesrc=d=40:c=pink:r=48000", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-g", "100", "-keyint_min", "100", "-sc_threshold", "0", "-c:a", "ac3", "-ac", "6", str(src)],
                   check=True)
    start = stream.remux_start(src, 30)  # the player's offset: the clock shows start + currentTime
    assert abs(start - 28.0) < 0.05
    out = tmp_path / "out.mp4"
    out.write_bytes(subprocess.run(stream.remux_cmd(src, 30, "H.264"), capture_output=True, check=True).stdout)

    def pcm(f, at, length):
        return array.array("h", subprocess.run([ff, "-v", "error", "-ss", f"{at:.3f}", "-i", str(f), "-t", str(length),
                                                "-vn", "-ac", "1", "-ar", "2000", "-f", "s16le", "-"],
                                               capture_output=True, check=True).stdout)

    def match(a, b):  # best normalized correlation of a anywhere in b
        na = sum(x * x for x in a) ** .5
        return max(sum(x * y for x, y in zip(a, b[s:])) / (na * sum(y * y for y in b[s:s + len(a)]) ** .5 + 1e-9)
                   for s in range(len(b) - len(a)))

    head = pcm(out, 0, 0.25)  # the output's first sound must be the original's at `start`, not at 30 s
    assert match(head, pcm(src, start - 0.1, 0.45)) > 0.8


@pytest.mark.skipif(not stream.ffmpeg_path(), reason="FFmpeg not installed")
def test_unprobed_file_is_probed_when_opened(tmp_path):
    """A file the scan hasn't read yet (still scanning): opening the episode reads it, so the player gets a
    duration (HLS, the timeline, saved positions) instead of the file-name guess."""
    from bams import scanner
    from bams.db import connect
    media = tmp_path / "media" / "Show" / "Season 01"
    media.mkdir(parents=True)
    src = media / "Show - S01E01.mkv"
    subprocess.run([stream.ffmpeg_path(), "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=4",
                    "-f", "lavfi", "-i", "sine=duration=4", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "ac3", str(src)], check=True)
    paths = Paths(tmp_path / "data")
    c = signed_in(create_app(paths, start_scheduler=False))
    try:
        lib = c.post("/api/libraries", json={"name": "TV", "type": "show", "paths": [str(tmp_path / "media")]}).json()
        con = connect(paths.db)
        scanner.scan_library(con, lib["id"], do_probe=False)
        ep = con.execute("SELECT id FROM items WHERE kind='episode'").fetchone()["id"]
        assert con.execute("SELECT probe FROM files").fetchone()["probe"] is None
        f = c.get(f"/api/items/{ep}").json()["files"][0]
        assert f["probe"]["duration"] == pytest.approx(4, abs=0.2)
        assert f["playback"]["source"] == "ffprobe" and f["playback"]["duration"]
        assert con.execute("SELECT probe FROM files").fetchone()["probe"] is not None  # kept: not probed twice
        con.close()
    finally:
        readonly.set_protected_roots([])


@pytest.mark.skipif(not stream.ffmpeg_path() or not stream.video_encoder(), reason="FFmpeg/H.264 encoder not installed")
def test_transcode_outputs_h264_from_the_exact_start(tmp_path):
    media = tmp_path / "media" / "Old Film (1999)"
    media.mkdir(parents=True)
    src = media / "Old Film (1999).avi"
    subprocess.run([stream.ffmpeg_path(), "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=6",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=6", "-c:v", "mpeg4", "-vtag", "XVID",
                    "-c:a", "libmp3lame", str(src)], check=True)
    before = src.read_bytes()
    paths = Paths(tmp_path / "data")
    c = signed_in(create_app(paths, start_scheduler=False))
    try:
        assert c.get("/api/status").json()["video_encoder"]["id"] == stream.video_encoder()
        lib = c.post("/api/libraries", json={"name": "Movies", "type": "movie", "paths": [str(tmp_path / "media")]}).json()
        jobs.run_scan(paths, lib["id"], do_match=False)
        movie = c.get(f"/api/libraries/{lib['id']}/items").json()[0]
        f = c.get(f"/api/items/{movie['id']}").json()["files"][0]
        pb = f["playback"]
        assert (pb["method"], pb["mode"], pb["video_codec"]) == ("transcode", "transcode", "Xvid")
        assert pb["url"] == pb["transcode_url"] == f"/api/files/{f['id']}/transcode"

        r = c.get(pb["url"], params={"t": 2})
        assert r.status_code == 200 and r.headers["content-type"] == "video/mp4"
        out = tmp_path / "out.mp4"
        out.write_bytes(r.content)
        info = probe.summarize(json.loads(subprocess.run(
            [probe.ffprobe_path(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(out)],
            capture_output=True, check=True).stdout))
        assert info["video"]["codec"] == "H.264" and info["video"]["bit_depth"] == 8
        assert info["audio"][0]["codec"] == "AAC" and info["audio"][0]["channels"] == 2
        assert abs(info["duration"] - 4) < 0.3  # frame-accurate: starts at exactly t=2
        assert src.read_bytes() == before        # the media file is untouched
    finally:
        readonly.set_protected_roots([])


def test_audio_channels():
    assert stream.audio_channels({"channels": 6}, 6) == 6
    assert stream.audio_channels({"channels": 8}, 6) == 6   # 7.1 folds to 5.1
    assert stream.audio_channels({"channels": 2}, 6) == 2   # nothing to keep
    assert stream.audio_channels({"channels": 6}, 2) == 2   # the viewer wants stereo
    assert stream.audio_channels(None, 6) == 2
    cmd = stream.remux_cmd(Path("a.mkv"), 0, "H.264", 1, 6) if stream.ffmpeg_path() else None
    if cmd:
        assert cmd[cmd.index("-ac") + 1] == "6" and cmd[cmd.index("-b:a") + 1] == "384k" and "0:a:1?" in cmd


def test_burn_in_and_gpu_filters(monkeypatch, tmp_path):
    monkeypatch.setattr(stream, "ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(stream, "has_filter", lambda name: True)
    monkeypatch.setattr(stream, "has_libplacebo", lambda: False)
    monkeypatch.delenv("BAMS_GPU_FILTERS", raising=False)
    monkeypatch.delenv("BAMS_HWACCEL", raising=False)
    hevc = {"codec": "HEVC", "width": 1920, "height": 1080, "bit_depth": 10}
    out = tmp_path / "t"
    # NVENC + SDR: decode, deinterlace, scale and encode all on the GPU
    cmd = stream.hls_cmd(Path("a.mkv"), 0, hevc, out, encoder="h264_nvenc", max_height=720)
    assert cmd[cmd.index("-hwaccel_output_format") + 1] == "cuda"
    vf = cmd[cmd.index("-vf") + 1]
    assert vf.startswith("bwdif_cuda") and "scale_cuda" in vf and "1280" in vf and "format=yuv420p" not in vf
    # ...but not with a subtitle burned in (overlay is a CPU filter), nor after a failed GPU run, nor for HDR
    burn = stream.hls_cmd(Path("a.mkv"), 0, hevc, out, encoder="h264_nvenc", burn=2)
    fc = burn[burn.index("-filter_complex") + 1]
    assert fc.startswith("[0:v:0][0:s:2]overlay=") and fc.endswith("[v]") and burn[burn.index("-map") + 1] == "[v]"
    assert "-hwaccel_output_format" not in burn and "-vf" not in burn
    mid = stream.hls_cmd(Path("a.mkv"), 25, hevc, out, encoder="h264_nvenc", burn=2)  # starts at 100 s
    assert mid.count("-i") == 2 and mid[mid.index("-i") + 2:mid.index("-i") + 6] == ["-ss", "70.000", "-i", "a.mkv"]
    assert mid[mid.index("-filter_complex") + 1].startswith("[0:v:0][1:s:2]overlay")  # subtitles from 30 s before
    fmp4 = stream.transcode_cmd(Path("a.mkv"), 12, hevc, encoder="h264_nvenc", burn=0)
    assert "[1:s:0]" in fmp4[fmp4.index("-filter_complex") + 1] and "-copyts" in fmp4  # the file's clock, then back to 0
    assert fmp4[fmp4.index("-output_ts_offset") + 1] == "-12.000" and fmp4.count("-ss") == 2 and "0.000" in fmp4
    assert "-hwaccel_output_format" not in stream.hls_cmd(Path("a.mkv"), 0, hevc, out, encoder="h264_nvenc", gpu=False)
    assert not stream.gpu_filters({**hevc, "hdr": "HDR10"}, "h264_nvenc", "zscale", None)
    assert not stream.gpu_filters({"codec": "H.264", "bit_depth": 10}, "h264_nvenc", None, None)  # Hi10P: no NVDEC
    assert not stream.gpu_filters(hevc, "libx264", None, None)
    monkeypatch.setenv("BAMS_GPU_FILTERS", "0")
    assert not stream.gpu_filters(hevc, "h264_nvenc", None, None)


def test_hls_copy_cmd(monkeypatch, tmp_path):
    monkeypatch.setattr(stream, "ffmpeg_path", lambda: "ffmpeg")
    out = tmp_path / "data" / "transcode" / "s" / "0"
    cmd = stream.hls_copy_cmd(Path("a.mkv"), 40, 120.5, "HEVC", out, 1, 6)
    i = cmd.index("-i")
    assert cmd[cmd.index("-ss") + 1] == "120.500" and cmd.index("-copyts") < i
    assert cmd[cmd.index("-hls_segment_options") + 1] == "movflags=+frag_discont"  # real times in every run
    assert cmd[cmd.index("-c:v") + 1] == "copy" and cmd[cmd.index("-tag:v") + 1] == "hvc1"
    assert cmd[cmd.index("-hls_segment_type") + 1] == "fmp4" and cmd[cmd.index("-start_number") + 1] == "40"
    # bare: FFmpeg 6.1 (Ubuntu 24.04) puts the playlist's folder in front of an absolute name too (ENOENT);
    # the run starts in `out` (hls.Transcodes), where newer FFmpeg puts a bare name
    assert cmd[cmd.index("-hls_fmp4_init_filename") + 1] == "init_40.mp4"
    assert cmd[cmd.index("-hls_segment_filename") + 1] == str(out / "%d.m4s")
    assert "0:a:1?" in cmd and cmd[cmd.index("-ac") + 1] == "6"
    assert cmd[cmd.index("-hls_flags") + 1] == "temp_file"  # a half-written segment is never served
    assert cmd[cmd.index("-hls_list_size") + 1] == "0"
    copy = stream.hls_copy_cmd(Path("a.mkv"), 0, 0, "H.264", out, 0, 6, copy_audio=True)
    assert copy[copy.index("-c:a") + 1] == "copy" and "-ac" not in copy
    live = stream.remux_cmd(Path("a.mkv"), 5, "H.264", 0, 2, copy_audio=True)
    assert live[live.index("-c:a") + 1] == "copy" and "-b:a" not in live


@pytest.fixture
def gpu(monkeypatch):
    """Every filter 'available', no failed GPU runs remembered, no overrides in the environment."""
    monkeypatch.setattr(stream, "ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(stream, "has_filter", lambda name: True)
    monkeypatch.setattr(stream, "has_libplacebo", lambda: False)
    monkeypatch.setattr(stream, "_gpu_broken", set())
    for var in ("BAMS_GPU_FILTERS", "BAMS_HWACCEL", "BAMS_VAAPI_DEVICE"):
        monkeypatch.delenv(var, raising=False)


def test_all_gpu_filters_for_quick_sync_amf_and_vaapi(gpu, monkeypatch, tmp_path):
    """Intel Quick Sync, AMD AMF (Windows) and VAAPI (Linux) keep frames on the GPU like NVIDIA does. Their scalers
    get the output size as numbers (from the probe's pixel aspect) and a deinterlacer only for interlaced video."""
    out = tmp_path / "t"
    hevc = {"codec": "HEVC", "width": 3840, "height": 2160, "bit_depth": 10, "sar": 1.0, "field_order": "progressive"}
    dvd = {"codec": "MPEG-2", "width": 720, "height": 480, "bit_depth": 8, "sar": 32 / 27, "field_order": "tb"}

    def run(video, enc, h=None):
        cmd = stream.hls_cmd(Path("a.mkv"), 0, video, out, encoder=enc, max_height=h)
        pre = cmd[:cmd.index("-i")]
        fmt = pre[pre.index("-hwaccel_output_format") + 1] if "-hwaccel_output_format" in pre else None
        return pre[pre.index("-hwaccel") + 1] if "-hwaccel" in pre else None, fmt, cmd[cmd.index("-vf") + 1]

    assert run(hevc, "h264_qsv", 720) == ("qsv", "qsv", "vpp_qsv=w=1280:h=720:format=nv12,setsar=1")
    assert run(dvd, "h264_qsv") == ("qsv", "qsv", "vpp_qsv=deinterlace=advanced:w=852:h=480:format=nv12,setsar=1")
    monkeypatch.setattr(stream.sys, "platform", "linux")
    hw, fmt, vf = run(dvd, "h264_vaapi")
    assert (hw, fmt) == ("vaapi", "vaapi") and vf == "deinterlace_vaapi=auto=1,scale_vaapi=w=852:h=480:format=nv12,setsar=1"
    cmd = stream.hls_cmd(Path("a.mkv"), 0, hevc, out, encoder="h264_vaapi")
    assert cmd[cmd.index("-hwaccel_device") + 1] == "/dev/dri/renderD128"
    assert cmd[cmd.index("-vf") + 1] == "scale_vaapi=w=3840:h=2160:format=nv12,setsar=1"  # progressive: no deinterlacer
    assert not stream.gpu_filters(hevc, "h264_amf", None, None)  # AMF's all-GPU path is Windows only
    monkeypatch.setattr(stream.sys, "platform", "win32")
    assert run(hevc, "h264_amf", 1080) == ("d3d11va", "d3d11", "vpp_amf=w=1920:h=1080:format=nv12,setsar=1")
    # AMF has no GPU deinterlacer, and Quick Sync isn't trusted with a stream of unknown scan type: hybrid path
    assert not stream.gpu_filters(dvd, "h264_amf", None, None)
    assert not stream.gpu_filters({**dvd, "field_order": None}, "h264_qsv", None, None)
    assert stream.gpu_filters({**dvd, "field_order": None}, "h264_vaapi", None, None)  # auto=1 leaves progressive alone
    # probed before BAMS recorded the pixel aspect: the numbers can't be worked out, so hybrid (the API tops it up)
    assert not stream.gpu_filters({k: v for k, v in hevc.items() if k != "sar"}, "h264_qsv", None, None)
    assert stream.gpu_filters({k: v for k, v in hevc.items() if k != "sar"}, "h264_nvenc", None, None)
    # the same limits as NVIDIA: no HDR, no burn-in, no Hi10P; and the environment can turn it off
    assert not stream.gpu_filters({**hevc, "hdr": "HDR10"}, "h264_qsv", "zscale", None)
    assert not stream.gpu_filters(hevc, "h264_qsv", None, 0)
    assert not stream.gpu_filters({**hevc, "codec": "H.264"}, "h264_qsv", None, None)
    monkeypatch.setenv("BAMS_HWACCEL", "d3d11va")
    assert not stream.gpu_filters(hevc, "h264_qsv", None, None) and stream.gpu_filters(hevc, "h264_amf", None, None)


def test_a_failed_gpu_run_is_remembered(gpu):
    hevc = {"codec": "HEVC", "width": 1920, "height": 1080, "bit_depth": 10, "profile": "Main 10", "sar": 1.0}
    assert stream.gpu_filters(hevc, "h264_qsv", None, None)
    stream.gpu_failed("h264_qsv", hevc)
    assert not stream.gpu_filters(hevc, "h264_qsv", None, None)                  # hybrid from now on
    assert stream.gpu_filters({**hevc, "profile": "Main", "bit_depth": 8}, "h264_qsv", None, None)  # other kinds aren't
    assert stream.gpu_filters(hevc, "h264_nvenc", None, None)


def test_output_size_squares_pixels():
    dvd = {"width": 720, "height": 480, "sar": 32 / 27}  # anamorphic 16:9 NTSC DVD
    assert stream.output_size(dvd, "libx264") == (852, 480)
    assert stream.output_size({"width": 3840, "height": 2160}, "libx264") == (1920, 1080)  # CPU: 1080p at most
    assert stream.output_size({"width": 3840, "height": 1608}, "h264_nvenc", 720) == (1280, 536)
    assert stream.output_size({"width": 0, "height": 0}, "libx264") is None


def test_probe_records_pixel_shape_and_scan_type():
    s = {"codec_type": "video", "codec_name": "mpeg2video", "width": 720, "height": 576,
         "sample_aspect_ratio": "64:45", "field_order": "tt"}
    v = probe.summarize({"format": {}, "streams": [s]})["video"]
    assert v["sar"] == round(64 / 45, 6) and v["field_order"] == "tt" and stream.interlaced(v)
    v = probe.summarize({"format": {}, "streams": [{**s, "sample_aspect_ratio": "0:1", "field_order": "unknown"}]})["video"]
    assert v["sar"] == 1.0 and v["field_order"] is None and stream.interlaced(v) is None
    assert stream.interlaced({"codec": "HEVC"}) is False  # never interlaced in practice


@pytest.mark.skipif(not stream.ffmpeg_path(), reason="FFmpeg not installed")
def test_remux_over_hls_lines_up_across_runs(tmp_path):
    """The audio-only remux as HLS: segments cut at the file's keyframes; a run started mid-file (where the
    MKV index may only let FFmpeg start earlier) still names its segments by where they really begin."""
    media = tmp_path / "media" / "Show"
    media.mkdir(parents=True)
    src = media / "Show - S01E01.mkv"
    subprocess.run([stream.ffmpeg_path(), "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=20",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=20", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-g", "50", "-keyint_min", "50", "-sc_threshold", "0", "-c:a", "ac3", "-ac", "6", str(src)], check=True)
    before = src.read_bytes()
    paths = Paths(tmp_path / "data")
    c = signed_in(create_app(paths, start_scheduler=False))
    try:
        lib = c.post("/api/libraries", json={"name": "TV", "type": "show", "paths": [str(tmp_path / "media")]}).json()
        jobs.run_scan(paths, lib["id"], do_match=False)
        show = c.get(f"/api/libraries/{lib['id']}/items").json()[0]
        season = c.get(f"/api/items/{show['id']}").json()["children"][0]
        ep = c.get(f"/api/items/{season['id']}").json()["children"][0]
        f = c.get(f"/api/items/{ep['id']}").json()["files"][0]
        assert f["audio_tracks"][0]["label"] == "Track 1 · AC3 5.1"
        sess = c.post(f["playback"]["hls_url"], json={"remux": True, "channels": 6, "start": 9}).json()
        assert sess["copy"] and sess["channels"] == 6
        pl = c.get(f"/api/hls/{sess['id']}/0/index.m3u8").text
        # a keyframe every 2 s (FFmpeg 6.1's MKV starts at -0.006 s, AC3 priming: the first and last are 6 ms off)
        durations = [float(d) for d in re.findall(r"#EXTINF:([\d.]+),", pl)]
        assert len(durations) == 10 and all(abs(d - 2) < 0.01 for d in durations)
        assert '#EXT-X-MAP:URI="init.mp4"' in pl
        base = f"/api/hls/{sess['id']}/0"
        init = c.get(f"{base}/init.mp4")
        assert init.status_code == 200
        seg6 = c.get(f"{base}/6.m4s")
        seg0 = c.get(f"{base}/0.m4s")  # back to the start: another FFmpeg run
        assert seg6.status_code == seg0.status_code == 200
        ffprobe = probe.ffprobe_path()

        def first(seg: bytes, name: str) -> dict:
            p = tmp_path / name
            p.write_bytes(init.content + seg)
            r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "stream=codec_name,channels",
                                "-of", "json", str(p)], capture_output=True, check=True)
            v = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time",
                                "-read_intervals", "%+#1", "-of", "csv=p=0", str(p)], capture_output=True, check=True)
            return {**json.loads(r.stdout), "start": float(v.stdout.split()[0])}

        a, b = first(seg6.content, "6.mp4"), first(seg0.content, "0.mp4")
        assert {s["codec_name"] for s in a["streams"]} == {"h264", "aac"}
        assert next(s["channels"] for s in a["streams"] if s["codec_name"] == "aac") == 6
        assert abs(a["start"] - b["start"] - 12.0) < 0.05  # segment 6 starts 12 s after segment 0, from another run
        c.delete(f"/api/hls/{sess['id']}")
        # Dolby pass-through: the player's device decodes AC3, so it's copied as it is (all six channels)
        sess = c.post(f["playback"]["hls_url"], json={"remux": True, "passthrough": True, "start": 9}).json()
        assert sess["passthrough"]
        base = f"/api/hls/{sess['id']}/0"
        init = c.get(f"{base}/init.mp4")
        p = first(c.get(f"{base}/6.m4s").content, "6-pass.mp4")
        assert {(s["codec_name"], s.get("channels")) for s in p["streams"]} == {("h264", None), ("ac3", 6)}
        c.delete(f"/api/hls/{sess['id']}")
        live = tmp_path / "live.mp4"
        live.write_bytes(c.get(f"/api/files/{f['id']}/remux?t=4&passthrough=true").content)
        r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1", str(live)],
                           capture_output=True, text=True, check=True)
        assert r.stdout.split() == ["h264", "ac3"]
        live.write_bytes(c.get(f"/api/files/{f['id']}/remux?t=4").content)  # not asked: converted as before
        r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1", str(live)],
                           capture_output=True, text=True, check=True)
        assert r.stdout.split() == ["h264", "aac"]
        assert src.read_bytes() == before
    finally:
        readonly.set_protected_roots([])


def test_hls_copy_cmd_in_mpeg_ts(monkeypatch, tmp_path):
    monkeypatch.setattr(stream, "ffmpeg_path", lambda: "ffmpeg")
    out = tmp_path / "s" / "0"
    cmd = stream.hls_copy_cmd(Path("a.mkv"), 40, 120.5, "HEVC", out, 0, 6, copy_audio=True, ts=True)
    assert cmd[cmd.index("-hls_segment_type") + 1] == "mpegts" and "-tag:v" not in cmd  # hvc1 is an MP4 tag
    assert cmd[cmd.index("-hls_segment_filename") + 1] == str(out / "%d.ts") and "-hls_fmp4_init_filename" not in cmd
    assert cmd[cmd.index("-start_number") + 1] == "40" and cmd[cmd.index("-c:a") + 1] == "copy"
    assert "-copyts" in cmd and cmd[cmd.index("-output_ts_offset") + 1] == "10"  # runs line up as with fMP4
