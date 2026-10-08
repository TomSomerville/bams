"""Subtitles: track lists, sidecar files, WebVTT conversion, and burning picture subtitles in."""

import struct
import subprocess
from pathlib import Path

import pytest

import vobsub
from bams import jobs, readonly, stream, subtitles
from bams.app import create_app
from bams.config import Paths
from conftest import signed_in

needs_ffmpeg = pytest.mark.skipif(not stream.ffmpeg_path(), reason="FFmpeg not installed")

SRT = "1\n00:00:01,000 --> 00:00:02,500\nCafé {i}\n\n2\n00:00:04,000 --> 00:00:05,000\nSecond line\n"


def test_languages():
    assert subtitles.language("eng") == ("en", "English")
    assert subtitles.language("en") == ("en", "English")
    assert subtitles.language("English") == ("en", "English")
    assert subtitles.language("pt-BR")[1] == "Portuguese"
    assert subtitles.language("und") == (None, None) and subtitles.language("forced") == (None, None)


def test_sidecars_and_labels(tmp_path):
    v = tmp_path / "Movie (2001).mkv"
    for n in ("Movie (2001).mkv", "Movie (2001).srt", "Movie (2001).en.forced.srt", "Movie (2001).fre.sdh.ass",
              "Movie (2001).nfo", "Other.srt", "movie (2001).German.vtt"):
        (tmp_path / n).write_text("x")
    probe = {"subtitles": [{"codec": "subrip", "language": "eng", "title": "SDH", "forced": False, "image": False},
                           {"codec": "hdmv_pgs_subtitle", "language": "spa", "title": None, "forced": True,
                            "image": True}]}
    tr = subtitles.tracks(probe, v, 7)
    assert [t["id"] for t in tr] == ["e0", "e1", "x0", "x1", "x2", "x3"]
    e0, e1, *side = tr
    assert e0["label"] == "English · SDH" and e0["url"] == "/api/files/7/subtitles/e0.vtt"
    assert e1["image"] and e1["url"] is None and e1["label"] == "Spanish · forced"
    labels = {t["file"]: (t["label"], t["language"]) for t in side}
    assert labels["Movie (2001).en.forced.srt"] == ("English · forced", "en")
    assert labels["Movie (2001).fre.sdh.ass"] == ("French · SDH", "fr")
    assert labels["movie (2001).German.vtt"] == ("German", "de")  # case-insensitive match
    assert labels["Movie (2001).srt"] == ("Movie (2001).srt", None)


def test_vobsub_sidecars_are_listed(tmp_path):
    """DVD subtitles ripped to Movie.idx + Movie.sub: one picture track per language in the index; an .idx whose
    .sub is missing (or a .sub alone) isn't a track."""
    v = tmp_path / "Movie (2001).mkv"
    v.write_text("x")
    vobsub.write(tmp_path / "Movie (2001).idx", (320, 240), [("en", [(1, 2, vobsub.box(8, 8), 0, 0)]),
                                                              ("fr", [(1, 2, vobsub.box(8, 8), 0, 0)])])
    vobsub.write(tmp_path / "Movie (2001).de.forced.idx", (320, 240), [("", [(1, 2, vobsub.box(8, 8), 0, 0)])])
    (tmp_path / "Movie (2001).es.idx").write_text("id: es, index: 0\n")  # no .sub next to it
    (tmp_path / "Movie (2001).it.sub").write_bytes(b"\0" * 2048)          # no .idx
    readonly.set_protected_roots([tmp_path])
    try:
        tr = subtitles.tracks({}, v, 3)
    finally:
        readonly.set_protected_roots([])
    assert [(t["id"], t["label"], t["language"], t["image"], t["url"]) for t in tr] == [
        ("x0-0", "German · forced", "de", True, None),  # no language in the index: the file name's
        ("x1-0", "English", "en", True, None),
        ("x1-1", "French", "fr", True, None),
    ]
    assert subtitles.burn_source(tr[2], v) == (tmp_path / "Movie (2001).idx", 1)


def test_shift():
    vtt = ("WEBVTT\n\n00:00:01.000 --> 00:00:02.500\nA\n\n00:01:05.000 --> 00:01:06.000 line:90%\nB\n\n"
           "01:00:00.000 --> 01:00:01.000\nC\n")
    out = subtitles.shift(vtt, 60)
    assert "A" not in out.split("WEBVTT")[1]                           # over before the stream starts
    assert "00:00:05.000 --> 00:00:06.000 line:90%\nB" in out           # settings kept
    assert "00:59:00.000 --> 00:59:01.000\nC" in out
    assert subtitles.shift(vtt, 0) == vtt


