"""Holidays: which movies and episodes are about one, and which holiday is next / just past (Home rows and library
filters "Upcoming holiday" / "Recent holiday", owner 2026-10-19).

Dates are worked out here, with no calendar service: fixed days, "the nth weekday of a month" rules, Easter's
computus, Hanukkah from the Hebrew calendar, and Lunar New Year from a table (it follows the moon). Titles are matched
by words in their own title, tagline and description (movies and episodes), plus TMDB's keywords for movies
(`items.extra.keywords`, filled while identifying). Admins can add or take out a title by hand (`holiday_tags`).

Everything is matched once and kept in memory until a title changes (`titles()`), so rows and filters cost a set
lookup, not a scan.
"""

from __future__ import annotations

import datetime as dt
import re
import sqlite3
import threading
from dataclasses import dataclass
from typing import Callable

from .db import jload

Date = dt.date


def _fixed(month: int, day: int) -> Callable[[int], Date]:
    return lambda y: Date(y, month, day)


def _nth_weekday(month: int, weekday: int, n: int) -> Callable[[int], Date]:
    """The n-th `weekday` (Mon=0) of `month`; n=-1 = the last one."""
    def f(y: int) -> Date:
        if n > 0:
            d = Date(y, month, 1)
            return d + dt.timedelta(days=(weekday - d.weekday()) % 7 + 7 * (n - 1))
        d = Date(y + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)
        return d - dt.timedelta(days=(d.weekday() - weekday) % 7)
    return f


def easter(y: int) -> Date:
    """Western Easter Sunday (the anonymous Gregorian computus)."""
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month = (h + m - 7 * n + 114) // 31
    return Date(y, month, (h + m - 7 * n + 114) % 31 + 1)


# ---- the Hebrew calendar, for Hanukkah (25 Kislev). Arithmetic from Reingold & Dershowitz, "Calendrical
# Calculations": days counted from the Gregorian 0001-01-01 = 1 (Python's date.toordinal()).

_HEBREW_EPOCH = -1373427  # R.D. of 1 Tishri, year 1 (the Hebrew epoch), in the proleptic Gregorian count


def _hebrew_leap(y: int) -> bool:
    return (7 * y + 1) % 19 < 7


def _hebrew_elapsed(y: int) -> int:
    months = (235 * y - 234) // 19
    parts = 12084 + 13753 * months
    day = 29 * months + parts // 25920
    return day + 1 if (3 * (day + 1)) % 7 < 3 else day


def _hebrew_new_year(y: int) -> int:
    """R.D. of 1 Tishri of Hebrew year y."""
    ny0, ny1, ny2 = _hebrew_elapsed(y - 1), _hebrew_elapsed(y), _hebrew_elapsed(y + 1)
    delay = 2 if ny2 - ny1 == 356 else 1 if ny1 - ny0 == 382 else 0
    return _HEBREW_EPOCH + ny1 + delay


def _kislev_25(hebrew_year: int) -> Date:
    """25 Kislev: Tishri (30 days) and Heshvan (29 or 30) come first."""
    start = _hebrew_new_year(hebrew_year)
    days_in_year = _hebrew_new_year(hebrew_year + 1) - start
    heshvan = 30 if days_in_year % 10 == 5 else 29  # a "complete" year (355/385 days) has a 30-day Heshvan
    return Date.fromordinal(start + 30 + heshvan + 24)


def hanukkah(y: int) -> Date:
    """The evening Hanukkah begins in Gregorian year y (the eve of 25 Kislev)."""
    return _kislev_25(y + 3761) - dt.timedelta(days=1)


# Lunar New Year follows the moon (the second new moon after the winter solstice, in China's time zone): a table.
LUNAR_NEW_YEAR = {
    2020: (1, 25), 2021: (2, 12), 2022: (2, 1), 2023: (1, 22), 2024: (2, 10), 2025: (1, 29), 2026: (2, 17),
    2027: (2, 6), 2028: (1, 26), 2029: (2, 13), 2030: (2, 3), 2031: (1, 23), 2032: (2, 11), 2033: (1, 31),
    2034: (2, 19), 2035: (2, 8), 2036: (1, 28), 2037: (2, 15), 2038: (2, 4), 2039: (1, 24), 2040: (2, 12),
    2041: (2, 1), 2042: (1, 22), 2043: (2, 10), 2044: (1, 30), 2045: (2, 17), 2046: (2, 6), 2047: (1, 26),
    2048: (2, 14), 2049: (2, 2), 2050: (1, 23),
}


def lunar_new_year(y: int) -> Date | None:
    md = LUNAR_NEW_YEAR.get(y)
    return Date(y, *md) if md else None


@dataclass(frozen=True)
class Holiday:
    id: str
    name: str
    date: Callable[[int], Date | None]
    words: re.Pattern


def _words(*alternatives: str) -> re.Pattern:
    return re.compile(r"(?<![\w'])(?:" + "|".join(alternatives) + r")(?![\w])", re.I)


APOS = "['’]?"  # Valentine's / Valentines / Valentine’s

