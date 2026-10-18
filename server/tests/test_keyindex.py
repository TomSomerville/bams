"""Keyframes from the file's index (keyindex) must equal what ffprobe finds reading every packet, or not be used."""

import subprocess
from pathlib import Path

import pytest

from bams import hls, keyindex, probe, stream

pytestmark = pytest.mark.skipif(not stream.ffmpeg_path(), reason="FFmpeg not installed")

# keyframes at uneven times (x264 adds none of its own: -g is longer than the clip), B-frames on (ctts, edit lists)
KEYS = "0,1.3,2.9,3.4,5,7.7,8.1,11,14.2,15.04,17.5"


def make(path: Path, *out: str, video_in: tuple[str, ...] = ()) -> Path:
    cmd = [stream.ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y", *video_in,
           "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=20",
           "-f", "lavfi", "-i", "sine=frequency=440:duration=20",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "1000", "-sc_threshold", "0", "-bf", "3",
           "-force_key_frames", KEYS, "-c:a", "aac", *out]
    subprocess.run(cmd, check=True, timeout=120)
    return path


def full_read(path: Path, monkeypatch) -> list[float] | None:
    with monkeypatch.context() as m:
        m.setattr(keyindex, "read", lambda p: None)
        return stream.keyframes(path)


@pytest.mark.parametrize("name,out", [
    ("film.mkv", ()),
    ("film.mp4", ()),
    ("faststart.mp4", ("-movflags", "+faststart")),
    ("film.mov", ()),
])
def test_index_gives_the_same_keyframes_as_reading_the_packets(tmp_path, monkeypatch, name, out):
    p = make(tmp_path / name, *out, str(tmp_path / name))
    assert keyindex.read(p), "the index should be used"
    want = full_read(p, monkeypatch)
    assert len(want) == len(KEYS.split(","))
    assert stream.keyframes(p) == want


def test_delayed_video_track(tmp_path, monkeypatch):
    """The video starts 1.5 s after the sound: an empty edit in MP4, a later first block in Matroska."""
    for name in ("late.mp4", "late.mkv"):
        p = make(tmp_path / name, str(tmp_path / name), video_in=("-itsoffset", "1.5"))
        assert keyindex.read(p)
        want = full_read(p, monkeypatch)
        assert stream.keyframes(p) == want
        assert want[0] >= 1.4 or name == "late.mp4"  # FFmpeg 6.1 (Ubuntu 24.04) counts that MP4 track from 0


def edit_cues(p: Path, change) -> None:
    """Change the CuePoints of a Matroska file in place, keeping every size: change(n, data, at) for the n-th."""
    data = bytearray(p.read_bytes())
    cues = data.rindex(b"\x1c\x53\xbb\x6b")
    size, n = keyindex._vint(data, cues + 4, False)
    i, end, k = cues + 4 + n, cues + 4 + n + size, 0
    while i < end:
        eid, a = keyindex._vint(data, i, True)
        sz, b = keyindex._vint(data, i + a, False)
        if eid == keyindex.CUE_POINT:
            change(k, data, i)
            k += 1
        i += a + b + sz
    p.write_bytes(bytes(data))


