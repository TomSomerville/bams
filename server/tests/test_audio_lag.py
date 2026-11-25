"""Files that store their sound far from the picture it plays with (a converter's output, or a remux that fixed its
timestamps: the sound for 0:00 next to the picture for 2:21). FFmpeg reads a file in order, so a conversion wrote the
first segments without sound and the sound later with times belonging to other segments: browsers that need the
conversion (HEVC in Helium) played the film silent. `stream.audio_lags` finds such files and conversions read their
sound through an input of its own."""
import json
import subprocess
from pathlib import Path

import pytest

from conftest import signed_in
from bams import hls, jobs, probe, readonly, stream
from bams.app import create_app
from bams.config import Paths

pytestmark = pytest.mark.skipif(not stream.ffmpeg_path() or not probe.ffprobe_path() or not stream.video_encoder(),
                                reason="FFmpeg/ffprobe/H.264 encoder not installed")

LENGTH = 32  # seconds
LAG = 20     # how far behind its picture the sound is stored

# HEVC like the real files (falls back to H.264 where FFmpeg has no libx265: the layout is what matters), with
# AAC as converters leave it: 5.1 whose layout ffprobe calls "unknown" (channel config 0 + PCE), mono, and stereo
# with no language and default=0
AUDIO = {
    "surround": ["-af", "pan=5.1|c0=c0|c1=c0|c2=c0|c3=c0|c4=c0|c5=c0", "-c:a", "aac", "-aac_pce", "1", "-b:a", "384k"],
    "mono": ["-ac", "1", "-c:a", "aac"],
    "stereo": ["-ac", "2", "-c:a", "aac", "-disposition:a", "0"],
}
CHANNELS = {"surround": 6, "mono": 1, "stereo": 2}


def _ffmpeg(*args: str) -> None:
    subprocess.run([stream.ffmpeg_path(), "-v", "error", "-y", "-nostdin", *args], check=True)


