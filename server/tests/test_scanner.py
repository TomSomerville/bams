import shutil

from bams import library
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
