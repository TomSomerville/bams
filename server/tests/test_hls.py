import json
import subprocess
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import signed_in
from bams import hls, jobs, probe, readonly, stream
from bams.app import create_app
from bams.config import Paths


class FakeFFmpeg:
    """Stands in for an HLS FFmpeg run: makes `make` segments at once, then one more per poll() while it
    runs (if `grow`), like a real one working through the file."""

    def __init__(self, out: Path, start: int, total: int, make: int = 1, grow: bool = True, rc: int | None = None,
                 ext: str = "ts", init: bool = False):
        self.out, self.next, self.total, self.grow, self.ext = out, start, total, grow, ext
        self.start = start
        self.returncode = rc
        if init:
            (out / f"init_{start}.mp4").write_bytes(b"init")
        for _ in range(make):
            self._make()

    def _make(self):
        if self.next < self.total:
            (self.out / f"{self.next}.{self.ext}").write_bytes(b"ts")
            self.next += 1

    def poll(self):
        if self.returncode is None and self.grow:
            self._make()
        return self.returncode

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


@pytest.fixture
def tc(tmp_path, monkeypatch):
    monkeypatch.setattr(hls, "WAIT", 3.0)  # a broken test fails fast instead of hanging
    monkeypatch.setattr(hls, "POLL", 0.01)
    runs: list[tuple[int, FakeFFmpeg]] = []
    how = {"make": 1, "grow": True, "rc": None}
    limit = [0]
    gpu = []  # the gpu flag of each run

    def cmd(s, v, k):
        gpu.append(v.gpu)
        p = FakeFFmpeg(v.dir, k, total=v.segments, ext=v.ext, init=v.copy, **how)
        runs.append((k, p))
        return p

    starts = {}  # copy variants: where FFmpeg's seek really lands, by requested time
    cwds = []  # the folder each run was started in

    t = hls.Transcodes(tmp_path / "transcode", lambda: limit[0], spawn=lambda c, cwd=None: cwds.append(cwd) or c,
                       cmd=cmd, copy_start=lambda path, at, zero=False: starts.get(round(at, 3), at))
    t.gpu_runs, t.starts, t.cwds = gpu, starts, cwds
    yield t, runs, how, limit
    t.shutdown()


def new(t, duration=1000.0, **kw):
    return t.create(1, Path("film.mkv"), None, duration, **kw)


def test_playlists():
    v = hls.Variant(0, hls.uniform_bounds(10.5), 10.5, Path("d"))
    pl = v.playlist()
    assert pl.count("#EXTINF") == 3 and "#EXTINF:2.500," in pl and pl.rstrip().endswith("#EXT-X-ENDLIST")
    assert "#EXT-X-PLAYLIST-TYPE:VOD" in pl and "\n2.ts" in pl
    c = hls.Variant(0, hls.copy_bounds([0.042, 2.0, 7.5]), 9.0, Path("d"), copy=True)
    pl = c.playlist()  # copy: cut at the file's keyframes, fMP4 with a header
    assert '#EXT-X-MAP:URI="init.mp4"' in pl and "#EXTINF:2.000,\n0.m4s" in pl and "#EXTINF:1.500,\n2.m4s" in pl
    assert "#EXT-X-TARGETDURATION:6" in pl and c.at(7.4) == 1 and c.at(7.5) == 2
    s = hls.Session("x", 1, Path("a"), None, 0, 10.5, Path("d"), [
        hls.Variant(0, [0.0], 10.5, Path("d"), height=None, bandwidth=5_200_000, resolution=(1920, 1080)),
        hls.Variant(1, [0.0], 10.5, Path("d"), height=720, bandwidth=3_200_000, resolution=(1280, 720))])
    master = s.playlist()
    assert "BANDWIDTH=5200000,RESOLUTION=1920x1080\n0/index.m3u8" in master and "1/index.m3u8" in master


