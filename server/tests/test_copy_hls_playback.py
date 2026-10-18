"""What the TV apps get, with a real FFmpeg: copy-HLS (video copied, Dolby sound converted) in MPEG-TS for the
Samsung TV and fMP4 for the Fire TV, through a pause past the idle limit, a seek, and FFmpeg cutting at keyframes the
file's index leaves out. Every segment must hold exactly its stretch of picture, the sound must cover the same
stretch, and all of it must sit on one clock: the players time text subtitles by that clock."""

import subprocess
from pathlib import Path

import pytest

from bams import hls, probe, stream
from test_keyindex import edit_cues

pytestmark = pytest.mark.skipif(not stream.ffmpeg_path(), reason="FFmpeg not installed")

FPS = 25


def episode(path: Path) -> Path:
    """40 s, a keyframe every second, B-frames, AC3 5.1 (as most of the owner's files); the Cues then list every
    other keyframe, like the owner's mkvmerge files, so FFmpeg cuts twice as often as the playlist does."""
    keys = ",".join(str(x) for x in range(40))
    subprocess.run([stream.ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", f"testsrc=size=320x240:rate={FPS}:duration=40",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=40",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "1000", "-sc_threshold", "0", "-bf", "3",
                    "-force_key_frames", keys, "-c:a", "ac3", "-ac", "6", str(path)], check=True, timeout=120)
    edit_cues(path, lambda n, data, at: data.__setitem__(at, 0xEC) if n % 2 else None)
    return path


def packets(f: Path) -> tuple[list[float], list[tuple[float, float]]]:
    """Video presentation times, and the sound's (time, length) packets, of a segment file."""
    r = subprocess.run([probe.ffprobe_path(), "-v", "error", "-show_entries",
                        "packet=codec_type,pts_time,duration_time", "-of", "csv=p=0", str(f)],
                       capture_output=True, text=True, check=True)
    video, audio = [], []
    for line in r.stdout.split():
        kind, pts, dur, *_ = line.split(",") + ["", ""]
        if pts in ("", "N/A"):
            continue
        if kind == "video":
            video.append(float(pts))
        elif kind == "audio":
            audio.append((float(pts), float(dur) if dur not in ("", "N/A") else 1024 / 48000))
    return sorted(video), sorted(audio)


@pytest.mark.parametrize("ts", [True, False], ids=["samsung-mpegts", "firetv-fmp4"])
def test_copy_hls_through_a_pause_keeps_picture_sound_and_clock_together(tmp_path, ts):
    src = episode(tmp_path / "episode.mkv")
    kf = stream.keyframes(src)
    assert len(kf) == 20  # from the (sparse) index: FFmpeg sees 40
    t = hls.Transcodes(tmp_path / "transcode", lambda: 0)
    try:
        s = t.create(1, src, None, 40.0, keyframes=kf, video_codec="H.264", ts=ts)
        v = s.variants[0]
        init = None if ts else t.init(s, 0).read_bytes()
        n = [0]

        def fetch(k: int):
            n[0] += 1
            f = tmp_path / f"seg{k}-{n[0]}.{'ts' if ts else 'mp4'}"
            f.write_bytes((init or b"") + t.segment(s, 0, k).read_bytes())
            return packets(f)

        got = [(k, fetch(k)) for k in (0, 1, 2, 3)]  # playing from the start
        s.last_access -= hls.IDLE + 1  # paused past the idle limit: the session sleeps
        t.reap()
        assert s.asleep and not list(v.dir.glob(f"*.{v.ext}")) and not v.running()
        # Play: woken, FFmpeg restarts where the player is. FFmpeg's seek lands a keyframe early, so this run makes
        # segment 3 again (from 6 s): it must have its sound too (it had none before -noaccurate_seek)
        after = [(k, fetch(k)) for k in (4, 5, 3)]
        assert not s.asleep and v.job_start == 3
        after += [(k, fetch(k)) for k in (12, 13)]  # a seek ahead
        assert dict(after)[3][0] == dict(got)[3][0]  # made again by another run: the very same picture
        clock = None
        for k, (video, audio) in got + after:
            start, end = (v.first_key if k == 0 else v.time(k)), v.time(k + 1)  # segment 0: from 0, picture from the first keyframe
            # the picture: exactly this stretch (two of FFmpeg's pieces joined), every frame once
            assert len(video) == round((end - start) * FPS), k
            # one clock for every segment and every run: the player's time is the file's, so subtitles line up
            offset = video[0] - start
            clock = offset if clock is None else clock
            assert abs(offset - clock) < 0.002, (k, offset, clock)
            # the sound covers the same stretch (a few packets out at each end: the picture's packets come
            # B-frames late, so the cut falls among sound packets a little before the keyframe)
            assert audio, k
            heard_from, heard_to = audio[0][0], audio[-1][0] + audio[-1][1]
            assert abs(heard_from - video[0]) <= 0.15, (k, heard_from, video[0])
            assert abs(heard_to - (video[-1] + 1 / FPS)) <= 0.15, (k, heard_to, video[-1])
        # within a run, picture and sound run on from one segment to the next: no gap, nothing twice
        first, second = dict(got), dict(after)
        for made, k in [(first, 0), (first, 1), (first, 2), (second, 3), (second, 4), (second, 12)]:
            assert abs(made[k][0][-1] + 1 / FPS - made[k + 1][0][0]) < 0.002, k
            assert abs(made[k][1][-1][0] + made[k][1][-1][1] - made[k + 1][1][0][0]) < 0.002, k
    finally:
        t.shutdown()