def video_packets(path: Path) -> list[float]:
    r = subprocess.run([probe.ffprobe_path(), "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "packet=pts_time", "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return sorted(float(x.split(",")[0]) for x in r.stdout.split())


def test_cues_missing_keyframes_still_make_whole_segments(tmp_path):
    """Every other cue turned into padding (an EBML Void of the same size), like the owner's mkvmerge files whose
    Cues leave out keyframes FFmpeg cuts at. The shorter list is used; played as copy-HLS (MPEG-TS, as on the
    Samsung TV), FFmpeg's extra pieces join their segment: each segment holds exactly its stretch of the film."""
    p = make(tmp_path / "sparse.mkv", str(tmp_path / "sparse.mkv"))
    full = stream.keyframes(p)
    edit_cues(p, lambda n, data, at: data.__setitem__(at, 0xEC) if n % 2 else None)  # CuePoint (0xBB) -> Void
    sparse = stream.keyframes(p)
    assert sparse and len(sparse) < len(full) and set(sparse) < set(full)
    t = hls.Transcodes(tmp_path / "transcode", lambda: 0)
    try:
        s = t.create(1, p, None, 20.0, keyframes=sparse, video_codec="H.264", ts=True)
        v = s.variants[0]
        frames = 0
        for k in [3, 0, 1, 2, *range(4, v.segments)]:  # a seek first: runs from mid-file and from 0
            seg = t.segment(s, 0, k)
            pts = video_packets(seg)
            assert abs(len(pts) - round((v.time(k + 1) - max(v.time(k), sparse[0])) * 25)) <= 1, k
            frames += len(pts)
        assert abs(frames - 500) <= 1  # 20 s at 25 fps: nothing lost, nothing twice
    finally:
        t.shutdown()


def test_index_listing_a_non_keyframe_is_not_used(tmp_path, monkeypatch):
    """Cue times moved a frame late: the stretches ffprobe reads show they aren't keyframes FFmpeg cuts at, so the
    complete read is used instead."""
    p = make(tmp_path / "shifted.mkv", str(tmp_path / "shifted.mkv"))

    def later(n, data, at):
        _, a = keyindex._vint(data, at, True)
        _, b = keyindex._vint(data, at + a, False)
        i = at + a + b  # the CuePoint's first child: CueTime
        if data[i] == keyindex.CUE_TIME:
            size, c = keyindex._vint(data, i + 1, False)
            v = int.from_bytes(data[i + 1 + c:i + 1 + c + size], "big") + 40
            data[i + 1 + c:i + 1 + c + size] = v.to_bytes(size, "big")

    edit_cues(p, later)
    shifted = keyindex.read(p)
    assert shifted and not stream._index_agrees(probe.ffprobe_path(), p, shifted, 0)
    assert stream.keyframes(p) == full_read(p, monkeypatch)


def test_index_check_reads_stretches_of_a_long_file(tmp_path, monkeypatch):
    """A file longer than three check stretches is checked at its start, middle and end, not read whole."""
    p = tmp_path / "long.mkv"
    subprocess.run([stream.ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=160x120:rate=25:duration=120", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-g", "100", "-sc_threshold", "0", str(p)], check=True, timeout=120)
    runs = []
    real = subprocess.run

    def run(cmd, **kw):
        runs.append(cmd)
        return real(cmd, **kw)

    monkeypatch.setattr(subprocess, "run", run)
    got = stream.keyframes(p)
    checks = [c for c in runs if "-read_intervals" in c]
    assert len(checks) == 3 and not any("-read_intervals" not in c and "packet=pts_time,flags" in c for c in runs)
    monkeypatch.setattr(subprocess, "run", real)
    assert got == full_read(p, monkeypatch) and len(got) == 30


def test_no_usable_index(tmp_path, monkeypatch):
    """Matroska written to a pipe has no Cues, a fragmented MP4 no sample table, an AVI no index read here:
    each falls back to reading the packets."""
    piped = tmp_path / "piped.mkv"
    with open(piped, "wb") as f:
        cmd = [stream.ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
               "testsrc=size=320x240:rate=25:duration=6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "50",
               "-f", "matroska", "-"]
        subprocess.run(cmd, check=True, stdout=f, timeout=60)
    frag = make(tmp_path / "frag.mp4", "-movflags", "frag_keyframe+empty_moov", str(tmp_path / "frag.mp4"))
    avi = tmp_path / "old.avi"
    subprocess.run([stream.ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=320x240:rate=25:duration=6", "-c:v", "mpeg4", "-g", "50", str(avi)],
                   check=True, timeout=60)
    for p in (piped, frag, avi):
        assert keyindex.read(p) is None, p.name
        assert stream.keyframes(p) == full_read(p, monkeypatch) and stream.keyframes(p), p.name