def test_ladder():
    v1080 = {"width": 1920, "height": 1080}
    assert hls.ladder(v1080, "h264_nvenc") == [None, 720, 480]
    assert hls.ladder({"width": 3840, "height": 2160}, "libx264") == [None, 720, 480]  # CPU: full = 1080p
    assert hls.ladder({"width": 3840, "height": 2160}, "h264_nvenc") == [None, 1080, 720, 480]
    assert hls.ladder({"width": 720, "height": 480}, "h264_nvenc") == [None]  # a DVD: nothing smaller worth it
    assert hls.output_size({"width": 1920, "height": 800}, "h264_nvenc", 720) == (1280, 532)


def test_segments_are_made_on_demand(tc):
    t, runs, how, _ = tc
    s = new(t)
    assert t.segment(s, 0, 0).name == "0.ts" and [k for k, _ in runs] == [0]
    assert t.segment(s, 0, 3).exists() and len(runs) == 1    # coming soon from the same run: waited for
    t.segment(s, 0, 60)                                      # a seek far ahead: FFmpeg restarts there
    assert [k for k, _ in runs] == [0, 60] and runs[0][1].returncode == -9
    assert t.segment(s, 0, 2).exists() and len(runs) == 2    # already on disk: served as-is
    t.segment(s, 0, 30)                                      # behind the current run: restart
    assert [k for k, _ in runs] == [0, 60, 30]
    with pytest.raises(KeyError):
        t.segment(s, 0, 250)                                 # past the end of the playlist
    with pytest.raises(KeyError):
        t.segment(s, 1, 0)                                   # no such variant


def test_first_run_starts_where_the_player_does(tc):
    t, runs, _, _ = tc
    s = new(t, start=605.0)
    assert s.variants[0].wanted == 151
    t.segment(s, 0, 151)
    assert [k for k, _ in runs] == [151]


def test_superseded_request_gives_up(tc):
    t, runs, how, _ = tc
    s = new(t)
    how.update(make=0, grow=False)  # this run never gets anywhere
    result = {}

    def ask():
        try:
            t.segment(s, 0, 40)
        except hls.SegmentGone:
            result["gone"] = True

    th = threading.Thread(target=ask)
    th.start()
    while not runs:
        pass
    how.update(make=1, grow=True)
    assert t.segment(s, 0, 5).exists()  # the player seeked to 5: that request wins
    th.join(5)
    assert result == {"gone": True} and [k for k, _ in runs] == [40, 5]


def test_ffmpeg_failure_and_real_end(tc):
    t, runs, how, _ = tc
    how.update(make=0, grow=False, rc=1)
    with pytest.raises(RuntimeError, match="exit code 1"):
        t.segment(new(t), 0, 0)
    assert t.gpu_runs == [True, False]  # one retry without the GPU filters, then the error
    how.update(rc=0)
    with pytest.raises(KeyError):  # FFmpeg finished without making it: past the real end of the video
        t.segment(new(t), 0, 0)


def test_reaper_stops_runs_far_ahead_and_prunes(tc):
    t, runs, how, _ = tc
    s = new(t)
    v = s.variants[0]
    how.update(make=int(hls.AHEAD / stream.SEGMENT) + 5, grow=False)
    t.segment(s, 0, 0)
    (v.dir / "200.ts").write_bytes(b"old")  # far from the playhead
    t.reap()
    assert runs[0][1].returncode == -9 and v.killed  # 20 made, 15 is enough ahead of segment 0
    assert not (v.dir / "200.ts").exists() and (v.dir / "19.ts").exists()
    how.update(make=1, grow=True)
    t.segment(s, 0, 20)  # the player caught up: FFmpeg starts again where it stopped
    assert [k for k, _ in runs] == [0, 20]


