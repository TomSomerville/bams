---
name: bams-server
description: Connect to the owner's BAMS server (Ubuntu 24.04 at 192.168.1.253) over SSH and troubleshoot it - read its log, check the service and version, look things up in its database read-only, reproduce FFmpeg/HLS/VAAPI failures with the real files, try patched code there, and tell the owner how to update it. Use when the owner reports a playback or server problem ("X doesn't play", "the server is slow", "check the server log", "what version is the server on"), or before/after shipping a fix that touches FFmpeg commands.
---

# The owner's BAMS server (SSH)

Since 2026-10-10 the owner's main BAMS runs on a separate Ubuntu machine, not on this PC. This PC can reach it
over SSH with a key made for this purpose. Run everything with the Bash tool (Git Bash).

| What | Value |
|---|---|
| Server | `192.168.1.253`, hostname `server`, Ubuntu 24.04.5, Intel HD 630 (`/dev/dri/renderD128`) |
| SSH | alias **`bams-server`** in `~/.ssh/config` (user `beached`, key `~/.ssh/bams_claude`, `IdentitiesOnly yes`) |
| Account | `beached` = the account BAMS runs as (`BAMS_USER` in `/etc/default/bams`); groups `adm`, `render`, `sudo` (sudo needs the owner's password: never use it) |
| BAMS | the released `.deb`: code `/opt/bams/lib/bams`, Python `/opt/bams/venv/bin/python`, systemd `bams.service` (+ drop-in `/etc/systemd/system/bams.service.d/10-user.conf`), port 8484 on all interfaces |
| Data dir | `/var/lib/bams`: `bams.db`, `security.db`, `logs/bams.log` (5 MB, `.1`–`.3` kept), `transcode/`, `cache/`, `images/` |
| FFmpeg | `/usr/bin/ffmpeg` 6.1.1 (Ubuntu's). Windows has 9.x: **behaviour differs** (see "Known failures") |
| Media | NAS share `//192.168.1.254/server` (CIFS) on `/mnt/nas`; library folders under `/mnt/nas/jellyfin-media/` (`shows`, `movies`, `Music`). Read the real list from the DB (below) |
| Tools there | `python3`, `strace`, `journalctl`, `findmnt`. No `sqlite3` CLI, no `vainfo` |

## Rules

- **Read-only.** Look, don't change. Write only under `/tmp/bams-debug/`, and `rm -rf` it when done. Never write in a
  media folder (CLAUDE.md rule 1): FFmpeg test output goes to `/tmp/bams-debug`, never next to the file.
- **Always `-o BatchMode=yes`** so a broken key fails at once instead of waiting at a password prompt.
- **Never type, ask for or use the owner's password** (sudo, login). Anything that needs sudo (restart, install,
  groups, packages, config) is the owner's: give them the exact command (see "Needs the owner").
- **Don't stop, restart or kill** BAMS or its FFmpeg processes (someone may be watching), and never by name.
- **Secrets stay put:** don't dump `users` (password hashes, TOTP secrets), `security.db`, or `settings` (the TMDB key:
  CLAUDE.md rule 4). Query only the columns you need.
- Long or awkward scripts: write them to the scratchpad and pipe them in (`ssh bams-server python3 - < script.py`),
  which avoids quoting trouble. Heredocs inside `ssh '…'` can't contain single quotes.

## Connect / check

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 bams-server 'whoami; systemctl is-active bams; dpkg -s bams | grep ^Version'
```

Expect `beached`, `active`, `Version: 0.9.x`. If it fails:

| Error | Cause → what to do |
|---|---|
| `Connection timed out` / `No route to host` | Server off or its address changed. Ask the owner. New address: update `HostName` in `~/.ssh/config`, this file, STATUS.md §6 |
| `Connection refused` | SSH server not running: owner runs `sudo systemctl start ssh` (package `openssh-server`) |
| `Permission denied (publickey,password)` | The key isn't accepted (removed, or the account changed). Put it back (below) |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | Reinstalled server, or another machine got the address. **Stop and tell the owner**; only after they confirm: `ssh-keygen -R 192.168.1.253` and connect again |

**Put the key back** (the owner types their password; you never see it). Open it in their Terminal panel with
`run_in_terminal` (PowerShell there, so call Git Bash's `ssh-copy-id`):

```
& "C:\Program Files\Git\bin\bash.exe" -lc "ssh-copy-id -i ~/.ssh/bams_claude.pub bams-server"
```

The user name is lowercase `beached` (Ubuntu names are lowercase; `Beached` is refused). If `~/.ssh/bams_claude` is
gone, make a new one first: `ssh-keygen -t ed25519 -f ~/.ssh/bams_claude -N "" -C claude-bams -q`, and add to
`~/.ssh/config`:

```
Host bams-server
    HostName 192.168.1.253
    User beached
    IdentityFile ~/.ssh/bams_claude
    IdentitiesOnly yes