def pgs(path: Path, w: int, h: int, box: tuple[int, int, int, int], start: float, end: float) -> None:
    """A minimal Blu-ray (PGS) subtitle stream: one white box from `start` to `end`."""
    def seg(kind: int, pts: float, data: bytes) -> bytes:
        return b"PG" + struct.pack(">IIBH", int(pts * 90000), 0, kind, len(data)) + data

    x, y, bw, bh = box
    line = bytes([0x00, 0xC0 | (bw >> 8), bw & 0xFF, 0x01, 0x00, 0x00])  # bw pixels of colour 1, end of line
    rle = line * bh
    show = (seg(0x16, start, struct.pack(">HHBHBBBB", w, h, 0x10, 1, 0x80, 0, 0, 1) + struct.pack(">HBBHH", 0, 0, 0, x, y))
            + seg(0x17, start, struct.pack(">BBHHHH", 1, 0, x, y, bw, bh))
            + seg(0x14, start, bytes([0, 0]) + bytes([1, 235, 128, 128, 255]))
            + seg(0x15, start, struct.pack(">HBB", 0, 0, 0xC0) + (len(rle) + 4).to_bytes(3, "big")
                  + struct.pack(">HH", bw, bh) + rle)
            + seg(0x80, start, b""))
    def clear(t: float, n: int) -> bytes:
        return (seg(0x16, t, struct.pack(">HHBHBBBB", w, h, 0x10, n, 0x80 if n == 0 else 0x00, 0, 0, 0))
                + seg(0x17, t, struct.pack(">BBHHHH", 1, 0, x, y, bw, bh)) + seg(0x80, t, b""))
    # an empty display set at 0 first: muxers count a subtitle stream's times from its first packet
    path.write_bytes(clear(0.0, 0) + show + clear(end, 2))


@pytest.fixture
def film(tmp_path):
    """A 6 s black film with an embedded SRT track and a PGS track, plus a Windows-1252 sidecar."""
    ff = stream.ffmpeg_path()
    d = tmp_path / "media" / "Film (2001)"
    d.mkdir(parents=True)
    (tmp_path / "in.srt").write_text(SRT, encoding="utf-8")
    pgs(tmp_path / "in.sup", 320, 240, (60, 180, 200, 40), 1.0, 5.5)
    src = d / "Film (2001).mkv"
    subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", "color=black:size=320x240:rate=25:duration=6",
                    "-i", str(tmp_path / "in.srt"), "-i", str(tmp_path / "in.sup"),
                    "-map", "0", "-map", "1", "-map", "2", "-c:v", "mpeg4", "-c:s:0", "srt", "-c:s:1", "copy",
                    "-metadata:s:s:0", "language=eng", "-metadata:s:s:1", "language=ger", str(src)], check=True)
    (d / "Film (2001).fr.srt").write_bytes(SRT.replace("Café", "Crème brûlée").encode("cp1252"))
    paths = Paths(tmp_path / "data")
    c = signed_in(create_app(paths, start_scheduler=False))
    lib = c.post("/api/libraries", json={"name": "Movies", "type": "movie", "paths": [str(tmp_path / "media")]}).json()
    jobs.run_scan(paths, lib["id"], do_match=False)
    movie = c.get(f"/api/libraries/{lib['id']}/items").json()[0]
    yield c, c.get(f"/api/items/{movie['id']}").json(), src, tmp_path
    readonly.set_protected_roots([])


@needs_ffmpeg
def test_subtitles_through_the_api(film):
    c, item, src, _ = film
    before = src.read_bytes()
    f = item["files"][0]
    tr = {t["id"]: t for t in f["subtitles"]}
    assert set(tr) == {"e0", "e1", "x0"}
    assert tr["e0"]["label"] == "English" and tr["e1"]["image"] and tr["x0"]["language"] == "fr"
    r = c.get(tr["e0"]["url"])
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/vtt")
    assert r.text.startswith("WEBVTT") and "00:01.000 --> 00:02.500" in r.text and "Café" in r.text
    side = c.get(tr["x0"]["url"]).text
    assert "Crème brûlée" in side  # read as Windows-1252, served as UTF-8
    shifted = c.get(tr["e0"]["url"] + "?shift=3.5").text
    assert "Café" not in shifted and "00:00:00.500 --> 00:00:01.500" in shifted
    assert c.get(f"/api/files/{f['id']}/subtitles/e1.vtt").status_code == 400  # a picture track
    assert c.get(f"/api/files/{f['id']}/subtitles/x9.vtt").status_code == 404
    assert src.read_bytes() == before and sorted(p.name for p in src.parent.iterdir()) == [
        "Film (2001).fr.srt", "Film (2001).mkv"]  # nothing written next to the media


