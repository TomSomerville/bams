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
     dict(title="Bob's Burgers", season=5, episodes=[1], episode_title=None)),
    ("Bobs Burgers (2011) S14 (1080p HULU WEB-DL H265 SDR DDP 5.1 English - HONE)/Bobs Burgers (2011) S14E01 (1080p HULU WEB-DL H265 SDR DDP 5.1 English - HONE).mkv",
     dict(title="Bobs Burgers", year=2011, season=14, episodes=[1], episode_title=None)),
    ("Bobs Burgers (2011)/Season 14/Bobs Burgers (2011) - S14E01 - Amelia (1080p HULU WEB-DL H265 - HONE).mkv",
     dict(title="Bobs Burgers", season=14, episodes=[1], episode_title="Amelia")),
    # apostrophes inside titles survive
    ("Bob's Burgers/Season 1/Bob's Burgers - S01E01 - Human Flesh.mkv", dict(title="Bob's Burgers", season=1, episodes=[1])),
    # no episode number, but in a season folder of a show: shown under that season (tester report: Season 00 extras)
    ("Show (2010)/Season 00/Behind the Scenes.mkv",
     dict(title="Show", season=0, episodes=[], unnumbered=True, episode_title="Behind the Scenes")),
    ("Show (2010)/Specials/Show - Making Of.mkv", dict(title="Show", season=0, unnumbered=True, episode_title="Making Of")),
    ("Show (2010)/Season 02/Show.Recap.1080p.WEB-DL.mkv", dict(title="Show", season=2, unnumbered=True, episode_title="Recap")),
    # " - " in a show name: two different shows, not "Star Trek" twice (tester report)
    ("Star Trek - Lower Decks (2020)/Season 01/Star Trek - Lower Decks - S01E01 - Second Contact.mkv",
     dict(title="Star Trek - Lower Decks", year=2020, season=1, episodes=[1], episode_title="Second Contact")),
    ("Star Trek - Prodigy/Season 1/Star Trek - Prodigy S01E02.mkv", dict(title="Star Trek - Prodigy", season=1, episodes=[2])),
    ("Star Trek - Lower Decks S01E01 1080p WEB-DL.mkv", dict(title="Star Trek - Lower Decks", season=1, episodes=[1])),
    # nested pack (tester's library): the show is the folder above the season folder, not the pack; scene
    # abbreviations become TMDB's names; DVD extras in a season folder are unnumbered episodes of that season
    ("Star.Trek.Megapack.TheZerg/Star.Trek.DS9/S03/Star.Trek.DS9.S03E14.Heart.Of.Stone.REPACK.DVDRip.XviD-VF/Star.Trek.DS9.S03E14.DVDRip.XviD-VF.avi",
     dict(title="Star Trek Deep Space Nine", season=3, episodes=[14])),
    ("Star.Trek.Megapack.TheZerg/Star.Trek.TNG/S01/Star.Trek-TNG.S01E09.iNTERNAL.DVDRip.XviD-DVDiSO/st-tng.s01e09.dvdrip.xvid-dvdiso.avi",
     dict(title="Star Trek The Next Generation", season=1, episodes=[9])),
    ("Star.Trek.Megapack.TheZerg/Star.Trek.TOS/S01/Star.Trek.TOS.S01E01.DVDRip.XviD-OSiRiS/star.trek.tos.s01e01.avi",
     dict(title="Star Trek", season=1, episodes=[1])),
    ("Star.Trek.Megapack.TheZerg/Star.Trek.DS9/S03/Star.Trek.DS9.S03.Extras.DVDRip.XviD-VF/Star.Trek.DS9.S03.Extra10.DVDRip.XviD-Vf.avi",
     dict(title="Star Trek Deep Space Nine", season=3, episodes=[], unnumbered=True, episode_title="Extra10")),
    ("Star.Trek.Megapack.TheZerg/Star.Trek.DS9/S01/Star.Trek.DS9.S01.Extras.DVDRip.XviD-VF/ds9-s1.xtra1.avi",
     dict(title="Star Trek Deep Space Nine", season=1, unnumbered=True, episode_title="xtra1")),
    ("Star.Trek.Megapack.TheZerg/Star.Trek.TNG/S05/Star.Trek.TNG.Extras.S5.DVDRip.DivX-LOL/tng.s5.extras.dept.briefing.visual.effects.divx-lol.avi",
     dict(title="Star Trek The Next Generation", season=5, unnumbered=True)),
    # pack folders that aren't the show's name: the deepest season-pack folder names it
    ("The Simpsons FIXED -jlw/The Simpsons S28/The Simpsons - 28x01 - Monty Burns' Fleeing Circus.mkv",
     dict(title="The Simpsons", season=28, episodes=[1])),
    ("The Great British Sewing Bee Series 1 - 10 - DD/The Great British Sewing Bee - Series 5 (2019) [720p mp4 subs]/Great British Sewing Bee, The.S05E03.70s Week.HDTV-720p.x264 AAC.mp4",
     dict(title="The Great British Sewing Bee", year=None, season=5, episodes=[3])),  # 2019 is the series' year, not the show's
    ("Star.Trek.The.Animated.Series.S01-S02.720p.BluRay.x264-PRESENT [NO RAR]/Star.Trek.The.Animated.Series.S02.720p.BluRay.x264-PRESENT/Star.Trek.The.Animated.Series.S02E06.720p.BluRay.x264-PRESENT.mkv",
     dict(title="Star Trek The Animated Series", season=2, episodes=[6])),
    # an extras folder inside a season folder: still that show, that season
    ("Daria Complete Series/Season 3/Season 3 Extras/Extra - Look Back in Annoyance.avi",
     dict(title="Daria", season=3, episodes=[], unnumbered=True)),
    # ...unless the inner one is a one-word short form that the outer pack spells out
    ("Parks and Recreation S01-07 web hevc-d3g/Parks S07/Parks.and.Recreation.S07E01.2017.1080p.AMZN.WEBRip.DD5.1.x264-NTb.mkv",
     dict(title="Parks and Recreation", season=7, episodes=[1])),
]