```

## Read the log

```bash
ssh -o BatchMode=yes bams-server 'tail -n 150 /var/lib/bams/logs/bams.log'
ssh -o BatchMode=yes bams-server 'grep -n -E "WARNING|ERROR|Traceback" /var/lib/bams/logs/bams.log | tail -80'
ssh -o BatchMode=yes bams-server "sed -n '/^2026-10-10 16:5/,\$p' /var/lib/bams/logs/bams.log | grep -v progress"   # from a time on
ssh -o BatchMode=yes bams-server 'journalctl -u bams --since "-30 min" --no-pager | tail -50'   # + HTTP access lines, crashes
```

To catch a problem as it happens: note the time (`ssh bams-server date`), ask the owner to reproduce it, then read
from that minute on. What the lines mean:

| Line | Meaning |
|---|---|
| `bams: BAMS 0.9.2  data dir: …` | a start (service restart or update), with the running version |
| `bams.stream: video transcoding encoder: VAAPI` (+ `VAAPI: this driver encodes at a constant QP only`) | the encoder picked at start-up |
| `bams.hls: HLS <sid>: file <id>, <s> s, video copied` | copy-HLS session (video kept, sound converted): HEVC/H.264 with AC3/EAC3/DTS sound |
| `bams.hls: HLS <sid>: file <id>, <s> s, full size, 480p` | conversion session (the sizes offered) |
| `bams.hls: keyframes of file <id>: N in X s` | the first copy-HLS of a file reads every keyframe first (seconds on the NAS; cached afterwards) |
| `bams.stream: ffmpeg: …` (WARNING) | FFmpeg's own stderr: **the actual error** |
| `HLS <sid>: FFmpeg failed (exit code N); retrying without GPU filters` | the all-GPU run failed; a hybrid run follows |
| `HLS <sid>: idle, closed` | the player went away |
| `[matroska,webm …] EBML header parsing failed` (no timestamp) | ffprobe noise during scans about a broken file, harmless |

The player retries a failed stream several times and then falls back (copy-HLS → live remux / conversion), so one
failure shows up as many repeated FFmpeg lines; the first error of the series is the one that counts.

## Look things up (database, read-only)

Open the DB with `?mode=ro` (never write it). The `file <id>` in log lines is `files.id`. Template:

```python
# scratchpad/q.py   → ssh -o BatchMode=yes bams-server python3 - < q.py
import sqlite3, json
con = sqlite3.connect("file:/var/lib/bams/bams.db?mode=ro", uri=True)
print(con.execute("select l.name, l.type, r.path from library_roots r join libraries l on l.id=r.library_id").fetchall())
for fid, root, rel, probe in con.execute(
        "select f.id, r.path, f.rel_path, f.probe from files f join library_roots r on r.id=f.root_id "
        "where f.id = ? or f.rel_path like ? limit 10", (1314, "%Family.Guy.S01E01%")):
    p = json.loads(probe or "{}")
    print(fid, root + "/" + rel)
    print("  ", p.get("container"), p.get("video"), [a.get("codec") for a in p.get("audio") or []])
