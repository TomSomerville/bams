"""User accounts and login sessions.

- Passwords are stored as scrypt hashes (stdlib `hashlib.scrypt`, no extra dependency).
- Signing in sets an HttpOnly cookie holding a random token. The DB keeps only its SHA-256, so a copy of the
  database can't be used to sign in. Sessions last SESSION_DAYS after their last use.
- The very first account (an admin) is created from the web UI only by a browser on the server itself
  (loopback), so nobody else on the network can claim a fresh server; `bams user add` works anywhere.
- Repeated wrong passwords from one address are slowed down (Throttle).
- An admin can make an account set a new password at its next sign-in (`must_change_password`): until it does, its
  session opens only the password change (app.LoginRequired).
- Two-step sign-in: each account can add a time-based code (TOTP, RFC 6238: SHA-1, 6 digits, 30 s, the kind Google
  Authenticator and other authenticator apps make). Stdlib only. A code is accepted once, +-1 step for clock drift.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import sqlite3
import struct
import threading
import time
from urllib.parse import quote, urlencode

from .db import jdump, jload, now

COOKIE = "bams_session"
SESSION_DAYS = 30
MIN_PASSWORD = 8
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}  # ~50 ms and 16 MB per hash


class AuthError(ValueError):
    """A rejected account change; the message is shown to the user."""


# ------------------------------------------------------------------ passwords

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${b64(salt)}${b64(h)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, h = stored.split("$")
        if algo != "scrypt":
            return False
        want = base64.b64decode(h)
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                             dklen=len(want))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, want)


# A hash to check against when the name doesn't exist, so a wrong name takes as long as a wrong password.
_DUMMY = hash_password(secrets.token_hex(8))


def _check_name(name: str) -> str:
    name = (name or "").strip()
    if not 1 <= len(name) <= 40:
        raise AuthError("Names are 1 to 40 characters long.")
    if any(c in name for c in "\r\n\t") or not name.isprintable():
        raise AuthError("Names can't contain control characters.")
    return name


def _check_password(password: str) -> str:
    if len(password or "") < MIN_PASSWORD:
        raise AuthError(f"Passwords need at least {MIN_PASSWORD} characters.")
    if len(password) > 1024:
        raise AuthError("That password is too long.")
    return password


# ------------------------------------------------------------------ users

def user_count(con: sqlite3.Connection) -> int:
    return con.execute("SELECT COUNT(*) FROM users").fetchone()[0]


# Each user's display preferences: name -> default. Unknown names are ignored when saving.
PREFS: dict[str, object] = {
    "home_hero": True,   # the rotating "Recently added" banner at the top of Home
    # Home's rows in the user's order, each {"id", "show"}: "continue", "recent", "lib:<id>", "top_rated",
    # "genre:<name>" (older saves: one "genres" entry for every genre).
    # Empty = the default layout; rows missing from the list (a new library) are shown at their default place.
    "home_rows": [],
}
MAX_HOME_ROWS = 200


def _home_rows(v) -> list | None:
    if not isinstance(v, list) or len(v) > MAX_HOME_ROWS:
        return None
    rows, seen = [], set()
    for r in v:
        if not (isinstance(r, dict) and isinstance(r.get("id"), str) and 0 < len(r["id"]) <= 100
                and isinstance(r.get("show"), bool)):
            return None
        if r["id"] not in seen:
            seen.add(r["id"])
            rows.append({"id": r["id"], "show": r["show"]})
    return rows


def _valid(k: str, v):
    """The value to store for pref k, or None when it isn't a valid one."""
    if k == "home_rows":
        return _home_rows(v)
    return v if isinstance(v, type(PREFS[k])) else None


def prefs(u: sqlite3.Row) -> dict:
    saved = jload(u["prefs"]) or {}
    return {k: saved.get(k, default) for k, default in PREFS.items()}


def set_prefs(con: sqlite3.Connection, user_id: int, changes: dict) -> dict:
    u = get_user(con, user_id)
    ok = {k: _valid(k, v) for k, v in changes.items() if k in PREFS}
    new = {**prefs(u), **{k: v for k, v in ok.items() if v is not None}}
    con.execute("UPDATE users SET prefs=? WHERE id=?", (jdump(new), user_id))
    return new


def public(u: sqlite3.Row) -> dict:
    return {"id": u["id"], "name": u["name"], "is_admin": bool(u["is_admin"]),
            "created_at": u["created_at"], "last_login_at": u["last_login_at"], "prefs": prefs(u),
            "must_change_password": bool(u["must_change_password"]), "two_factor": bool(u["totp_secret"])}