def _luma(ff: str, video: Path, t: float, x: int, y: int) -> int:
    """The brightness of one pixel of the frame `t` seconds in (decoded up to there: a lone segment can't be seeked)."""
    r = subprocess.run([ff, "-v", "error", "-i", str(video), "-ss", str(t), "-frames:v", "1", "-vf", "scale=320:240",
                        "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"], capture_output=True, check=True)
    return r.stdout[y * 320 + x]


@pytest.mark.skipif(not stream.ffmpeg_path() or not stream.video_encoder(), reason="FFmpeg/H.264 encoder not installed")
def test_picture_subtitles_are_burned_in(film):
    c, item, _, tmp = film
    f = item["files"][0]
    ff = stream.ffmpeg_path()
    # the subtitle shows from 1 to 5.5 s. Segment 1 (4-8 s) on its own: FFmpeg starts mid-line and must still show it
    for burn, k, expect_box in ((None, 0, False), (1, 0, True), (1, 1, True)):
        sess = c.post(f["playback"]["hls_url"], json={"burn": burn, "start": k * 4}).json()
        seg = c.get(f"/api/hls/{sess['id']}/0/{k}.ts")
        assert seg.status_code == 200, seg.text
        out = tmp / f"burn-{burn}-{k}.ts"
        out.write_bytes(seg.content)
        at = 2.0 if k == 0 else 1.0  # 2 s and 5 s into the film, both inside the line
        inside, outside = _luma(ff, out, at, 160, 200), _luma(ff, out, at, 160, 100)
        assert outside < 40
        assert (inside > 180) is expect_box, (burn, k, inside)
        c.delete(f"/api/hls/{sess['id']}")
    # the live stream (browsers without HLS), started mid-line at 3 s: the line is on screen from its first frame
    live = tmp / "pgs-live.mp4"
    live.write_bytes(c.get(f"{f['playback']['transcode_url']}?t=3&sub=1").content)
    assert _luma(ff, live, 0.0, 160, 200) > 180 and _luma(ff, live, 2.9, 160, 200) < 40


@pytest.mark.skipif(not stream.ffmpeg_path() or not stream.video_encoder(), reason="FFmpeg/H.264 encoder not installed")
def test_vobsub_sidecar_is_burned_in(film, unguarded):
    """A DVD subtitle pair next to the film, its line on screen from 1 to 5.5 s: burned in from segment 0, from
    segment 1 (FFmpeg starts mid-line), and in the live stream started at 3 s. Nothing is written next to it."""
    c, item, src, tmp = film
    with unguarded:  # the user drops the pair in
        vobsub.write(src.with_suffix(".idx"), (320, 240), [("en", [(1.0, 5.5, vobsub.box(200, 40), 60, 180)])])
    before = sorted(p.name for p in src.parent.iterdir())
    f = c.get(f"/api/items/{item['id']}").json()["files"][0]
    track = next(t for t in f["subtitles"] if t["codec"] == "vobsub")
    assert track["id"] == "x1-0" and track["image"] and track["label"] == "English"
    ff = stream.ffmpeg_path()
    for k, at in ((0, 0.5), (0, 2.0), (1, 1.0), (1, 1.8)):  # 0.5, 2, 5 and 5.8 s into the film
        sess = c.post(f["playback"]["hls_url"], json={"burn": track["id"], "start": k * 4}).json()
        out = tmp / f"vob-{k}.ts"
        seg = c.get(f"/api/hls/{sess['id']}/0/{k}.ts")
        c.delete(f"/api/hls/{sess['id']}")
        assert seg.status_code == 200, (k, seg.text)
        out.write_bytes(seg.content)
        film_t = k * 4 + at
        assert (_luma(ff, out, at, 160, 200) > 180) is (1.0 < film_t < 5.5), film_t
    live = tmp / "vob-live.mp4"
    live.write_bytes(c.get(f"{f['playback']['transcode_url']}?t=3&sub={track['id']}").content)
    assert _luma(ff, live, 1.0, 160, 200) > 180 and _luma(ff, live, 2.9, 160, 200) < 40  # 4 s in: on; 5.9 s: off
    assert c.post(f["playback"]["hls_url"], json={"burn": "x7-0"}).status_code == 422
    assert c.post(f["playback"]["hls_url"], json={"burn": "e0"}).status_code == 422  # a text track: not burned in
    assert sorted(p.name for p in src.parent.iterdir()) == before
