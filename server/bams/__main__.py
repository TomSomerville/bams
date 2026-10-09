"""BAMS command line.

    bams serve                       run the server (API + scheduled scans)
    bams library add NAME --type show --path D:\\TV [--path ...] [--interval 6]
    bams library list | remove NAME
    bams scan NAME [--no-match] [--rematch]
    bams tmdb-key                    paste your own TMDB key (hidden prompt); --clear to remove
    bams user add NAME [--admin]     create an account (password prompt)
    bams user list | passwd NAME | remove NAME | unlock NAME
    bams security allow-all          let every address in again (if the IP lists shut you out)
    bams status
"""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import logging.handlers
import sys
from pathlib import Path

from .config import APP_NAME, DEFAULT_HOST, DEFAULT_PORT, VERSION, Paths, default_data_dir


def _setup_logging(paths: Paths, verbose: bool) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)
    paths.logs.mkdir(parents=True, exist_ok=True)
    fileh = logging.handlers.RotatingFileHandler(paths.logs / "bams.log", maxBytes=5_000_000, backupCount=3,
                                                 encoding="utf-8")
    fileh.setFormatter(fmt)
    root.addHandler(fileh)
    for noisy in ("httpx", "httpcore", "rebulk"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _web_dir() -> Path | None:
    for here in (Path(__file__).resolve().parent / "web",  # installed: the installers put the built UI here
                 Path(__file__).resolve().parents[2] / "web" / "dist"):  # repo checkout
        if here.is_dir():
            return here
    return None


def _new_password() -> str:
    pw = getpass.getpass("Password (input hidden): ")
    if getpass.getpass("Same password again: ") != pw:
        print("error: the passwords don't match", file=sys.stderr)
        sys.exit(2)
    return pw


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="bams", description=f"{APP_NAME} {VERSION} - Bad Ass Media Server")
    p.add_argument("--data-dir", type=Path, help=f"default: {default_data_dir()} (or env BAMS_DATA_DIR)")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="run the server")
    s.add_argument("--host", default=DEFAULT_HOST,
                   help="bind address (default 127.0.0.1, this computer only; 0.0.0.0 = every network interface)")
    s.add_argument("--port", type=int, default=DEFAULT_PORT)

    lib = sub.add_parser("library", help="manage libraries").add_subparsers(dest="lcmd", required=True)
    la = lib.add_parser("add")
    la.add_argument("name")
    la.add_argument("--type", required=True, choices=["show", "movie", "music"])
    la.add_argument("--path", action="append", required=True, help="media folder (repeatable). Read-only to BAMS")
    la.add_argument("--interval", type=float, default=6, help="hours between automatic scans (default 6)")
    lib.add_parser("list")
    lr = lib.add_parser("remove", help="forget a library (media files are never touched)")
    lr.add_argument("name")

    sc = sub.add_parser("scan", help="scan a library now (in this process)")
    sc.add_argument("name")
    sc.add_argument("--no-match", action="store_true", help="index files only, skip TMDB")
    sc.add_argument("--rematch", action="store_true", help="also retry titles that failed to match before")

    k = sub.add_parser("tmdb-key", help="set your own TMDB API key / Read Access Token")
    k.add_argument("--clear", action="store_true")

    us = sub.add_parser("user", help="manage accounts").add_subparsers(dest="ucmd", required=True)
    ua = us.add_parser("add", help="create an account (asks for its password)")
    ua.add_argument("name")
    ua.add_argument("--admin", action="store_true", help="can manage libraries, settings and accounts")
    us.add_parser("list")
    up = us.add_parser("passwd", help="set a new password (signs the user out everywhere)")
    up.add_argument("name")
    ur = us.add_parser("remove")
    ur.add_argument("name")
    ul = us.add_parser("unlock", help="unlock an account locked after wrong passwords (or by an admin)")
    ul.add_argument("name")

    se = sub.add_parser("security", help="security settings").add_subparsers(dest="scmd", required=True)
    se.add_parser("allow-all", help="switch the IP lists to 'allow everyone except the block list'")

    sub.add_parser("status")
    a = p.parse_args(argv)

    paths = Paths(a.data_dir or default_data_dir())
    _setup_logging(paths, a.verbose)

    from . import jobs, library
    from .app import bootstrap, create_app
    from .db import connect, get_setting, set_setting
    from .tmdb import InvalidKey, Tmdb, TmdbError

    bootstrap(paths)
    log = logging.getLogger("bams")

    if a.cmd == "serve":
        import uvicorn
        if a.host not in ("127.0.0.1", "localhost", "::1"):
            log.info("listening on %s: other devices can reach BAMS (they have to sign in). For access from the "
                     "internet, put it behind an HTTPS reverse proxy", a.host)
        from . import auth
        con = connect(paths.db)
        try:
            if not auth.user_count(con):
                log.warning("no accounts yet: open http://localhost:%s on this computer to create the admin "
                            "account, or run `bams user add NAME --admin`", a.port)
        finally:
            con.close()
        log.info("BAMS %s  data dir: %s  http://%s:%s  (API docs at /docs)", VERSION, paths.root, a.host, a.port)
        uvicorn.run(create_app(paths, web_dir=_web_dir()), host=a.host, port=a.port, log_level="info")
        return 0

    con = connect(paths.db)
    try:
        if a.cmd == "library":
            if a.lcmd == "add":
                lib_id = library.create(con, paths.root, a.name, a.type, a.path, a.interval)
                print(json.dumps(library.describe(con, library.get(con, lib_id)), indent=2))
            elif a.lcmd == "list":
                for r in library.listed(con):
                    print(json.dumps(library.describe(con, r), indent=2))
            elif a.lcmd == "remove":
                library.delete(con, library.get(con, a.name)["id"])
                print(f"removed library {a.name!r} (media files untouched)")
        elif a.cmd == "scan":
            lib_id = library.get(con, a.name)["id"]
            res = jobs.run_scan(paths, lib_id, "manual", do_match=not a.no_match, retry_unmatched=a.rematch,
                                progress=lambda m, *_: log.info(m))
            print(json.dumps(res, indent=2))
            return 0 if res["status"] != "error" else 1
        elif a.cmd == "tmdb-key":
            if a.clear:
                set_setting(con, "tmdb_key", None)
                print("TMDB key removed")
                return 0
            key = getpass.getpass("Paste your TMDB API Read Access Token or API Key (input hidden): ").strip()
            try:
                t = Tmdb(key)
                t.check()
                t.close()
            except InvalidKey as e:
                print(f"Not saved: {e}", file=sys.stderr)
                return 1
            except TmdbError as e:
                print(f"Couldn't verify with TMDB ({e}); saving anyway.", file=sys.stderr)
            set_setting(con, "tmdb_key", key)
            print(f"TMDB key saved (…{key[-4:]})")
        elif a.cmd == "user":
            from . import auth
            try:
                if a.ucmd == "add":
                    pw = _new_password()
                    auth.create_user(con, a.name, pw, a.admin)
                    print(f"created {'admin ' if a.admin else ''}account {a.name!r}")
                elif a.ucmd == "list":
                    for u in con.execute("SELECT * FROM users ORDER BY name COLLATE NOCASE"):
                        print(f"{u['name']}{'  (admin)' if u['is_admin'] else ''}")
                elif a.ucmd in ("passwd", "remove", "unlock"):
                    u = auth.get_user(con, a.name)
                    if not u:
                        print(f"error: no account called {a.name!r}", file=sys.stderr)
                        return 2
                    if a.ucmd == "unlock":
                        from . import security
                        sec = security.Security(paths.security_db, paths.db)
                        sec.unlock(u["id"])
                        sec.log("unlock", "admin", name=u["name"], user_id=u["id"], reason="by the command line")
                        print(f"unlocked {u['name']!r}")
                    elif a.ucmd == "passwd":
                        auth.update_user(con, u["id"], password=_new_password())
                        print(f"password changed for {u['name']!r}")
                    else:
                        auth.delete_user(con, u["id"])
                        print(f"removed account {u['name']!r} (and its watch history)")
            except auth.AuthError as e:
                print(f"error: {e}", file=sys.stderr)
                return 2
        elif a.cmd == "security":
            set_setting(con, "ip_mode", "allow_all")
            print("IP lists: every address may connect except those on the block list (a running server picks "
                  "this up within 10 seconds)")
        elif a.cmd == "status":
            libs = [library.describe(con, r) for r in library.listed(con)]
            from . import probe, readonly
            print(json.dumps({"version": VERSION, "data_dir": str(paths.root), "ffprobe": probe.ffprobe_path(),
                              "tmdb_configured": bool(get_setting(con, "tmdb_key")),
                              "protected_roots": list(readonly.protected_roots()), "libraries": libs}, indent=2))
    except library.LibraryError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