def get_user(con: sqlite3.Connection, ref: int | str) -> sqlite3.Row | None:
    col = "id" if isinstance(ref, int) else "name"
    return con.execute(f"SELECT * FROM users WHERE {col}=?", (ref,)).fetchone()


def create_user(con: sqlite3.Connection, name: str, password: str, is_admin: bool = False,
                must_change_password: bool = False) -> int:
    name = _check_name(name)
    _check_password(password)
    if get_user(con, name):
        raise AuthError(f"There's already a user called {name!r}.")
    return con.execute("INSERT INTO users(name, password, is_admin, created_at, must_change_password) "
                       "VALUES (?,?,?,?,?)",
                       (name, hash_password(password), int(is_admin), now(), int(must_change_password))).lastrowid


def update_user(con: sqlite3.Connection, user_id: int, *, name: str | None = None, password: str | None = None,
                is_admin: bool | None = None, must_change_password: bool | None = None) -> None:
    """An admin's change to an account. A new password or turning on "must change password" signs the user out
    everywhere, so their next sign-in is the one that asks for a new password. A new password without the flag
    in the same call clears it."""
    u = get_user(con, user_id)
    if not u:
        raise AuthError("No such user.")
    if name is not None:
        name = _check_name(name)
        other = get_user(con, name)
        if other and other["id"] != user_id:
            raise AuthError(f"There's already a user called {name!r}.")
        con.execute("UPDATE users SET name=? WHERE id=?", (name, user_id))
    if is_admin is not None and not is_admin and u["is_admin"] and _admins(con) <= 1:
        raise AuthError("BAMS needs at least one admin. Make someone else an admin first.")
    if is_admin is not None:
        con.execute("UPDATE users SET is_admin=? WHERE id=?", (int(is_admin), user_id))
    if password is not None:
        con.execute("UPDATE users SET password=?, must_change_password=? WHERE id=?",
                    (hash_password(_check_password(password)), int(bool(must_change_password)), user_id))
        con.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))  # signed out everywhere
    elif must_change_password is not None:
        con.execute("UPDATE users SET must_change_password=? WHERE id=?", (int(must_change_password), user_id))
        if must_change_password and not u["must_change_password"]:
            con.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))


def change_own_password(con: sqlite3.Connection, user_id: int, current: str, new: str) -> None:
    """The user's own change (they know the current password). Clears "must change password" and signs them out
    everywhere (the caller starts a new session for the device that asked)."""
    u = get_user(con, user_id)
    if not verify_password(current or "", u["password"]):
        raise AuthError("Your current password isn't right.")
    _check_password(new)
    if verify_password(new, u["password"]):
        raise AuthError("Pick a password that's different from the current one.")
    con.execute("UPDATE users SET password=?, must_change_password=0 WHERE id=?", (hash_password(new), user_id))
    con.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))


def delete_user(con: sqlite3.Connection, user_id: int) -> None:
    u = get_user(con, user_id)
    if not u:
        raise AuthError("No such user.")
    if u["is_admin"] and _admins(con) <= 1:
        raise AuthError("BAMS needs at least one admin, so the last one can't be removed.")
    con.execute("DELETE FROM users WHERE id=?", (user_id,))  # sessions and watch state cascade


def _admins(con: sqlite3.Connection) -> int:
    return con.execute("SELECT COUNT(*) FROM users WHERE is_admin=1").fetchone()[0]


def authenticate(con: sqlite3.Connection, name: str, password: str) -> sqlite3.Row | None:
    u = get_user(con, (name or "").strip())
    if not u:
        verify_password(password or "", _DUMMY)
        return None
    return u if verify_password(password or "", u["password"]) else None


# ------------------------------------------------------------------ two-step sign-in (TOTP)

TOTP_STEP = 30
TOTP_DIGITS = 6


def new_totp_secret() -> str:
    """160 random bits in base32 (what authenticator apps take), without padding."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _secret_bytes(secret: str) -> bytes:
    s = "".join(secret.split()).upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def totp(secret: str, step: int) -> str:
    """The code for one time step (RFC 6238 over RFC 4226)."""
    h = hmac.new(_secret_bytes(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    n = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 10**TOTP_DIGITS
    return str(n).zfill(TOTP_DIGITS)


def totp_step(code: str, secret: str, last: int | None = None, t: float | None = None) -> int | None:
    """The time step `code` belongs to (now, or one step either side for clock drift), or None. Steps at or before
    `last` (the last code used) don't count, so a code can't be used twice."""
    code = "".join((code or "").split())
    if not (len(code) == TOTP_DIGITS and code.isdigit()):
        return None
    try:
        _secret_bytes(secret)
    except (ValueError, TypeError):
        return None
    now_step = int((time.time() if t is None else t) // TOTP_STEP)
    for step in (now_step, now_step - 1, now_step + 1):
        if (last is None or step > last) and hmac.compare_digest(totp(secret, step), code):
            return step
    return None


def totp_uri(secret: str, account: str, issuer: str) -> str:
    """The otpauth:// link an authenticator app reads from the QR code."""
    label = quote(f"{issuer}:{account}", safe="")
    return f"otpauth://totp/{label}?" + urlencode({"secret": secret, "issuer": issuer, "algorithm": "SHA1",
                                                   "digits": TOTP_DIGITS, "period": TOTP_STEP}, quote_via=quote)


