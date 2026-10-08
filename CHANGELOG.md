# Changelog

What changed in each BAMS release. To update, run the newer installer over the old one: it keeps your libraries,
accounts, watch history and settings ([docs/INSTALL.md](docs/INSTALL.md#updating)).

## 0.3.0 (2026-10-08)

The rest of the first round of testing.

### New
- **Choose CPU or GPU for converting video:** Settings → Playback → *Convert with*. It lists every encoder that
  works on your server (for example NVIDIA NVENC on the GPU, x264 on the CPU); *Automatic* picks the best one, as
  before. Videos already playing keep what they started with.
- **See how far a scan is, and how much is left:** each library in Settings shows what the scan is doing, "235 of
  586 files (351 left) · 2.2 GB of 5.4 GB · about 4 min left", with a progress bar.
- **Put your libraries in your own order:** drag them in the sidebar (admins: a handle shows when you point at
  one; arrow keys work too), or use the ▲ ▼ buttons on each library in Settings. Everyone sees that order in the
  sidebar, on Home and in Settings. New libraries go to the end.

### Improved
- A long scan saves what it has read as it goes, so stopping the server half-way no longer throws that work away.
- The sidebar updates right away when a library is added, renamed, removed or moved.

### When you update
- The database is upgraded on the first start (a backup is kept). Your libraries keep alphabetical order until you
  move them.

## 0.2.0 (2026-10-08)

Fixes and requests from the first round of testing.

### Fixed
- **"HTTP 500" while a library was scanning.** During a first scan you couldn't sign in or add another library
  until it finished (worst on slow network shares). The scan no longer holds the database while it reads the
  disks. A library added mid-scan waits its turn ("Scan queued") instead of failing.
- **Titles with " - " were cut short.** "Star Trek - Lower Decks" and "Star Trek - Prodigy" both became "Star Trek";
  "Spider-Man - Into the Spider-Verse" became "Spider-Man". They're now separate, complete titles.
- **Season 00 / Specials extras weren't shown.** A file in a season folder without an episode number
  ("Show/Season 00/Behind the Scenes.mkv") is now listed in that season, after the numbered episodes.

### New
- **Unrecognized files can be identified by hand:** Settings → *Unrecognized files* (all libraries), or the
  *Unrecognized* tab on a library's page. Paste a TMDB or IMDb link and the fields fill themselves in, or type the
  show / season / episode (or movie / year): every field suggests what's already in the library as you type. Kept
  across rescans; *Undo* puts a file back. Unrecognized files stay out of the normal library views.
- **Show password** button on every password field, and a **confirm new password** field when changing yours.
- **When a title counts as watched / started** is a setting (Settings → Playback): e.g. started after 10 seconds,
  watched at 95%. Defaults stay 30 seconds and 90%.
- **Hide the "Recently added" banner** at the top of Home (Settings → Accounts; per person, follows you to other devices).
- **Playback speed** in the video player: 0.1x to 3x (slider, presets, `<` and `>` keys).
- **Reorder the music queue** by dragging a track's handle (mouse or touch), or with the arrow keys.

### When you update
- The database is upgraded on the first start (a backup is kept in the data folder, `backups`).
- The next scan re-reads every video file's name once. Shows that were wrongly merged because of a " - " in their
  name split into the right shows and are matched again; progress on those episodes starts over.

## 0.1.0 (2026-10-08)

First release: double-click installers for Windows and Debian / Ubuntu / Linux Mint.
