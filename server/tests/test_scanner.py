import shutil

from bams import library
from bams.db import set_setting
from bams.scanner import scan_library
from conftest import make_tree

FILES = [
    "Family Guy S15 1080p DSNP WEB-DL AAC2 0 H 264-OldT/Family.Guy.S15E01.The.the.Band.1080p.DSNP.WEB-DL.AAC2.0.H.264-OldT.mkv",
    "Family Guy S15 1080p DSNP WEB-DL AAC2 0 H 264-OldT/Family.Guy.S15E02.Bookie.of.the.Year.1080p.DSNP.WEB-DL.AAC2.0.H.264-OldT.mkv",
    "The Simpsons 1989 S35 1080p DSNP WEBRip DDP 5 1 x265-edge2020/The.Simpsons.S35E01.Homers.Crossing.1080p.DSNP.WEBRip.DDP.5.1.x265-edge2020.mkv",
    "The Simpsons 1989 S35 1080p DSNP WEBRip DDP 5 1 x265-edge2020/Sample/the.simpsons.s35e01.sample.mkv",
    "The.Simpsons.S36.1080p/The.Simpsons.S36E01.Bart.mkv",  # same show, folder without the year
    "Some Show/Some Show - Season 00 - 'S00E01-Episode name'.mkv",
    "Some Show/Some Show - S01E02E03.mkv",
    "Junk/holiday video.mkv",
]


def tree(con, lib_id, kind="show"):
    out = {}
    for show in con.execute("SELECT * FROM items WHERE library_id=? AND kind=?", (lib_id, kind)):
        seasons = {}
        for s in con.execute("SELECT * FROM items WHERE parent_id=? ORDER BY season_number", (show["id"],)):
            seasons[s["season_number"]] = [e["episode_number"] for e in con.execute(
                "SELECT * FROM items WHERE parent_id=? ORDER BY episode_number", (s["id"],))]
        out[(show["title"], show["year"])] = seasons
    return out


def setup(env, files=FILES):
    paths, media, con = env
    make_tree(media, files)
    lib_id = library.create(con, paths.root, "TV", "show", [str(media)])
    return paths, media, con, lib_id


def test_groups_shows_seasons_episodes(env):
    paths, media, con, lib_id = setup(env)
    set_setting(con, "autofill", "0")  # the naming rules alone (auto fill would make 'Junk' a show)
    st = scan_library(con, lib_id, do_probe=False)
    assert st.added == 7 and st.unrecognized == 1  # the Sample folder is skipped; 'holiday video' unrecognised
    assert tree(con, lib_id) == {
        ("Family Guy", None): {15: [1, 2]},
        ("The Simpsons", 1989): {35: [1], 36: [1]},  # yearless S36 folder joins the 1989 show
        ("Some Show", None): {0: [1], 1: [2, 3]},
    }
    ep = con.execute("SELECT title FROM items WHERE kind='episode' AND season_number=0").fetchone()
    assert ep["title"] == "Episode name"


def test_rescan_is_idempotent(env):
    paths, media, con, lib_id = setup(env)
    scan_library(con, lib_id, do_probe=False)
    before = con.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    st = scan_library(con, lib_id, do_probe=False)
    assert (st.added, st.changed, st.missing, st.moved) == (0, 0, 0, 0)
    assert con.execute("SELECT COUNT(*) FROM items").fetchone()[0] == before


def test_moved_file_keeps_its_row(env, unguarded):
    paths, media, con, lib_id = setup(env)
    scan_library(con, lib_id, do_probe=False)
    old = "Some Show/Some Show - S01E02E03.mkv"
    fid = con.execute("SELECT id FROM files WHERE rel_path=?", (old,)).fetchone()[0]
    with unguarded:  # the user reorganises their folders
        (media / "Some Show" / "Season 1").mkdir()
        shutil.move(media / old, media / "Some Show" / "Season 1" / "Some Show - S01E02E03.mkv")
    st = scan_library(con, lib_id, do_probe=False)
    assert (st.moved, st.added, st.missing) == (1, 0, 0)
    assert con.execute("SELECT rel_path FROM files WHERE id=?", (fid,)).fetchone()[0] == "Some Show/Season 1/Some Show - S01E02E03.mkv"


def test_deleted_file_flagged_not_dropped(env, unguarded):
    paths, media, con, lib_id = setup(env)
    scan_library(con, lib_id, do_probe=False)
    with unguarded:
        (media / FILES[0]).unlink()
    st = scan_library(con, lib_id, do_probe=False)
    assert st.missing == 1
    row = con.execute("SELECT available, missing_since FROM files WHERE rel_path=?", (FILES[0],)).fetchone()
    assert row["available"] == 0 and row["missing_since"]