def check_code(con: sqlite3.Connection, u: sqlite3.Row, code: str | None) -> bool:
    """Whether `code` is a right, unused code for u's two-step sign-in. A right one is used up."""
    step = totp_step(code or "", u["totp_secret"], u["totp_last"])
    if step is None:
        return False
    # of two requests with the same code at once, only one moves totp_last past it
    return con.execute("UPDATE users SET totp_last=? WHERE id=? AND (totp_last IS NULL OR totp_last < ?)",
                       (step, u["id"], step)).rowcount == 1


def enable_two_factor(con: sqlite3.Connection, user_id: int, secret: str, code: str) -> None:
    """Turn on two-step sign-in with `secret`, once the app shows a right code for it."""
    step = totp_step(code, secret)
    if step is None:
        raise AuthError("That code doesn't match. Type the code the app shows for BAMS now (it changes every 30 "
                        "seconds), and check that the phone's clock is right.")
    con.execute("UPDATE users SET totp_secret=?, totp_last=? WHERE id=?", ("".join(secret.split()).upper(), step,
                                                                          user_id))


def disable_two_factor(con: sqlite3.Connection, user_id: int) -> None:
    con.execute("UPDATE users SET totp_secret=NULL, totp_last=NULL WHERE id=?", (user_id,))


# ------------------------------------------------------------------ sessions

def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


digest = _digest  # what `sessions.token` stores for a token (media tickets name sessions by it)


def new_session(con: sqlite3.Connection, user_id: int, user_agent: str | None = None) -> str:
    token = secrets.token_urlsafe(32)
    t = now()
    con.execute("INSERT INTO sessions(token, user_id, created_at, last_seen_at, user_agent) VALUES (?,?,?,?,?)",
                (_digest(token), user_id, t, t, (user_agent or "")[:300]))
    con.execute("UPDATE users SET last_login_at=? WHERE id=?", (t, user_id))
    con.execute("DELETE FROM sessions WHERE last_seen_at < ?", (t - SESSION_DAYS * 86400,))  # tidy up
    return token


def session_user(con: sqlite3.Connection, token: str | None) -> sqlite3.Row | None:
    """The signed-in user for a cookie value, or None. Sliding expiry: last_seen_at is refreshed at most
    hourly, so a stream's many requests don't each write to the DB."""
    if not token or len(token) > 100:
        return None
    return session_user_by_digest(con, _digest(token))


def session_user_by_digest(con: sqlite3.Connection, d: str) -> sqlite3.Row | None:
    """session_user for a session named by its stored digest (a media ticket's)."""
    r = con.execute("""SELECT u.*, s.last_seen_at AS seen FROM sessions s JOIN users u ON u.id=s.user_id
                       WHERE s.token=?""", (d,)).fetchone()
    t = now()
    if not r or r["seen"] < t - SESSION_DAYS * 86400:
        return None
    if r["seen"] < t - 3600:
        con.execute("UPDATE sessions SET last_seen_at=? WHERE token=?", (t, d))
    return r


def end_session(con: sqlite3.Connection, token: str | None) -> None:
    if token:
        con.execute("DELETE FROM sessions WHERE token=?", (_digest(token),))


# ------------------------------------------------------------------ throttle

class Throttle:
    """At most MAX failed sign-ins per address per WINDOW seconds."""

    MAX = 10
    WINDOW = 600.0

    def __init__(self):
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def blocked(self, addr: str) -> bool:
        with self._lock:
            t = time.monotonic()
            fails = [f for f in self._fails.get(addr, []) if f > t - self.WINDOW]
            self._fails[addr] = fails
            return len(fails) >= self.MAX

    def fail(self, addr: str) -> None:
        with self._lock:
            self._fails.setdefault(addr, []).append(time.monotonic())

    def ok(self, addr: str) -> None:
        with self._lock:
            self._fails.pop(addr, None)


def is_loopback(host: str | None) -> bool:
    return host in ("127.0.0.1", "::1", "localhost") or bool(host and host.startswith("127."))
