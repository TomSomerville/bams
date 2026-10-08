import json
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
    assert fmp4[fmp4.index("-itsoffset") + 1] == "-12.000" and "[1:s:0]" in fmp4[fmp4.index("-filter_complex") + 1]
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
    assert cmd[cmd.index("-hls_fmp4_init_filename") + 1] == str(out / "init_40.mp4")  # in the data dir
    assert cmd[cmd.index("-hls_segment_filename") + 1] == str(out / "%d.m4s")
    assert "0:a:1?" in cmd and cmd[cmd.index("-ac") + 1] == "6"


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
        assert pl.count("#EXTINF:2.000,") == 10 and '#EXT-X-MAP:URI="init.mp4"' in pl  # a keyframe every 2 s
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
        assert src.read_bytes() == before
    finally:
        readonly.set_protected_roots([])