def test_offline_root_marks_nothing_missing(env, unguarded, tmp_path):
    paths, media, con, lib_id = setup(env)
    scan_library(con, lib_id, do_probe=False)
    with unguarded:  # "unmount the drive"
        media.rename(tmp_path / "unplugged")
    st = scan_library(con, lib_id, do_probe=False)
    assert st.roots_offline == [str(media)]
    assert st.missing == 0
    assert con.execute("SELECT COUNT(*) FROM files WHERE available=0").fetchone()[0] == 0


def test_movie_library(env):
    paths, media, con = env
    make_tree(media, ["The Matrix (1999)/The Matrix (1999).mkv",
                      "The Matrix (1999)/The Matrix (1999) - 2160p.mkv",  # second version, same movie
                      "Heat (1995)/movie.mkv",
                      "Alien.1979.1080p.BluRay.x264.mkv"])
    lib_id = library.create(con, paths.root, "Movies", "movie", [str(media)])
    scan_library(con, lib_id, do_probe=False)
    movies = {(r["title"], r["year"]): r["n"] for r in con.execute(
        """SELECT i.title, i.year, COUNT(fi.file_id) n FROM items i JOIN file_items fi ON fi.item_id=i.id
           WHERE i.kind='movie' GROUP BY i.id""")}
    assert movies == {("The Matrix", 1999): 2, ("Heat", 1995): 1, ("Alien", 1979): 1}


