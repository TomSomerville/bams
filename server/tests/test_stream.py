import json
import subprocess

import pytest
from fastapi.testclient import TestClient

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
    monkeypatch.setattr(stream, "_encoder_works", lambda exe, enc: tried.append(enc) or enc in works)
    monkeypatch.delenv("BAMS_VIDEO_ENCODER", raising=False)
    return works, tried


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
    c = TestClient(create_app(paths, start_scheduler=False))
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
    c = TestClient(create_app(paths, start_scheduler=False))
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
