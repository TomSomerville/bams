# Security and privacy practices for the repo

**Read this before every commit.** The BAMS repo may be public. Anything committed is published: it stays in the
history, in clones, forks and caches, even after it's deleted from the files. Removing it later means rewriting the
history of every clone (done once, 2026-10-19). So the rule is simple: **personal or security-sensitive content never
goes into git**, not in code, tests, docs, commit messages, file names or images.

## Never commit

| Kind | Examples (made up) | Use instead |
|---|---|---|
| People's names, emails, account names | a real first/last name, `someone@example.com`, the OS login name, a Linux user | "the owner", "a tester", `<you>`; GitHub handle only where the repo URL needs it |
| Real IP addresses, hostnames, computer names | the owner's server, PC, NAS, TV, Fire TV addresses; `DESKTOP-…`; the server's hostname | made-up examples listed in `tools/privacy_check.py` `EXAMPLE_IPS` (`192.168.1.20`, `192.168.1.150`, …) |
| Machine-specific paths | `C:\Users\<name>\…`, `/home/<name>`, `/mnt/<disk>/…`, scratchpad/session paths, NAS shares | relative paths, `data/`, `<path>`, `~/…`, or "the owner's test folder" |
| Access details | SSH aliases/keys/users for the owner's machines, which account has sudo, ports opened on a real machine | `CLAUDE.local.md` |
| Secrets and signing material | API keys (TMDB, OpenSubtitles), passwords, tokens, `.jks`/`.keystore`/`.p12`/`.pem`/`.pwd`, `keystore.properties`, where those files live | the owner keeps them; docs say "location in `CLAUDE.local.md`" |
| Exact device identifiers | full TV model/region code, DUID, serial numbers, MAC addresses | the model family ("2022 The Frame") |
| Logs and debug output from real machines | `bams.log`, `netflow/*.jsonl`, journal lines, DB rows, timestamps of the owner's sessions, account tiers | describe the finding in your own words, with made-up names |
| The owner's media library | real file/folder names, release groups, rip sources of the owner's files | invented names with the same shape (`Show.S01E01.1080p.WEB-DL.x264-GRP.mkv`); parser cases stay realistic, groups are fake |
| Screenshots and images | anything showing another app, a desktop, a browser with tabs/bookmarks, account pages, the owner's library | screenshots of BAMS itself with test data only; check every pixel (title bars, URLs, names) |
| Other private projects | names, paths or code from the owner's other projects | "a local tool" |
| Local tooling files | `CLAUDE.local.md`, `.privacy-patterns`, `.claude/launch.json`, `.claude/skills/`, `.claude/settings.local.json`, `data/` | they're git-ignored: keep them so |

## Where personal details go

- **`CLAUDE.local.md`** (repo root, git-ignored, loaded by Claude Code next to CLAUDE.md): the owner's machines,
  addresses, accounts, SSH access, key and certificate locations, test media folders. Each machine keeps its own copy;
  a fresh clone doesn't have one (ask the owner).
- **`.claude/skills/`** and **`.claude/launch.json`**: local only (git-ignored). Skills that reach the owner's machines
  stay out of git.
- **`.privacy-patterns`** (git-ignored): the owner's real names, addresses, paths and library names, one per line;
  `tools/privacy_check.py` refuses any commit containing one. Add to it when a new personal detail turns up.

## Before every commit

1. Review the staged diff (`git diff --cached`) against the table above, including commit messages, new file names
   and every image.
2. Run the check: `server\.venv\Scripts\python tools\privacy_check.py` (Linux: `server/.venv/bin/python`); it must
   pass. It runs by itself as the pre-commit hook once `git config core.hooksPath .githooks` is set in the clone (it
   is on the owner's Windows PC; set it on every other clone). `--all` checks every tracked file. A reviewed, made-up
   value it still flags (a fake token in a test) gets the comment `privacy-check: ok` on its line.
3. Commit as the GitHub no-reply address (`git config user.email <id>+<handle>@users.noreply.github.com`); the check
   refuses a personal email.
4. When in doubt, leave it out and ask the owner. Never "temporarily" commit something sensitive.

## Be security-conscious in general

- Treat everything from the owner's machines (logs, DB rows, file names, traffic logs) as private: read it to debug,
  never paste it into tracked files, issues, PRs or release notes.
- Never handle the owner's API keys or passwords yourself (CLAUDE.md rule 4).
- Don't widen what BAMS exposes (new public routes, CORS, listening addresses, file access) without the owner's OK.
- Prefer safe defaults: least privilege, read-only where possible, no secrets in URLs or logs.
- If something sensitive was committed: stop, tell the owner, and don't push. If it was pushed, it needs a history
  rewrite (`git filter-repo`) and a force push, and any exposed secret must be rotated.