HOLIDAYS: tuple[Holiday, ...] = (
    Holiday("new_year", "New Year's", _fixed(1, 1),
            _words(f"new year{APOS}s(?: eve| day)?", "new years? eve", "hogmanay", "auld lang syne")),
    Holiday("lunar_new_year", "Lunar New Year", lunar_new_year,
            _words("lunar new year", "chinese new year")),
    Holiday("valentines", "Valentine's Day", _fixed(2, 14),
            _words(f"valentine{APOS}s(?: day)?", "saint valentine", r"st\.? valentine")),
    Holiday("st_patricks", "St. Patrick's Day", _fixed(3, 17),
            _words(rf"(?:st\.?|saint) patrick{APOS}s(?: day)?", f"(?:st\\.? )?paddy{APOS}s day")),
    Holiday("easter", "Easter", easter,
            _words(r"easter(?! island)", "resurrection sunday")),
    Holiday("mothers_day", "Mother's Day", _nth_weekday(5, 6, 2), _words(f"mother{APOS}s day", "mothering sunday")),
    Holiday("memorial_day", "Memorial Day", _nth_weekday(5, 0, -1), _words("memorial day")),
    Holiday("fathers_day", "Father's Day", _nth_weekday(6, 6, 3), _words(f"father{APOS}s day")),
    Holiday("independence_day", "Independence Day", _fixed(7, 4),
            _words("independence day", "(?:fourth|4th) of july", "july (?:4th|fourth)")),
    Holiday("labor_day", "Labor Day", _nth_weekday(9, 0, 1), _words("labou?r day")),
    Holiday("halloween", "Halloween", _fixed(10, 31),
            _words("halloween", "hallowe['’]?en", "trick[- ]or[- ]treat(?:ing|ers?)?", f"all hallows{APOS} eve",
                   "jack[- ]o['’]?[- ]lanterns?")),
    Holiday("day_of_the_dead", "Day of the Dead", _fixed(11, 1),
            _words("day of the dead", "d[ií]a de (?:los )?muertos")),
    Holiday("thanksgiving", "Thanksgiving", _nth_weekday(11, 3, 4), _words("thanksgiving")),
    Holiday("hanukkah", "Hanukkah", hanukkah, _words("hanukk?ah", "chanukk?ah")),
    Holiday("christmas", "Christmas", _fixed(12, 25),
            _words("christmas", "x-?mas", "yuletide", "santa claus", "kris kringle", "saint nick", r"st\.? nick")),
    Holiday("kwanzaa", "Kwanzaa", _fixed(12, 26), _words("kwanzaa")),
)
BY_ID = {h.id: h for h in HOLIDAYS}


def occurrence(h: Holiday, today: Date, forward: bool) -> Date | None:
    """`h`'s next date on or after `today` (forward) or its last date before it."""
    for y in ((today.year, today.year + 1) if forward else (today.year, today.year - 1)):
        d = h.date(y)
        if d and (d >= today if forward else d < today):
            return d
    return None


def today() -> Date:
    """The server's own date (tests patch it)."""
    return Date.today()


def next_and_recent(today: Date) -> tuple[tuple[Holiday, Date], tuple[Holiday, Date]]:
    """The next holiday (today counts as upcoming) and the most recent one before today."""
    nxt = min(((h, d) for h in HOLIDAYS if (d := occurrence(h, today, True))), key=lambda x: (x[1], x[0].id))
    rec = max(((h, d) for h in HOLIDAYS if (d := occurrence(h, today, False))), key=lambda x: (x[1], x[0].id))
    return nxt, rec


def matches(text: str) -> set[str]:
    """The holidays a piece of text is about."""
    return {h.id for h in HOLIDAYS if h.words.search(text)} if text else set()


# ---- which titles are about which holiday, kept until something changes

_lock = threading.Lock()
_cache: dict[str, object] = {"key": None, "titles": {}}


def _fingerprint(con: sqlite3.Connection) -> tuple:
    items = con.execute("SELECT COUNT(*), MAX(updated_at) FROM items WHERE kind IN ('movie','episode')").fetchone()
    tags = con.execute("SELECT COUNT(*), MAX(rowid), TOTAL(tagged) FROM holiday_tags").fetchone()
    return tuple(items) + tuple(tags)


def titles(con: sqlite3.Connection) -> dict[str, set[int]]:
    """holiday id -> the movies and episodes about it."""
    key = _fingerprint(con)
    with _lock:
        if _cache["key"] == key:
            return _cache["titles"]  # type: ignore[return-value]
    out: dict[str, set[int]] = {h.id: set() for h in HOLIDAYS}
    for r in con.execute("""SELECT id, title, tagline, overview, json_extract(extra, '$.keywords') AS keywords
                            FROM items WHERE kind IN ('movie','episode')"""):
        text = " \n".join(x for x in (r["title"], r["tagline"], r["overview"]) if x)
        kw = jload(r["keywords"]) if r["keywords"] else None
        if kw:
            text += " \n" + " \n".join(kw)
        for hid in matches(text):
            out[hid].add(r["id"])
    for r in con.execute("SELECT item_id, holiday, tagged FROM holiday_tags"):
        if r["holiday"] in out:
            (out[r["holiday"]].add if r["tagged"] else out[r["holiday"]].discard)(r["item_id"])
    with _lock:
        _cache.update(key=key, titles=out)
    return out


def of_item(con: sqlite3.Connection, item_id: int) -> list[dict]:
    """Every holiday with whether this movie/episode is in it, and whether by hand (`tagged`: True/False/None)."""
    t = titles(con)
    hand = {r["holiday"]: bool(r["tagged"]) for r in
            con.execute("SELECT holiday, tagged FROM holiday_tags WHERE item_id=?", (item_id,))}
    return [{"id": h.id, "name": h.name, "on": item_id in t[h.id], "tagged": hand.get(h.id)} for h in HOLIDAYS]


def set_tag(con: sqlite3.Connection, item_id: int, holiday: str, tagged: bool | None) -> None:
    """Put a title in a holiday (True), keep it out (False), or go back to automatic (None)."""
    if tagged is None:
        con.execute("DELETE FROM holiday_tags WHERE item_id=? AND holiday=?", (item_id, holiday))
    else:
        con.execute("""INSERT INTO holiday_tags (item_id, holiday, tagged) VALUES (?, ?, ?)
                       ON CONFLICT (item_id, holiday) DO UPDATE SET tagged=excluded.tagged""",
                    (item_id, holiday, int(tagged)))
