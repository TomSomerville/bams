"""Turn a file's path (relative to its library root) into "what is this?".

No network, no disk access: pure string work, so it's fast and unit-testable.
guessit does the heavy lifting on messy release names. Our own rules handle folder layouts,
explicit id tags, and SxxEyy patterns that guessit misses (e.g. quoted names).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath

from guessit import guessit

# Bump when parsing rules change: the next scan re-parses files parsed by an older version.
PARSER_VERSION = 6

# {tmdb-603} [tmdbid=603] {imdb-tt0133093} [imdbid-tt0133093] {tvdb-81189}
_ID_RE = re.compile(r"[\[{](tmdb|imdb|tvdb)(?:id)?[-=]((?:tt)?\d+)[\]}]", re.I)
_IMDB_BARE_RE = re.compile(r"\b(tt\d{7,9})\b")
# S01E02, S01E02E03, S01E02-E03, s1e2, S01.E02; also 1x02 / 1x02x03
_SXE_RE = re.compile(r"(?<![a-z0-9])s(\d{1,4})[ ._-]?e(\d{1,4})((?:[ ._-]?-?e\d{1,4})*)(?![0-9])", re.I)
_NXN_RE = re.compile(r"(?<![a-z0-9])(\d{1,2})x(\d{2,3})((?:x\d{2,3})*)(?![0-9])", re.I)
_SEASON_DIR_RE = re.compile(r"^(?:season|series|staffel|saison|temporada|seizoen)[ ._-]*(\d{1,4})\b|^s(\d{1,4})$", re.I)
_SPECIALS_RE = re.compile(r"^(specials?|extras? season)$", re.I)
# quote marks wrapping a chunk ('S00E01-Episode name'), not apostrophes inside words (Bob's)
_WRAPPING_QUOTES_RE = re.compile(r"(?:(?<=^)|(?<=[\s\-_.(\[]))['\"‘’“”]|['\"‘’“”](?=$|[\s\-_.)\]])")
# "(1080p HULU WEB-DL H265 SDR DDP 5.1 English - HONE)": a bracketed group of release tags.
_RELEASE_GROUP_RE = re.compile(
    r"[(\[](?=[^)\]]*\b(?:\d{3,4}p|2160p|4k|web-?dl|webrip|bluray|blu-ray|bdrip|hdtv|dvdrip|remux|[xh]\.?26[45]|hevc|avc)\b)"
    r"[^)\]]*[)\]]", re.I)
_GENERIC_STEMS = {"movie", "film", "video", "feature", "main", "title", "video_ts", "bdmv", "index"}
# Scene packs abbreviate the Star Trek series ("Star.Trek.DS9"); TMDB knows the full names (TOS is just "Star Trek").
_STAR_TREK_RE = re.compile(r"^(star[ .]?trek)[ .:_-]+(ds9|tng|tos|voy|ent)$", re.I)
_STAR_TREK = {"ds9": "Deep Space Nine", "tng": "The Next Generation", "tos": "", "voy": "Voyager", "ent": "Enterprise"}


@dataclass
class Parsed:
    kind: str                          # 'episode' | 'movie'
    title: str | None = None           # show title (episodes) or movie title
    year: int | None = None
    season: int | None = None
    episodes: list[int] = field(default_factory=list)
    episode_title: str | None = None
    unnumbered: bool = False           # in a season folder but no episode number ("Season 00/Making Of.mkv")
    part: int | None = None            # multi-part movies (cd1 / part2)
    edition: str | None = None
    ids: dict[str, str] = field(default_factory=dict)   # tmdb / imdb / tvdb hints from the path
    release: dict[str, str] = field(default_factory=dict)  # resolution, codecs etc. from the name

    @property
    def recognized(self) -> bool:
        if not self.title:
            return False
        return self.kind == "movie" or (self.season is not None and (bool(self.episodes) or self.unnumbered))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["recognized"] = self.recognized
        d["v"] = PARSER_VERSION
        return d


def title_key(title: str | None) -> str:
    """Normalised title for grouping files of one show/movie: case, accents, punctuation ignored."""
    if not title:
        return ""
    t = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    t = t.casefold().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "", t)


def _unquote(s: str) -> str:
    return re.sub(r"\s{2,}", " ", _WRAPPING_QUOTES_RE.sub(" ", s)).strip()


def _str(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v)


def _title(g: dict) -> str | None:
    """guessit splits "Star Trek - Lower Decks" into title "Star Trek" + alternative_title "Lower Decks":
    for us the part after the dash is part of the name (two shows, not one)."""
    title = _str(g.get("title"))
    alt = g.get("alternative_title")
    # "Show - Series 5" (British packs): the part after the dash is a season marker, not part of the name
    alts = [str(a) for a in (alt if isinstance(alt, list) else [alt]) if a and not _SEASON_DIR_RE.match(str(a))]
    title = " - ".join([title, *alts]) if title and alts else title
    if title and (m := _STAR_TREK_RE.match(title)):
        title = f"{m.group(1)} {_STAR_TREK[m.group(2).lower()]}".strip()
    return title


def _int(v) -> int | None:
    if isinstance(v, list):
        v = v[0] if v else None
    return v if isinstance(v, int) else None


def _ids(rel: str) -> dict[str, str]:
    ids = {k.lower(): v for k, v in _ID_RE.findall(rel)}
    if "imdb" in ids and not ids["imdb"].startswith("tt"):
        ids["imdb"] = "tt" + ids["imdb"]
    if "imdb" not in ids and (m := _IMDB_BARE_RE.search(rel)):
        ids["imdb"] = m.group(1)
    return ids


def _release(g: dict) -> dict[str, str]:
    keys = {"screen_size": "resolution", "source": "source", "video_codec": "video_codec",
            "audio_codec": "audio_codec", "audio_channels": "audio_channels",
            "streaming_service": "service", "release_group": "group", "other": "other"}
    return {out: s for k, out in keys.items() if (s := _str(g.get(k)))}


def _clean_stem(name: str) -> str:
    stem = PurePosixPath(name).stem if "." in name else name
    stem = _ID_RE.sub(" ", stem)
    return _unquote(stem)


def _clean_dir(name: str) -> str:
    """Folder names have no extension: never strip a 'suffix' from 'Show.S01.1080p'."""
    s = _unquote(_ID_RE.sub(" ", name))
    return _core(s) or s


def _sxe(text: str) -> tuple[int, list[int], str] | None:
    """Season, episodes, and the text after the match (an episode title candidate)."""
    for rx in (_SXE_RE, _NXN_RE):
        m = rx.search(text)
        if m:
            eps = [int(m.group(2))] + [int(x) for x in re.findall(r"\d+", m.group(3) or "")]
            if len(eps) == 2 and eps[1] > eps[0] and "-" in (m.group(3) or ""):
                eps = list(range(eps[0], eps[1] + 1))  # S01E01-E03 is a range
            return int(m.group(1)), sorted(set(eps)), text[m.end():]
    return None


def _season_from_dir(name: str) -> int | None:
    n = _unquote(name)
    if _SPECIALS_RE.match(n):
        return 0
    if m := _SEASON_DIR_RE.match(n):
        return int(m.group(1) or m.group(2))
    return None


def _core(s: str) -> str:
    """The name without bracketed release-tag groups, for reading titles (not quality info)."""
    return re.sub(r"\s{2,}", " ", _RELEASE_GROUP_RE.sub(" ", s)).strip()


_SEASON_MARK_RE = re.compile(r"(?<![a-z0-9])(s\d{1,4}|season|series|staffel|saison|temporada)(?![a-z])", re.I)


def _folder_year(name: str, year: int | None) -> int | None:
    """The show's year from its folder. "Show 1989 S35 ..." names the show's year; in
    "Show - Series 5 (2019)" the year comes after the season marker and is the season's, not the show's."""
    if year is None:
        return None
    y, s = re.search(str(year), name), _SEASON_MARK_RE.search(name)
    return None if (y and s and s.start() < y.start()) else year


def _show_dir(dirs: list[str]) -> tuple[str | None, int | None]:
    """Which folder names the show, and the season of the season folder the file is in (if any).

    With a season folder ("S03", "Season 2", "Specials"), the show is the folder right above it: in a nested pack
    ("Star.Trek.Megapack/Star.Trek.DS9/S03/...") that's the series, not the pack. Folders below the season folder
    are release folders. Without one, the deepest folder that reads as a season pack ("Pack/The Simpsons S28/...")
    names the show, else the top folder does.
    """
    season_at = [i for i, d in enumerate(dirs) if _season_from_dir(d) is not None]
    if season_at:  # "Season 3/Season 3 Extras/x.avi": both are season folders; the show is above them
        above = [d for d in dirs[:season_at[-1]] if _season_from_dir(d) is None]
        return (above[-1] if above else None), _season_from_dir(dirs[season_at[-1]])
    chosen: tuple[str, str] | None = None  # (folder, its title)
    for d in reversed(dirs):
        gd = guessit(_clean_dir(d), {"type": "episode"})
        t = _title(gd)
        if not t or gd.get("episode") is not None or (gd.get("season") is None and not gd.get("year")):
            continue
        if chosen is None:
            chosen = (d, t)
        elif " " not in chosen[1] and title_key(t).startswith(title_key(chosen[1])):
            chosen = (d, t)  # "Parks and Recreation S01-07/Parks S07/...": the pack spells out the one-word inner name
    return (chosen[0] if chosen else dirs[0] if dirs else None), None


def parse_episode(rel: str) -> Parsed:
    parts = rel.replace("\\", "/").split("/")
    dirs, name = parts[:-1], parts[-1]
    stem = _clean_stem(name)
    p = Parsed(kind="episode", ids=_ids(rel), release=_release(guessit(stem, {"type": "episode"})))
    stem = _core(stem) or stem
    g = guessit(stem, {"type": "episode"})

    if hit := _sxe(stem):
        p.season, p.episodes, tail = hit
    else:
        tail = ""
        p.season = _int(g.get("season"))
        ep = g.get("episode")
        p.episodes = sorted(set(ep)) if isinstance(ep, list) else ([ep] if isinstance(ep, int) else [])

    season_dir = False
    if p.season is None:  # "Show/Season 2/Show - 05.mkv": season from the folders, deepest first
        for d in reversed(dirs):
            s = _season_from_dir(d)
            if s is None:
                s = _int(guessit(_unquote(d), {"type": "episode"}).get("season"))
            if s is not None:
                p.season, season_dir = s, True
                break
    if p.season is None and p.episodes:
        p.season = 1  # "Show/Show - 05.mkv": Plex treats a bare episode number as season 1

    # Show title: the folder that names the show (see _show_dir); else whatever the filename says.
    show_dir, folder_season = _show_dir(dirs)
    if folder_season is not None and not p.episodes:
        p.season, season_dir = folder_season, True  # "S03/.../ds9.s03.extra1.avi": an extra of the folder's season
    if show_dir:
        gd = guessit(_clean_dir(show_dir), {"type": "episode"})
        p.title = _title(gd)
        p.year = _folder_year(_clean_dir(show_dir), _int(gd.get("year")))
    if not p.title:
        p.title = _title(g)
    if p.year is None:
        p.year = _int(g.get("year"))

    et = _str(g.get("episode_title"))
    if (not et or _SXE_RE.search(et)) and tail:
        # guessit missed it, or swallowed the SxxEyy into it (quoted names): look at what follows SxxEyy,
        # letting guessit strip release tags. A bare release group ("...x264-TrollHD") is not a title.
        cand = _str(guessit(tail.strip(" ._-–:"), {"type": "movie"}).get("title"))
        junk = {(_str(v) or "").casefold() for v in (g.get("release_group"), g.get("streaming_service"),
                                                      p.release.get("group"), p.release.get("service"))}
        et = cand if cand and cand.casefold() not in junk else None
    p.episode_title = et
    if not p.episodes and season_dir and show_dir and p.title:
        # "Show/Season 00/Behind the Scenes.mkv": no episode number, but the folders say whose and which season
        # it is. Shown under that season (sorted after the numbered episodes), named after the file.
        p.unnumbered = True
        p.episode_title = _loose_title(stem, p.title)
    return p


def _loose_title(stem: str, show: str) -> str:
    """A name for an unnumbered episode: the file name without the show's name and release tags."""
    g = guessit(stem, {"type": "movie"})
    alt = g.get("alternative_title")
    if alt:  # "Star.Trek.DS9.S03.Extra10": guessit reads the show as the title and the rest as an alternative
        t = str(alt[-1] if isinstance(alt, list) else alt)
    else:
        t = _str(g.get("title")) or stem
        words, show_words = re.split(r"[\s._]+", t.strip()), re.split(r"[\s._]+", show.strip())
        if len(words) > len(show_words) and title_key(" ".join(words[:len(show_words)])) == title_key(show):
            t = " ".join(words[len(show_words):])
    return t.strip(" -–:._") or stem


def parse_movie(rel: str) -> Parsed:
    parts = rel.replace("\\", "/").split("/")
    dirs, name = parts[:-1], parts[-1]
    stem = _clean_stem(name)
    g = guessit(stem, {"type": "movie"})
    p = Parsed(kind="movie", ids=_ids(rel), release=_release(g))
    p.title = _title(g)
    p.year = _int(g.get("year"))
    p.part = _int(g.get("part")) or _int(g.get("cd"))
    p.edition = _str(g.get("edition"))

    if dirs:  # "Movie (Year)/whatever.mkv": the folder is often the better name
        gd = guessit(_clean_dir(dirs[-1]), {"type": "movie"})
        ft, fy = _title(gd), _int(gd.get("year"))
        generic = not p.title or p.title.casefold() in _GENERIC_STEMS
        if ft and (generic or (p.year is None and fy is not None)):
            p.title, p.year = ft, fy
        elif p.year is None:
            p.year = fy
    return p


def parse(rel: str, library_type: str) -> Parsed:
    return parse_episode(rel) if library_type == "show" else parse_movie(rel)
