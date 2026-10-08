import pytest

from bams.parse import parse, title_key

# (relative path, expected subset of fields)
EPISODES = [
    # the test library: scene season packs
    ("Family Guy S15 1080p DSNP WEB-DL AAC2 0 H 264-OldT/Family.Guy.S15E05.Chris.Has.Got.a.Date.Date.Date.Date.Date.1080p.DSNP.WEB-DL.AAC2.0.H.264-OldT.mkv",
     dict(title="Family Guy", year=None, season=15, episodes=[5], episode_title="Chris Has Got a Date Date Date Date Date")),
    ("The Simpsons 1989 S35 1080p DSNP WEBRip DDP 5 1 x265-edge2020/The.Simpsons.S35E03.McMansion..Wife.1080p.DSNP.WEBRip.DDP.5.1.x265-edge2020.mkv",
     dict(title="The Simpsons", year=1989, season=35, episodes=[3])),
    # Plex layout
    ("Breaking Bad (2008)/Season 01/Breaking Bad - S01E01 - Pilot.mkv",
     dict(title="Breaking Bad", year=2008, season=1, episodes=[1], episode_title="Pilot")),
    ("Breaking Bad (2008)/Season 00/Breaking Bad - S00E01 - Special.mkv", dict(title="Breaking Bad", season=0, episodes=[1])),
    ("Breaking Bad (2008)/Specials/Breaking Bad - S00E02.mkv", dict(title="Breaking Bad", season=0, episodes=[2])),
    # the friend's flat style, with and without quotes
    ("Some Show/Some Show - Season 00 - S00E01-Episode name.mkv",
     dict(title="Some Show", season=0, episodes=[1], episode_title="Episode name")),
    ("Some Show/Some Show - Season 00 - 'S00E01-Episode name'.mkv",
     dict(title="Some Show", season=0, episodes=[1], episode_title="Episode name")),
    # multi-episode, ranges, NxNN
    ("Some Show/Season 2/Some.Show.S02E03E04.720p.mkv", dict(title="Some Show", season=2, episodes=[3, 4])),
    ("Some Show/Some Show - S01E01-E03.mkv", dict(season=1, episodes=[1, 2, 3])),
    ("Firefly/Firefly 1x02 The Train Job.avi", dict(title="Firefly", season=1, episodes=[2])),
    # season only from the folder
    ("Doctor Who (2005)/Season 3/Doctor Who - 07.mkv", dict(title="Doctor Who", year=2005, season=3, episodes=[7])),
    # no folder at all
    ("Doctor.Who.2005.S01E01.Rose.mkv", dict(title="Doctor Who", year=2005, season=1, episodes=[1])),
    # explicit id tag
    ("The Office (US) {tvdb-73244}/Season 1/The Office - S01E01.mkv", dict(season=1, episodes=[1], ids={"tvdb": "73244"})),
    # no episode title, only release tags after SxxEyy: title must stay empty, not "1080p Amazon ..."
    ("Bobs Burgers S01-S08 1080p WEB-DL DD5.1 H.264-Mixed/Bob's Burgers S05 1080p Amazon WEB-DL DD+ 5.1 x264-TrollHD/Bob's Burgers S05E01 1080p Amazon WEB-DL DD+ 5.1 x264-TrollHD.mkv",
     dict(title="Bobs Burgers", season=5, episodes=[1], episode_title=None)),
    ("Bobs Burgers (2011) S14 (1080p HULU WEB-DL H265 SDR DDP 5.1 English - HONE)/Bobs Burgers (2011) S14E01 (1080p HULU WEB-DL H265 SDR DDP 5.1 English - HONE).mkv",
     dict(title="Bobs Burgers", year=2011, season=14, episodes=[1], episode_title=None)),
    ("Bobs Burgers (2011)/Season 14/Bobs Burgers (2011) - S14E01 - Amelia (1080p HULU WEB-DL H265 - HONE).mkv",
     dict(title="Bobs Burgers", season=14, episodes=[1], episode_title="Amelia")),
    # apostrophes inside titles survive
    ("Bob's Burgers/Season 1/Bob's Burgers - S01E01 - Human Flesh.mkv", dict(title="Bob's Burgers", season=1, episodes=[1])),
]

MOVIES = [
    ("The Matrix (1999)/The Matrix (1999).mkv", dict(title="The Matrix", year=1999)),
    ("The Matrix (1999) {imdb-tt0133093}/The Matrix (1999) - 2160p.mkv", dict(title="The Matrix", year=1999, ids={"imdb": "tt0133093"})),
    ("The.Matrix.1999.2160p.UHD.BluRay.x265-GRP.mkv", dict(title="The Matrix", year=1999)),
    ("Heat (1995)/movie.mkv", dict(title="Heat", year=1995)),
    ("Alien (1979) [tmdbid=348]/Alien.mkv", dict(title="Alien", year=1979, ids={"tmdb": "348"})),
    ("Kill Bill Vol 1 (2003)/Kill Bill Vol 1 (2003) - cd1.avi", dict(year=2003, part=1)),
]


@pytest.mark.parametrize("rel,want", EPISODES, ids=[r for r, _ in EPISODES])
def test_episode(rel, want):
    got = parse(rel, "show").to_dict()
    assert got["recognized"]
    for k, v in want.items():
        assert got[k] == v, f"{k}: {got[k]!r} != {v!r}"


@pytest.mark.parametrize("rel,want", MOVIES, ids=[r for r, _ in MOVIES])
def test_movie(rel, want):
    got = parse(rel, "movie").to_dict()
    assert got["recognized"]
    for k, v in want.items():
        assert got[k] == v, f"{k}: {got[k]!r} != {v!r}"


def test_release_info_from_name():
    p = parse("Family Guy S15 1080p DSNP WEB-DL AAC2 0 H 264-OldT/Family.Guy.S15E01.The.the.Band.1080p.DSNP.WEB-DL.AAC2.0.H.264-OldT.mkv", "show")
    assert p.release["resolution"] == "1080p"
    assert p.release["video_codec"] == "H.264"


def test_unrecognized_episode():
    assert not parse("Random Stuff/holiday video.mkv", "show").recognized


def test_title_key_groups_variants():
    assert title_key("The Office (US)") == title_key("the office us")
    assert title_key("Law & Order") == title_key("Law and Order")
    assert title_key("Pokémon") == title_key("Pokemon")