def test_scan_does_not_hold_the_write_lock_while_reading_disks(env, monkeypatch, unguarded):
    """A first scan on a slow share used to keep the DB locked for the whole walk: logins and adding a
    library failed with HTTP 500 ("database is locked"). Other writers must get in while it reads disks."""
    import sqlite3

    from bams import readonly as ro
    from bams import scanner

    paths, media, con, lib_id = setup(env)
    scan_library(con, lib_id, do_probe=False)  # known files exist too: the walk updates them
    with unguarded:
        make_tree(media, ["New Show/New Show - S01E01.mkv", "New Show/New Show - S01E02.mkv"])
    other = sqlite3.connect(paths.db, timeout=0, isolation_level=None)
    writes = []

    def can_write():
        other.execute("INSERT INTO settings(key, value) VALUES ('probe', 'x') "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value")
        writes.append(1)

    real_walk, real_hash = ro.walk, ro.quick_hash

    def walk(*a, **kw):
        for e in real_walk(*a, **kw):
            can_write()  # raises "database is locked" if the scan holds the lock
            yield e

    def quick_hash(*a, **kw):
        can_write()
        return real_hash(*a, **kw)

    monkeypatch.setattr(scanner.readonly, "walk", walk)
    monkeypatch.setattr(scanner.readonly, "quick_hash", quick_hash)
    st = scan_library(con, lib_id, do_probe=False)
    other.close()
    assert st.added == 2 and len(writes) == st.files_seen + 2


def test_unnumbered_extras_in_season_folders_are_shown(env):
    """Tester report: a show's Season 00 folder of unnumbered extras was "unrecognized" and never shown."""
    paths, media, con, lib_id = setup(env, [
        "Show (2010)/Season 01/Show - S01E01.mkv",
        "Show (2010)/Season 00/Show - S00E01 - Pilot.mkv",
        "Show (2010)/Season 00/Behind the Scenes.mkv",
        "Show (2010)/Season 00/Show - Bloopers.mkv",
        "Show (2010)/Show - Bonus.mkv",  # not in a season folder: the rules can't place it, auto fill guesses
    ])
    st = scan_library(con, lib_id, do_probe=False)
    assert st.unrecognized == 0
    eps = [(e["season_number"], e["episode_number"], e["title"]) for e in con.execute(
        "SELECT * FROM items WHERE kind='episode' ORDER BY season_number, episode_number IS NULL, episode_number, title")]
    assert eps == [(0, 1, "Pilot"), (0, None, "Behind the Scenes"), (0, None, "Bloopers"), (1, 1, "Episode 1"),
                   (1, None, "Bonus")]
    assert con.execute("SELECT COUNT(*) FROM files WHERE json_extract(parse, '$.guessed')").fetchone()[0] == 1
    n = con.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    con.execute("UPDATE files SET parse=json_set(parse, '$.v', 0)")  # re-parse everything: no duplicates
    assert scan_library(con, lib_id, do_probe=False).reparsed == 5
    assert con.execute("SELECT COUNT(*) FROM items").fetchone()[0] == n


def test_nested_pack_splits_into_its_shows_on_reparse(env):
    """Tester's library: a "megapack" folder holding several series, each with S01-style season folders and
    DVD extras below them. Parser v5 made one fake show out of the pack; v6 splits it and keeps the extras."""
    paths, media, con, lib_id = setup(env, [
        "Star.Trek.Megapack.TheZerg/Star.Trek.DS9/S03/Star.Trek.DS9.S03E14.Heart.Of.Stone.DVDRip.XviD-VF/Star.Trek.DS9.S03E14.DVDRip.XviD-VF.avi",
        "Star.Trek.Megapack.TheZerg/Star.Trek.DS9/S03/Star.Trek.DS9.S03.Extras.DVDRip.XviD-VF/Star.Trek.DS9.S03.Extra10.DVDRip.XviD-Vf.avi",
        "Star.Trek.Megapack.TheZerg/Star.Trek.TNG/S03/Star.Trek-TNG.S03E14.iNTERNAL.DVDRip.XviD-DVDiSO/st-tng.s03e14.dvdrip.xvid-dvdiso.avi",
        "Star.Trek.Megapack.TheZerg/Star.Trek.Voyager/S01/Star.Trek.Voyager.S01E01.DVDRip.XviD-VF/star.trek.voyager.s01e01.avi",
    ])
    st = scan_library(con, lib_id, do_probe=False)
    assert st.unrecognized == 0
    shows = sorted(r["title"] for r in con.execute("SELECT title FROM items WHERE kind='show'"))
    assert shows == ["Star Trek Deep Space Nine", "Star Trek The Next Generation", "Star Trek Voyager"]
    eps = [(e["title"], e["season_number"], e["episode_number"]) for e in con.execute(
        "SELECT s.title, e.season_number, e.episode_number FROM items e JOIN items se ON se.id=e.parent_id "
        "JOIN items s ON s.id=se.parent_id WHERE e.kind='episode'")]
    assert ("Star Trek Deep Space Nine", 3, None) in eps  # the extra, under DS9 season 3
    assert ("Star Trek Deep Space Nine", 3, 14) in eps and ("Star Trek The Next Generation", 3, 14) in eps
    # a library indexed by the old parser: everything re-parses, the pack show goes away, nothing is left behind
    con.execute("UPDATE files SET parse=json_set(parse, '$.v', 5)")
    con.execute("UPDATE items SET title='Star Trek Megapack TheZerg', parsed_title=title, title_key='startrekmegapackthezerg' "
                "WHERE kind='show' AND title='Star Trek Voyager'")
    con.execute("UPDATE item_keys SET title_key='startrekmegapackthezerg' WHERE title_key='startrekvoyager'")
    st = scan_library(con, lib_id, do_probe=False)
    assert st.reparsed == 4
    assert sorted(r["title"] for r in con.execute("SELECT title FROM items WHERE kind='show'")) == shows
    assert con.execute("SELECT COUNT(*) FROM files f LEFT JOIN file_items fi ON fi.file_id=f.id WHERE fi.file_id IS NULL").fetchone()[0] == 0


def test_merging_shows_joins_their_unnumbered_extras(env):
    from bams import items
    paths, media, con, lib_id = setup(env, [
        "Show (2010)/Season 00/Making Of.mkv", "Show (2010)/Season 00/Bloopers.mkv",
        "Show Alt Name/Season 00/Making Of.mkv", "Show Alt Name/Season 00/Interview.mkv",
    ])
    scan_library(con, lib_id, do_probe=False)
    keep, drop = (r["id"] for r in con.execute("SELECT id FROM items WHERE kind='show' ORDER BY title"))
    items.merge_titles(con, keep, drop)
    titles = sorted(r["title"] for r in con.execute("SELECT title FROM items WHERE kind='episode'"))
    assert titles == ["Bloopers", "Interview", "Making Of"]  # the two "Making Of" files are one item
    assert con.execute("SELECT COUNT(*) FROM file_items").fetchone()[0] == 4


def test_scan_reports_progress_with_totals(env):
    """Settings shows "N of M files, X of Y GB, time left": each step reports done/total (and bytes where known)."""
    from bams.jobs import Scheduler

    paths, media, con, lib_id = setup(env)
    calls = []
    scan_library(con, lib_id, do_probe=False, progress=lambda *a, **k: calls.append(a))
    adding = [c for c in calls if c[0] == "Adding new files"]
    assert adding[0][1:3] == (0, 7) and adding[-1][1:3] == (6, 7)   # 7 new files (Sample skipped)
    assert adding[-1][4] == sum(f.stat().st_size for f in media.rglob("*.mkv") if "Sample" not in f.parts)
    assert calls[0][0] == "Looking for files"

    s = Scheduler(paths)
    s._running = {"library_id": lib_id, "step": "Starting", "step_started_at": 0}
    s._progress("Reading file details", 3, 10, 300, 1000)
    r = s.status()["running"]
    assert (r["step"], r["done"], r["total"], r["bytes_done"], r["bytes_total"]) == ("Reading file details", 3, 10, 300, 1000)
    assert r["step_started_at"] > 0  # a new step restarts the clock for "time left"