MOVIES = [
    ("The Matrix (1999)/The Matrix (1999).mkv", dict(title="The Matrix", year=1999)),
    ("The Matrix (1999) {imdb-tt0133093}/The Matrix (1999) - 2160p.mkv", dict(title="The Matrix", year=1999, ids={"imdb": "tt0133093"})),
    ("The.Matrix.1999.2160p.UHD.BluRay.x265-GRP.mkv", dict(title="The Matrix", year=1999)),
    ("Heat (1995)/movie.mkv", dict(title="Heat", year=1995)),
    ("Alien (1979) [tmdbid=348]/Alien.mkv", dict(title="Alien", year=1979, ids={"tmdb": "348"})),
    ("Kill Bill Vol 1 (2003)/Kill Bill Vol 1 (2003) - cd1.avi", dict(year=2003, part=1)),
    # " - " in a title is part of the name, not a subtitle to drop
    ("Spider-Man - Into the Spider-Verse (2018)/Spider-Man - Into the Spider-Verse (2018).mkv",
     dict(title="Spider-Man - Into the Spider-Verse", year=2018)),
    ("Mission Impossible - Fallout (2018) 1080p BluRay x264-GRP.mkv", dict(title="Mission Impossible - Fallout", year=2018)),
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


def test_season_pack_file_without_episode_stays_unrecognized():
    # a release group's mistake: the pack's own name on one file, no episode number (not in a season folder)
    rel = "The Simpsons-1989-S36 REPACK 1080p WEBRip x265-iVy/The Simpsons-1989-S36 REPACK 1080p WEBRip x265-iVy.mkv"
    p = parse(rel, "show")
    assert (p.title, p.season, p.episodes, p.recognized) == ("The Simpsons", 36, [], False)


def test_unnumbered_needs_a_season_folder():
    # loose in a show folder (often a movie in the TV library) or at the root: still unrecognised
    assert not parse("Show (2010)/Show - Bonus Episode.mkv", "show").recognized
    assert not parse("Loose video.mkv", "show").recognized