```

(`files.rel_path` is relative to its root; join `library_roots`. Items: `items` (`kind`, `title`), linked through
`file_items`.) For a whole copy to test against locally: `sqlite3` backup into `/tmp/bams-debug` with python3, `scp`
it to the scratchpad, delete the server copy. Treat the copy as private (accounts, history).

## Reproduce a playback failure

1. **Find the file and what BAMS did:** the log's `HLS … file <id>` line and the FFmpeg errors after it; the file's
   codecs from the DB (above). `stream.plan()` + the player decide the path: AC3/EAC3/DTS sound → copy-HLS; video the
   browser can't decode → conversion (VAAPI here).
2. **Run BAMS's own command builder on the server** against the real file, so the command is exactly what BAMS runs.
   The installed code: `/opt/bams/venv/bin/python` as is. Your patched code: copy the package over first:
   ```bash
   cd /c/Users/Beached/bams/server && tar -cf - --exclude=__pycache__ bams | ssh -o BatchMode=yes bams-server 'rm -rf /tmp/bams-debug && mkdir -p /tmp/bams-debug/src && tar -xf - -C /tmp/bams-debug/src'
   ssh -o BatchMode=yes bams-server 'cd /tmp && PYTHONPATH=/tmp/bams-debug/src /opt/bams/venv/bin/python -' < repro.py
   ssh -o BatchMode=yes bams-server 'rm -rf /tmp/bams-debug'
   ```
   `repro.py` sketch (copy-HLS; for a conversion use `stream.hls_cmd(f, 0, video, out, 0, gpu=True/False)`):
   ```python
   import time, logging; from pathlib import Path
   logging.basicConfig(level=logging.INFO)
   from bams import stream
   f = Path("/mnt/nas/jellyfin-media/shows/…/episode.mp4")          # from the DB query
   out = Path("/tmp/bams-debug/out/0"); out.mkdir(parents=True)
   cmd = stream.hls_copy_cmd(f, 0, 0.0, "HEVC", out, 0, 2)          # (path, segment, seek, video codec, dir, audio, channels)
   p = stream.spawn(cmd, cwd=out); t = time.time()                  # cwd: as hls.Transcodes does
   while time.time() - t < 8 and p.poll() is None: time.sleep(0.5)
   rc = p.poll(); p.kill(); p.wait()
   print("exit" if rc is not None else "still running", rc, sorted(x.name for x in out.iterdir())[:8])
   ```
   Errors print through the `bams.stream: ffmpeg:` logger. Segments per second of wall time tell the speed (4 s each
   for conversions; one per source keyframe for copy-HLS).
3. **Odd paths / "No such file or directory"**: `strace -f -e trace=openat -o /tmp/bams-debug/t.trace ffmpeg …` and grep
   the trace for the path FFmpeg really opened.
4. **GPU encoder**: test the rate-control modes directly (works because `beached` is in `render`):
   ```bash
   ssh -o BatchMode=yes bams-server 'ffmpeg -hide_banner -loglevel error -nostdin -vaapi_device /dev/dri/renderD128 -f lavfi -i color=black:size=256x256:rate=25:duration=0.2 -vf format=nv12,hwupload -frames:v 2 -c:v h264_vaapi -rc_mode CQP -qp 23 -f null - && echo OK'
   ```
   Swap in `-b:v 1500k -maxrate 2500k -bufsize 5000k` (bitrate mode) to compare: on this driver it fails with
   "supported modes: CQP".
5. **Same FFmpeg on this PC**: Docker `ubuntu:24.04` has the server's FFmpeg 6.1.1. `linux-tests.sh` (next to this
   file) installs it and runs pytest in the container on a copy of the repo (repo mounted read-only):
   ```bash
   S=/c/Users/Beached/bams/.claude/skills/bams-server
   MSYS_NO_PATHCONV=1 docker run --rm -v "$(cygpath -w /c/Users/Beached/bams):/src:ro" -v "$(cygpath -w $S):/scripts:ro" ubuntu:24.04 sh /scripts/linux-tests.sh tests/test_stream.py tests/test_hls.py
   ```
   Expected there: `test_encoder_choice_api` fails (Linux-only test artefact, CLAUDE.md); everything else in those
   two files passes. To compare with the last release, run it on `git archive HEAD server | tar -x -C <scratch>`.

## Service and machine

```bash
ssh -o BatchMode=yes bams-server 'systemctl show bams -p ActiveState,ActiveEnterTimestamp,NRestarts,MainPID --no-pager'
ssh -o BatchMode=yes bams-server 'ps -o pid,etime,args -u beached | grep -E "[b]ams serve|[f]fmpeg" | cut -c1-200'   # running conversions
ssh -o BatchMode=yes bams-server 'findmnt /mnt/nas; ls /mnt/nas/jellyfin-media; df -h /var/lib/bams; uptime; free -h'
```

`NRestarts` > 0 or a recent `ActiveEnterTimestamp` the owner didn't cause = a crash: read `journalctl -u bams` around
that time. An empty `findmnt` = the NAS isn't mounted: files show as unavailable (HTTP 410) and scans mark them
missing; the owner remounts it.

## Known failures (symptom → cause)

| Symptom | Cause | Status |
|---|---|---|
| Long wait, then "The converted stream stopped"; log `Failed to open segment '…/init_N.mp4'` | FFmpeg ≤ 6.1 puts the playlist's folder in front of the init file name, even an absolute one | fixed in 0.9.2 (bare name + `cwd`). If it's back, check the version and `hls_copy_cmd`/`_restart` |
| Log `h264_vaapi … Driver does not support any RC mode compatible with selected options (supported modes: CQP)` | Ubuntu's free Intel driver encodes at constant QP only | fixed in 0.9.2 (CQP fallback, `stream._vaapi_cqp`) |
| First play of an episode takes ~8 s | `keyframes of file …` read over the NAS before copy-HLS starts | known, cached per file afterwards |
| "database is locked" / 500 on sign-in | a write transaction held during disk work | see CLAUDE.md pitfall |

Add new ones here when you find them (and a CLAUDE.md pitfall if it's a coding trap).

## Needs the owner (sudo): give them the command

| Task | Command (on the server) |
|---|---|
| Update BAMS | Settings → About → Download, then the `sudo apt install …` command it shows; or `cd /tmp && wget https://github.com/TomSomerville/bams/releases/download/vX.Y.Z/bams_X.Y.Z_all.deb && sudo apt install ./bams_X.Y.Z_all.deb` |
| Restart BAMS | `sudo systemctl restart bams` |
| Change account/port/host | edit `/etc/default/bams`, then `sudo dpkg-reconfigure bams` |
| Intel driver with bitrate modes (optional, untried) | `sudo apt install intel-media-va-driver-non-free` (multiverse), then restart BAMS |
| Remove this access | delete the line ending `claude-bams` from `~/.ssh/authorized_keys` on the server; `sudo gpasswd -d beached render`; on this PC delete `~/.ssh/bams_claude*` and the `bams-server` entry |

A fix in the repo reaches the server only through a release (`deploy/README.md`); the server runs the `.deb`, not
this checkout.