def test_automatic_quality_switch_stops_the_old_size(tc):
    t, runs, how, _ = tc
    s = new(t, heights=[None, 720, 480])
    assert len(s.variants) == 3 and s.variants[1].height == 720
    t.segment(s, 0, 0)
    t.segment(s, 2, 1)  # the player dropped to 480p
    assert [k for k, _ in runs] == [0, 1] and runs[0][1].returncode is None
    s.variants[0].last_access -= hls.SWITCHED + 1
    t.reap()
    assert runs[0][1].returncode == -9 and runs[1][1].returncode is None  # only the abandoned size stops
    assert t.running() == 1  # several sizes are still one conversion


def test_copy_variant_numbers_segments_where_ffmpeg_really_starts(tc):
    t, runs, how, limit = tc
    limit[0] = 1
    t.create(2, Path("x.mkv"), None, 100.0, heights=[None])  # a conversion takes the only place...
    kf = [0.0, 2.0, 4.5, 9.0, 11.0, 15.0, 40.0, 60.0, 80.0]
    s = new(t, duration=100.0, keyframes=kf)  # ...but a copy isn't a conversion
    v = s.variants[0]
    assert v.copy and v.segments == 9 and v.ext == "m4s"
    assert t.init(s, 0).name == "init_0.mp4"  # the header comes from the first run
    assert t.cwds[-1] == v.dir  # FFmpeg runs in the variant's folder: the init file name is a bare one
    t.starts[60.001] = 40.0  # the file's index only lets FFmpeg start a keyframe earlier
    assert t.segment(s, 0, 7).name == "7.m4s"
    assert [k for k, _ in runs] == [0, 6]


def test_idle_session_is_closed(tc):
    t, runs, _, _ = tc
    s = new(t)
    t.segment(s, 0, 0)
    s.last_access -= hls.IDLE + 1
    t.reap()
    assert not s.dir.exists() and runs[0][1].returncode == -9
    with pytest.raises(KeyError):
        t.get(s.id)


def test_limit_on_simultaneous_conversions(tc):
    t, runs, how, limit = tc
    limit[0] = 1
    a = new(t)
    t.segment(a, 0, 0)
    with pytest.raises(hls.Busy, match="already converting 1 video"):
        new(t)
    t.segment(a, 0, 100)  # its own restart doesn't count against it
    t.close(a.id)
    b = new(t)  # room again
    t.segment(b, 0, 0)
    t.close(b.id)
    t.add_pipe(FakeFFmpeg(t.root, 0, 0))  # a plain fMP4 transcode counts too, while it runs
    with pytest.raises(hls.Busy):
        t.check()


def test_keyframe_cache(tmp_path):
    calls = []

    def read(p):
        calls.append(p)
        return [0.0, 2.0]

    k = hls.Keyframes(tmp_path / "kf", read=read)
    assert k.get(7, Path("a.mkv"), 10, 1) == [0.0, 2.0]
    assert hls.Keyframes(tmp_path / "kf", read=read).get(7, Path("a.mkv"), 10, 1) == [0.0, 2.0]  # from disk
    assert len(calls) == 1
    k.get(7, Path("a.mkv"), 10, 2)  # the file changed: read again, the old list is dropped
    assert len(calls) == 2 and [f.name for f in (tmp_path / "kf").iterdir()] == ["7-10-2.json"]