def _video_codec() -> list[str]:
    encoders = subprocess.run([stream.ffmpeg_path(), "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    if " libx265 " in encoders:
        return ["-c:v", "libx265", "-x265-params", "log-level=error", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-pix_fmt", "yuv420p"]


def make_clip(folder: Path, kind: str, lag: bool) -> Path:
    """A clip with `kind` sound; `lag`: the sound stored LAG s behind its picture. Made the way such files come about:
    the sound offset when muxed (so it's stored late), then its timestamps moved back in a copy whose muxer doesn't
    wait for it (`-max_interleave_delta`)."""
    folder.mkdir(parents=True, exist_ok=True)
    keep = ["-disposition:a", "0"] if kind == "stereo" else []  # FFmpeg would mark the only audio track default
    base = folder / f"{kind}-base.mkv"
    _ffmpeg("-f", "lavfi", "-i", f"testsrc2=s=320x240:r=24:d={LENGTH}",
            "-f", "lavfi", "-i", f"anoisesrc=sample_rate=48000:amplitude=0.3:d={LENGTH}",
            "-map", "0:v", "-map", "1:a", *_video_codec(), "-g", "48", *AUDIO[kind], "-map_metadata", "-1", str(base))
    if not lag:
        return base
    shifted = folder / f"{kind}-shifted.mkv"
    _ffmpeg("-i", str(base), "-itsoffset", str(LAG), "-i", str(base), "-map", "0:v", "-map", "1:a", "-c", "copy",
            *keep, str(shifted))
    out = folder / f"{kind}.mkv"
    _ffmpeg("-i", str(shifted), "-map", "0", "-c", "copy", "-bsf:a", f"setts=ts=TS-{LAG}/TB",
            "-max_interleave_delta", "1", *keep, str(out))
    base.unlink()
    shifted.unlink()
    return out


@pytest.fixture(scope="module")
def clips(tmp_path_factory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("lag")
    made = {kind: make_clip(d / "media" / f"{kind.title()} (2001)", kind, lag=True) for kind in AUDIO}
    made["interleaved"] = make_clip(d / "plain", "mono", lag=False)
    return made


def packets(path: Path, kind: str) -> list[float]:
    r = subprocess.run([probe.ffprobe_path(), "-v", "error", "-select_streams", kind, "-show_entries",
                        "packet=pts_time", "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return sorted(float(x.strip(",")) for x in r.stdout.split() if x.strip(",") not in ("", "N/A"))


def loudest(path: Path) -> float:
    r = subprocess.run([stream.ffmpeg_path(), "-hide_banner", "-nostdin", "-i", str(path), "-map", "0:a:0",
                        "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    line = next((x for x in r.stderr.splitlines() if "max_volume" in x), None)
    return float(line.split("max_volume:")[1].split("dB")[0]) if line else -999.0


def assert_has_sound(segment: Path, channels: int = 2) -> None:
    """The segment's sound covers the same stretch as its picture (not missing, not from elsewhere in the film)."""
    video, audio = packets(segment, "v"), packets(segment, "a")
    assert video and audio, f"{segment.name}: no sound"
    assert abs(audio[0] - video[0]) < 0.5 and abs(audio[-1] - video[-1]) < 0.5, (segment.name, audio[:1], video[:1])
    assert loudest(segment) > -30
    r = subprocess.run([probe.ffprobe_path(), "-v", "error", "-select_streams", "a:0", "-show_entries",
                        "stream=channels", "-of", "json", str(segment)], capture_output=True, check=True)
    assert json.loads(r.stdout)["streams"][0]["channels"] == channels


def test_the_clips_are_like_the_real_files(clips):
    for kind in AUDIO:
        a = probe.probe(clips[kind])["audio"][0]
        assert a["codec"] == "AAC" and a["channels"] == CHANNELS[kind] and a["language"] is None
    assert probe.probe(clips["surround"])["audio"][0]["layout"] is None  # ffprobe: "unknown" (JSON leaves it out)
    assert probe.probe(clips["stereo"])["audio"][0]["default"] is False
    assert abs(packets(clips["mono"], "a")[0]) < 0.1  # the sound itself starts at 0: it's only stored late


def test_audio_lags(clips):
    for kind in AUDIO:
        assert stream.audio_lags(clips[kind]) is True
        assert stream.audio_lags(clips[kind], 0, 12.0) is True  # cached; the same either way
    assert stream.audio_lags(clips["interleaved"]) is False
    assert stream.audio_lags(clips["mono"], 1) is False          # no such track
    assert stream.audio_lags(Path("/no/such/file.mkv")) is False


def _hls(path: Path, out: Path, segment: int, split: bool, channels: int = 2) -> None:
    out.mkdir(parents=True)
    cmd = stream.hls_cmd(path, segment, probe.probe(path)["video"], out, 0, max_height=180, channels=channels,
                         split_audio=split)
    subprocess.run(cmd, check=True, capture_output=True)


def test_hls_without_its_own_audio_input_loses_the_sound(clips, tmp_path):
    """What went wrong: the first segments had no sound at all."""
    _hls(clips["mono"], tmp_path / "old", 0, split=False)
    assert packets(tmp_path / "old" / "0.ts", "v") and not packets(tmp_path / "old" / "0.ts", "a")


def test_hls_segments_carry_the_sound(clips, tmp_path):
    for kind in AUDIO:
        for start in (0, 3):  # from the beginning, and a seek to 12 s (a new FFmpeg run)
            out = tmp_path / kind / str(start)
            _hls(clips[kind], out, start, split=True)
            for k in range(start, start + 3):
                assert_has_sound(out / f"{k}.ts")
    out = tmp_path / "surround-51"
    _hls(clips["surround"], out, 0, split=True, channels=6)  # the viewer asked for 5.1
    assert_has_sound(out / "1.ts", channels=6)


def test_copy_hls_without_its_own_audio_input_loses_the_sound(clips, tmp_path):
    """The TV apps' copy (video copied, sound converted) had the same problem."""
    out = tmp_path / "old"
    out.mkdir()
    subprocess.run(stream.hls_copy_cmd(clips["mono"], 0, 0.0, "HEVC", out, ts=True), check=True, capture_output=True,
                   cwd=out)
    assert packets(out / "0.ts", "v") and not packets(out / "0.ts", "a")


@pytest.mark.parametrize("ts", [True, False], ids=["samsung-mpegts", "firetv-fmp4"])
def test_copy_hls_carries_the_sound(clips, tmp_path, ts):
    """Through an HLS session as the TV apps get it: the session finds out by itself, and a run after a seek (whose
    picture starts at the keyframe its seek lands on: `remux_start`) gets its sound from that very point."""
    for kind in ("surround", "stereo"):
        src = clips[kind]
        kf = stream.keyframes(src)
        t = hls.Transcodes(tmp_path / f"transcode-{kind}-{ts}", lambda: 0)
        try:
            s = t.create(1, src, None, float(LENGTH), keyframes=kf, video_codec="HEVC", ts=ts)
            assert s.split_audio
            init = b"" if ts else t.init(s, 0).read_bytes()

            def check(k: int) -> None:
                f = tmp_path / f"{kind}-{ts}-{k}.{'ts' if ts else 'mp4'}"
                f.write_bytes(init + t.segment(s, 0, k).read_bytes())
                assert_has_sound(f)

            for k in (0, 1, 2):
                check(k)
            s.last_access -= hls.IDLE + 1  # paused past the idle limit: asleep, segments deleted
            t.reap()
            assert s.asleep
            for k in (8, 9):  # then a seek to 16 s: a new FFmpeg run with a real seek
                check(k)
            v = s.variants[0]
            assert v.runs == 2 and v.seek > 15 and v.landed > 0
        finally:
            t.shutdown()


def _pcm(f: Path, at: float, length: float, rate: int = 2000):
    import array
    return array.array("h", subprocess.run([stream.ffmpeg_path(), "-v", "error", "-ss", f"{at:.3f}", "-i", str(f),
                                            "-t", str(length), "-vn", "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
                                           capture_output=True, check=True).stdout)


def _found_at(a, b) -> int:
    """Where (in samples) `a` best matches inside `b` (normalized correlation)."""
    na = sum(x * x for x in a) ** .5
    score = [sum(x * y for x, y in zip(a, b[s:])) / (na * sum(y * y for y in b[s:s + len(a)]) ** .5 + 1e-9)
             for s in range(len(b) - len(a))]
    return max(range(len(score)), key=score.__getitem__)


def test_live_remux_carries_the_sound_in_step(clips, tmp_path):
    """The browsers' live remux (video copied from the keyframe at/before the seek, sound converted): the sound must
    come with the picture in the stream, not 20 s behind it, and match it (the copied picture starts a keyframe
    early; the sound's own input has to start exactly there)."""
    src = clips["surround"]
    assert stream.audio_lags(src)
    old = tmp_path / "old.mp4"
    old.write_bytes(subprocess.run(stream.remux_cmd(src, 0, "HEVC"), capture_output=True, check=True).stdout)
    assert loudest_in_first(old, 4) < -60  # the old stream: the first seconds came without sound
    for start in (0.0, 9.5):
        landed = stream.remux_start(src, start, zero=True)
        out = tmp_path / f"remux-{start}.mp4"
        out.write_bytes(subprocess.run(stream.remux_cmd(src, start, "HEVC", split_audio=True),
                                       capture_output=True, check=True).stdout)
        assert loudest_in_first(out, 4) > -30
        video, audio = packets(out, "v"), packets(out, "a")
        assert abs(audio[0] - video[0]) < 0.2 and abs(audio[-1] - video[-1]) < 0.2
        # 3 s in, the sound is the source's at landed + 3 s (a wrong clock would be off by start - landed, ~1.5 s)
        s = _found_at(_pcm(out, 3, 0.25), _pcm(src, landed + 3 - 0.3, 0.85))
        assert abs((landed + 3 - 0.3 + s / 2000) - (landed + 3)) < 0.15, s


def loudest_in_first(f: Path, seconds: float) -> float:
    """The loudest sound in the first `seconds` of the file *as it streams*: read as a pipe, so a player that
    gets the sound only later (stored late in the stream) hears nothing here."""
    data = f.read_bytes()
    r = subprocess.run([stream.ffmpeg_path(), "-hide_banner", "-nostdin", "-f", "mp4", "-i", "pipe:0", "-t",
                        str(seconds), "-map", "0:a:0?", "-af", "volumedetect", "-f", "null", "-"],
                       input=data[:len(data) * seconds // LENGTH], capture_output=True)
    line = next((x for x in r.stderr.decode(errors="replace").splitlines() if "max_volume" in x), None)
    return float(line.split("max_volume:")[1].split("dB")[0]) if line else -999.0


def test_live_transcode_carries_the_sound(clips, tmp_path):
    for start in (0.0, 9.5):
        cmd = stream.transcode_cmd(clips["surround"], start, probe.probe(clips["surround"])["video"], 0,
                                   max_height=180, split_audio=True)
        out = tmp_path / f"live-{start}.mp4"
        out.write_bytes(subprocess.run(cmd, capture_output=True, check=True).stdout)
        video, audio = packets(out, "v"), packets(out, "a")
        assert audio and abs(audio[0] - video[0]) < 0.5 and abs(audio[-1] - video[-1]) < 0.5
        assert abs(video[-1] - (LENGTH - start)) < 1 and loudest(out) > -30


def test_through_the_api(clips, tmp_path):
    """The player's way in: the session and the live stream find out by themselves; the audio track the player
    picks for a track with no language and default=0 is the first."""
    media = clips["mono"].parent.parent
    paths = Paths(tmp_path / "data")
    c = signed_in(create_app(paths, start_scheduler=False))
    try:
        lib = c.post("/api/libraries", json={"name": "Movies", "type": "movie", "paths": [str(media)]}).json()
        jobs.run_scan(paths, lib["id"], do_match=False)
        items = c.get(f"/api/libraries/{lib['id']}/items").json()
        assert len(items) == len(AUDIO)
        for it in items:
            f = c.get(f"/api/items/{it['id']}").json()["files"][0]
            assert [t["index"] for t in f["audio_tracks"]] == [0]
            sess = c.post(f["playback"]["hls_url"], json={"height": 180, "audio": 0}).json()
            base = sess["playlist"].rsplit("/", 1)[0] + "/0"
            for k in (0, 5):  # the start, then a seek to 20 s
                seg = c.get(f"{base}/{k}.ts")
                assert seg.status_code == 200
                (tmp_path / f"{k}.ts").write_bytes(seg.content)
                assert_has_sound(tmp_path / f"{k}.ts")
            c.delete(f"/api/hls/{sess['id']}")
        live = c.get(f"{f['playback']['transcode_url']}?t=4&h=180")
        assert live.status_code == 200
        (tmp_path / "live.mp4").write_bytes(live.content)
        assert packets(tmp_path / "live.mp4", "a") and loudest(tmp_path / "live.mp4") > -30
    finally:
        readonly.set_protected_roots([])
