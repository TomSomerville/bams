"""Editions (owner 2026-10-21): another version of a show or film ("MASH (No Laugh Track)", "Director's Cut") is a
title of its own beside the plain one, never merged with it, but matched to the same TMDB title for its information."""

import pytest

from bams import library, matcher, parse
from bams.scanner import scan_library
from bams.tmdb import Tmdb
from conftest import make_tree
from test_matcher import TOKEN, fake_tmdb


@pytest.mark.parametrize("name, edition", [
    ("MASH (No Laugh Track)", "No Laugh Track"),
    ("MASH (no canned laughter)", "No Canned Laughter"),
    ("M.A.S.H.S01.No.Laugh.Track.1080p", "No Laugh Track"),
    ("Show [Laugh Track Removed]", "Laugh Track Removed"),
    ("Aliens (1986) Directors Cut", "Director's Cut"),
    ("Kingdom of Heaven (2005) - Extended", "Extended"),
    ("Blade Runner (1982) [Final Cut]", "Final Cut"),
    ("Aliens (1986) {edition-Special Edition}", "Special Edition"), ("Hubble 3D (2010) IMAX", "IMAX"),
    # part of the name, or not a cut: no edition
    ("Uncut Gems (2019)", None), ("The Final Cut (2004)", None), ("Extended Family (2023)", None),
    ("The Laughing Policeman (1973)", None), ("Aliens.1986.REMASTERED.1080p", None), ("MASH", None),
])
def test_edition_names(name, edition):
    assert parse.edition_of(name) == edition


def test_editions_stay_apart_and_share_tmdb_information(env):
    paths, media, con = env
    make_tree(media, ["The Simpsons/Season 35/The Simpsons - S35E01.mkv",
                      "The Simpsons (No Laugh Track)/Season 35/The Simpsons - S35E01.mkv",
                      "Simpsons/Season 35/Simpsons - S35E02.mkv"])  # another folder name of the plain show
    lib_id = library.create(con, paths.root, "TV", "show", [str(media)])
    scan_library(con, lib_id, do_probe=False)
    t = Tmdb(TOKEN, transport=fake_tmdb([]))
    matcher.match_library(con, t, paths.images, lib_id)
    shows = {s["title"]: s for s in con.execute("SELECT * FROM items WHERE kind='show'")}
    # the plain show's two folders merged; the edition kept apart, with the same TMDB show and episode names
    assert sorted(shows) == ["The Simpsons", "The Simpsons (No Laugh Track)"]
    assert shows["The Simpsons (No Laugh Track)"]["tmdb_id"] == shows["The Simpsons"]["tmdb_id"] == 456
    assert shows["The Simpsons (No Laugh Track)"]["edition"] == "No Laugh Track"
    eps = lambda s: sorted(r["title"] for r in con.execute(
        "SELECT e.title FROM items e JOIN items se ON se.id=e.parent_id WHERE se.parent_id=?", (s["id"],)))
    assert eps(shows["The Simpsons"]) == ["Real Title 35x1", "Real Title 35x2"]
    assert eps(shows["The Simpsons (No Laugh Track)"]) == ["Real Title 35x1"]


def test_an_edition_merged_before_is_split_by_the_next_scan(env, monkeypatch):
    paths, media, con = env
    make_tree(media, ["The Simpsons/Season 35/The Simpsons - S35E01.mkv",
                      "The Simpsons (No Laugh Track)/Season 35/The Simpsons - S35E01.mkv"])
    lib_id = library.create(con, paths.root, "TV", "show", [str(media)])
    with monkeypatch.context() as m:  # an older BAMS: no editions, both folders one show
        m.setattr(parse, "edition_of", lambda name: None)
        scan_library(con, lib_id, do_probe=False)
    con.execute("UPDATE files SET parse=json_set(parse, '$.v', 9)")  # parsed by the older parser
    con.commit()
    assert con.execute("SELECT COUNT(*) FROM items WHERE kind='show'").fetchone()[0] == 1
    scan_library(con, lib_id, do_probe=False)
    matcher.match_library(con, Tmdb(TOKEN, transport=fake_tmdb([])), paths.images, lib_id)
    shows = sorted(r["title"] for r in con.execute("SELECT title FROM items WHERE kind='show'"))
    assert shows == ["The Simpsons", "The Simpsons (No Laugh Track)"]
    # each episode has its own file again
    assert con.execute("""SELECT COUNT(*) FROM items e WHERE kind='episode'
                          AND (SELECT COUNT(*) FROM file_items WHERE item_id=e.id) <> 1""").fetchone()[0] == 0


def test_movie_editions(env):
    paths, media, con = env
    make_tree(media, ["Aliens (1986)/Aliens (1986).mkv", "Aliens (1986) Directors Cut/Aliens.1986.Directors.Cut.mkv"])
    lib_id = library.create(con, paths.root, "Films", "movie", [str(media)])
    scan_library(con, lib_id, do_probe=False)
    rows = sorted((r["title"], r["parsed_title"], r["edition"]) for r in con.execute("SELECT * FROM items WHERE kind='movie'"))
    assert rows == [("Aliens", "Aliens", None), ("Aliens (Director's Cut)", "Aliens", "Director's Cut")]