@pytest.mark.skipif(not stream.ffmpeg_path() or not stream.video_encoder(), reason="FFmpeg/H.264 encoder not installed")
def test_hls_through_the_api(tmp_path):
    media = tmp_path / "media" / "Old Film (1999)"
    media.mkdir(parents=True)
    src = media / "Old Film (1999).avi"
    subprocess.run([stream.ffmpeg_path(), "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=18",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=18", "-c:v", "mpeg4", "-vtag", "XVID",
                    "-c:a", "libmp3lame", str(src)], check=True)
    before = src.read_bytes()
    paths = Paths(tmp_path / "data")
    c = signed_in(create_app(paths, start_scheduler=False))
    try:
        lib = c.post("/api/libraries", json={"name": "Movies", "type": "movie", "paths": [str(tmp_path / "media")]}).json()
        jobs.run_scan(paths, lib["id"], do_match=False)
        movie = c.get(f"/api/libraries/{lib['id']}/items").json()[0]
        f = c.get(f"/api/items/{movie['id']}").json()["files"][0]
        assert f["playback"]["hls_url"] == f"/api/files/{f['id']}/hls"

        sess = c.post(f["playback"]["hls_url"], json={"height": 180}).json()
        master = c.get(sess["playlist"])
        assert master.status_code == 200 and master.text.count("#EXT-X-STREAM-INF") == 1
        base = sess["playlist"].rsplit("/", 1)[0] + "/0"
        pl = c.get(f"{base}/index.m3u8")
        assert pl.status_code == 200 and pl.text.count("#EXTINF") == 5  # 18 s in 4 s segments

        seg = c.get(f"{base}/3.ts")  # a seek straight to 12 s
        assert seg.status_code == 200 and seg.headers["content-type"] == "video/mp2t"
        (tmp_path / "3.ts").write_bytes(seg.content)
        first = c.get(f"{base}/0.ts")  # then back to the start: FFmpeg restarts
        assert first.status_code == 200
        (tmp_path / "0.ts").write_bytes(first.content)
        ffprobe = probe.ffprobe_path()

        def video_start(p):
            r = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                                "stream=codec_name,height:packet=pts_time", "-read_intervals", "%+#1", "-of", "json",
                                str(p)], capture_output=True, check=True)
            d = json.loads(r.stdout)
            return d["streams"][0]["codec_name"], d["streams"][0]["height"], float(d["packets"][0]["pts_time"])

        codec, height, t3 = video_start(tmp_path / "3.ts")
        _, _, t0 = video_start(tmp_path / "0.ts")
        assert codec == "h264" and height == 180  # the quality the player asked for
        assert abs((t3 - t0) - 12.0) < 0.1      # segment 3 starts 12 s after segment 0, from another run

        assert c.get(f"{base}/99.ts").status_code == 404
        s = c.app.state.transcodes.get(sess["id"])
        assert c.delete(f"/api/hls/{sess['id']}").status_code == 204
        assert not s.dir.exists() and c.get(sess["playlist"]).status_code == 404

        auto = c.post(f["playback"]["hls_url"], json={"auto": True}).json()
        assert len(auto["variants"]) == 1  # a 240p film has nothing smaller in the ladder
        c.delete(f"/api/hls/{auto['id']}")
        assert src.read_bytes() == before  # the media file is untouched
    finally:
        readonly.set_protected_roots([])


def test_transcoding_limit_setting(tmp_path):
    c = signed_in(create_app(Paths(tmp_path / "data"), start_scheduler=False))
    s = c.get("/api/settings").json()
    assert s["max_transcodes"] == 0 and s["max_transcodes_auto"] in (2, 4)
    assert c.put("/api/settings/transcoding", json={"max_transcodes": 3}).json()["limit"] == 3
    assert c.get("/api/settings").json()["max_transcodes"] == 3
    assert c.get("/api/status").json()["transcodes"] == {"running": 0, "limit": 3}
    assert c.put("/api/settings/transcoding", json={"max_transcodes": -1}).status_code == 422


def test_copy_variant_in_mpeg_ts():
    """The TV app's copy: TS segments, no fMP4 header (Samsung's player takes no fMP4 HLS)."""
    c = hls.Variant(0, hls.copy_bounds([0.042, 2.0, 7.5]), 9.0, Path("d"), copy=True, ts=True)
    pl = c.playlist()
    assert "#EXT-X-MAP" not in pl and "#EXTINF:2.000,\n0.ts" in pl and "#EXT-X-VERSION:3" in pl
    assert c.file(2) == Path("d") / "2.ts"
