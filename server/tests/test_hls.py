import json
import subprocess
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bams import hls, jobs, probe, readonly, stream
from bams.app import create_app
from bams.config import Paths


class FakeFFmpeg:
    """Stands in for an HLS FFmpeg run: makes `make` segments at once, then one more per poll() while it
    runs (if `grow`), like a real one working through the file."""

    def __init__(self, out: Path, start: int, total: int, make: int = 1, grow: bool = True, rc: int | None = None):
        self.out, self.next, self.total, self.grow = out, start, total, grow
        self.returncode = rc
        for _ in range(make):
            self._make()

    def _make(self):
        if self.next < self.total:
            (self.out / f"{self.next}.ts").write_bytes(b"ts")
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

    def cmd(path, k, video, out, audio, max_height=None):
        p = FakeFFmpeg(out, k, total=250, **how)
        runs.append((k, p))
        return p

    t = hls.Transcodes(tmp_path / "transcode", lambda: limit[0], spawn=lambda c: c, cmd=cmd)
    yield t, runs, how, limit
    t.shutdown()


def new(t, duration=1000.0):
    return t.create(1, Path("film.mkv"), None, duration)


def test_playlist_lists_every_segment():
    s = hls.Session("x", 1, Path("a"), None, 0, None, 10.5, Path("d"))
    pl = s.playlist()
    assert pl.count("#EXTINF") == 3 and "#EXTINF:2.500," in pl and pl.rstrip().endswith("#EXT-X-ENDLIST")
    assert "#EXT-X-PLAYLIST-TYPE:VOD" in pl and "\n2.ts" in pl


def test_segments_are_made_on_demand(tc):
    t, runs, how, _ = tc
    s = new(t)
    assert t.segment(s, 0).name == "0.ts" and [k for k, _ in runs] == [0]
    assert t.segment(s, 3).exists() and len(runs) == 1    # coming soon from the same run: waited for
    t.segment(s, 60)                                      # a seek far ahead: FFmpeg restarts there
    assert [k for k, _ in runs] == [0, 60] and runs[0][1].returncode == -9
    assert t.segment(s, 2).exists() and len(runs) == 2    # already on disk: served as-is
    t.segment(s, 30)                                      # behind the current run: restart
    assert [k for k, _ in runs] == [0, 60, 30]
    with pytest.raises(KeyError):
        t.segment(s, 250)                                 # past the end of the playlist


def test_superseded_request_gives_up(tc):
    t, runs, how, _ = tc
    s = new(t)
    how.update(make=0, grow=False)  # this run never gets anywhere
    result = {}

    def ask():
        try:
            t.segment(s, 40)
        except hls.SegmentGone:
            result["gone"] = True

    th = threading.Thread(target=ask)
    th.start()
    while not runs:
        pass
    how.update(make=1, grow=True)
    assert t.segment(s, 5).exists()  # the player seeked to 5: that request wins
    th.join(5)
    assert result == {"gone": True} and [k for k, _ in runs] == [40, 5]


def test_ffmpeg_failure_and_real_end(tc):
    t, runs, how, _ = tc
    how.update(make=0, grow=False, rc=1)
    with pytest.raises(RuntimeError, match="exit code 1"):
        t.segment(new(t), 0)
    how.update(rc=0)
    with pytest.raises(KeyError):  # FFmpeg finished without making it: past the real end of the video
        t.segment(new(t), 0)


def test_reaper_stops_runs_far_ahead_and_prunes(tc):
    t, runs, how, _ = tc
    s = new(t)
    how.update(make=hls.AHEAD + 5, grow=False)
    t.segment(s, 0)
    (s.dir / "200.ts").write_bytes(b"old")  # far from the playhead
    t.reap()
    assert runs[0][1].returncode == -9 and s.killed  # 20 made, 15 is enough ahead of segment 0
    assert not (s.dir / "200.ts").exists() and (s.dir / "19.ts").exists()
    how.update(make=1, grow=True)
    t.segment(s, 20)  # the player caught up: FFmpeg starts again where it stopped
    assert [k for k, _ in runs] == [0, 20]


def test_idle_session_is_closed(tc):
    t, runs, _, _ = tc
    s = new(t)
    t.segment(s, 0)
    s.last_access -= hls.IDLE + 1
    t.reap()
    assert not s.dir.exists() and runs[0][1].returncode == -9
    with pytest.raises(KeyError):
        t.get(s.id)


def test_limit_on_simultaneous_conversions(tc):
    t, runs, how, limit = tc
    limit[0] = 1
    a = new(t)
    t.segment(a, 0)
    with pytest.raises(hls.Busy, match="already converting 1 video"):
        new(t)
    t.segment(a, 100)  # its own restart doesn't count against it
    t.close(a.id)
    b = new(t)  # room again
    t.segment(b, 0)
    t.close(b.id)
    t.add_pipe(FakeFFmpeg(t.root, 0, 0))  # a plain fMP4 transcode counts too, while it runs
    with pytest.raises(hls.Busy):
        t.check()


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
    c = TestClient(create_app(paths, start_scheduler=False))
    try:
        lib = c.post("/api/libraries", json={"name": "Movies", "type": "movie", "paths": [str(tmp_path / "media")]}).json()
        jobs.run_scan(paths, lib["id"], do_match=False)
        movie = c.get(f"/api/libraries/{lib['id']}/items").json()[0]
        f = c.get(f"/api/items/{movie['id']}").json()["files"][0]
        assert f["playback"]["hls_url"] == f"/api/files/{f['id']}/hls"

        sess = c.post(f["playback"]["hls_url"], json={"height": 180}).json()
        pl = c.get(sess["playlist"])
        assert pl.status_code == 200 and pl.text.count("#EXTINF") == 5  # 18 s in 4 s segments

        base = sess["playlist"].rsplit("/", 1)[0]
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
        assert src.read_bytes() == before  # the media file is untouched
    finally:
        readonly.set_protected_roots([])


def test_transcoding_limit_setting(tmp_path):
    c = TestClient(create_app(Paths(tmp_path / "data"), start_scheduler=False))
    s = c.get("/api/settings").json()
    assert s["max_transcodes"] == 0 and s["max_transcodes_auto"] in (2, 4)
    assert c.put("/api/settings/transcoding", json={"max_transcodes": 3}).json()["limit"] == 3
    assert c.get("/api/settings").json()["max_transcodes"] == 3
    assert c.get("/api/status").json()["transcodes"] == {"running": 0, "limit": 3}
    assert c.put("/api/settings/transcoding", json={"max_transcodes": -1}).status_code == 422
