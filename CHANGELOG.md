# Changelog

What changed in each BAMS release. To update, run the newer installer over the old one: it keeps your libraries,
accounts, watch history and settings ([docs/INSTALL.md](docs/INSTALL.md#updating)).

## 0.7.0 (2026-10-10)

More than one BAMS server at a time, server names, and music on the TV.

### New
- **Connect to other BAMS servers.** The web app and the TV app are clients that can show several BAMS servers at
  once, each with an account on that server. On the web: **Settings → Connect to a server** (next to Add library):
  type an IP address or domain name and sign in with an account there. On the TV: **Settings → Other BAMS servers →
  Add a server**: pick it from the network scan (or type it) and link it with a code, like the first one. Their
  libraries appear in the sidebar / menu under the server's name. Each browser and each TV keeps its **own** list
  (one TV can have six servers, another three). Libraries of other servers can be hidden (web and TV) and renamed (web),
  for that browser or TV only. What you watch on another server counts for your account there.
- **Home and Search combine every server.** Continue Watching (most recent first), Recently Added (newest first),
  Top Rated and every genre row mix titles from all your servers; Search looks in all of them. The web and the TV
  show exactly the same rows.
- **Name your server**: **Settings → This server → Server name** (admins). By default it's "*first admin*'s BAM
  Server". It's what TVs and other browsers list it as.
- **Music on the Samsung TV app**: music libraries (Artists, Albums, Playlists), artist and album pages, playlists, a
  music bar with previous / play-pause / next / stop, and the remote's media keys. Music keeps playing while you browse
  and pauses when a video starts. Music is in the TV's Home and Search too.

### Changed
- The TV's "find your server" screen stops looking around the network as soon as you pick or type an address (a typed
  address could time out behind the scan).

Browsers and TVs talk to each server directly: each server must be reachable from them (on your home network it is).
A BAMS page opened over https can't use a server that only has plain http. Update the TV app with the new
`BAMS-SamsungTV-0.7.0.wgt` as in the README.

## 0.6.3 (2026-10-09)

### Changed
- **Samsung TV app: the same Home as the web.** The TV's Home now has exactly the rows of the web's Home, in the order
  and with the rows each person chose in **Settings → Home page** (Continue Watching, Recently Added, each library's
  newest, Top Rated, one row per genre). Change them on the web and the TV follows. Library pages on the TV have the
  genre filter too.
- **TV Settings** says which account the TV uses: what you've watched, where you stopped and Continue Watching belong
  to that account on the server, shared with the web. **Switch account** signs the TV out to link it to someone else.

Watching on a computer and on the TV at the same time with one account works: both are recorded (now covered by a
test). To update the TV app, re-sign and install the new `BAMS-SamsungTV-0.6.3.wgt` as in the README.

## 0.6.2 (2026-10-09)

### Changed
- **Home shows every genre**: the genre rows used to show only your four most common genres, worked out from the 500
  newest titles. Now there's a row for every genre in your libraries (the same ones the library filters offer), most
  common first. **Settings → Home page** lists each genre as its own row, so you can switch genres off and move them
  anywhere. If you had already arranged your rows, the genres take the place of the old "Genres" entry.

## 0.6.1 (2026-10-09)

A Samsung TV app, and updates from inside BAMS.

### New
- **BAMS on Samsung TVs**: an app for Samsung smart TVs, used with the TV remote. It finds BAMS on your network, signs
  in with a code you enter on your phone or computer (or by scanning its QR code), and shows Continue Watching, your
  libraries, search, seasons and episodes. Videos play with the TV's own player: MKV, HEVC/HDR and Dolby Digital
  (AC3/EAC3) sound go to the TV untouched; only DTS/TrueHD sound and video the TV can't decode are converted. Resume,
  skipping, sound tracks, subtitles (with a timing control) and the next-episode countdown work like on the web.
  It's a separate download on the release page (`BAMS-SamsungTV-<version>.wgt`) and installs through the TV's
  Developer Mode: step-by-step instructions (written on a 2022 The Frame) at the bottom of the
  [README](README.md#samsung-tv-app-the-frame).
- **Settings → Your TVs** (every account): link a TV with its code, see your linked TVs, sign one out. The TV's QR code
  opens the new page **/link**.
- **Settings → About:** shows the version you run and the newest release; downloads it (checked against its SHA-256)
  and installs it. Windows runs the installer by itself; on Linux it shows the one `sudo apt install` command.
- **Home:** each library's row shows its newest titles, and a show with new episodes counts as new again; Top Rated and
  the genre rows are a fresh random pick each time.
- **Web player:** subtitle timing buttons (and the G / H keys), remembered per file; when a browser refuses sound
  until you tap, the video plays muted and says so.

### Fixed
- **Continue Watching** no longer drops a show you're half-way through because you opened the next episode for a
  few seconds (or a play failed).

## 0.5.3 (2026-10-08)

Requests from the second test session.

### New
- **Continue Watching:** the picture plays the episode, the show's name opens the show, and the episode line opens
  that episode's season.
- **Next episode button** in the player (⏭). It keeps your place in the episode you leave.
- **"Next episode" countdown 30 seconds before the end**, as if the episode were over: Play now, or let it count down;
  Cancel hides it. Pausing pauses the countdown. Leaving this way marks the episode watched.
- **Skip forward is 30 seconds**, back stays 10 (buttons and the → / ← keys).

### Fixed
- Firefox starting an episode over although its spot was saved: fixed in 0.5.2 (the player had to switch streams as it
  started). Update to this version if you're on 0.5.1 or older.

## 0.5.2 (2026-10-08)

Playback fixes for videos whose sound BAMS converts (AC3/EAC3 "Dolby Digital" to AAC).

### Fixed
- **Picture behind the sound after skipping** (up to a few seconds, until a long pause). It happened whenever the
  player used the live stream instead of HLS: in some browsers, and for episodes the scan hadn't read yet.
- **Resume started the episode over** although the spot was saved, when the player had to switch streams as it
  started.
- **Episodes the scan hadn't reached yet** played without a length (`0:00` at the end of the timeline) and never saved
  where you were. BAMS now reads such a file the moment you open it.
- `bams scan` from the command line stopped with an error.

## 0.5.1 (2026-10-08)

### Fixed
- **Titles that failed to match once stayed unmatched** even after a parser or matcher fix: a scan only tried
  titles it hadn't tried before. Now a scan retries them when it re-read file names (a parser upgrade) and the
  first time after the matching rules change. After 0.5.0, South Park, Parks and Recreation, Andor and Star Trek:
  The Animated Series sat unmatched for that reason; the next scan picks them up.

## 0.5.0 (2026-10-08)

Fixes from the second round of testing: 195 "unrecognized" files in one library, most of them in a nested
Star Trek pack, and shows that BAMS knew by name but couldn't match on TMDB.

### Fixed
- **Packs holding several shows** ("Star.Trek.Megapack/Star.Trek.DS9/S03/…"): the pack was taken as the show, so
  five series were piled into one unmatched title. The show is now the folder right above the season folder, and
  the scene short forms DS9, TNG, TOS, VOY and ENT are spelled out the way TMDB knows them.
- **DVD extras in a season folder** whose file name itself carries the season ("Star.Trek.DS9.S03.Extra10.avi",
  "Season 3/Season 3 Extras/…") were "unrecognized". They're listed under that season, after the episodes.
- **Pack folders that aren't the show's name** ("The Simpsons FIXED -jlw/The Simpsons S28/…",
  "…Sewing Bee Series 1 - 10 - DD/The Great British Sewing Bee - Series 5 (2019)/…"): the deepest folder that names
  the show wins, "Series N" stays out of the title, and a year after the series number no longer splits the show
  per series.
- **Exact titles that failed on TMDB** because a year in an episode's file name ("S07E01.2017") was taken for the
  show's start year (South Park, Parks and Recreation). A near-exact title now matches regardless of the year.
- **Franchise prefixes** ("Star Wars Andor" → TMDB's "Andor") match when TMDB puts that show first.

### When you update
- The next scan re-reads every video file's name once (parser v6). Shows that were wrongly merged split into the
  right shows and are matched again; progress on those episodes starts over.

## 0.4.0 (2026-10-08)

Security settings, a better music library, your own Home page, and the last playback gaps.

### New
- **Settings → Security (admins):** a log of every sign-in (successful or failed, and why) and every lock/unlock;
  after a wrong password the account waits a little longer each time (1, 2, 4, 8… seconds); after 5 wrong passwords
  in a row (you can change the number) the account is locked until an admin unlocks it, in Settings or with
  `bams user unlock NAME`. Admins can also lock and unlock accounts by hand.
- **Allow or block addresses:** a block list, and optionally an allow list so only listed addresses (or ranges) can
  reach BAMS. The computer BAMS runs on is always allowed, and BAMS won't let you block yourself. If you lock
  yourself out anyway, `bams security allow-all` turns the allow list off.
- **Traffic log:** every request to BAMS (who, from where, what, how big), with search, in Settings → Security. It
  keeps up to 10 GB by default (you can change the size and the folder) and deletes the oldest first.
- **Choose your Home page:** Settings → Home page. Turn each row (Continue Watching, Recently Added, each library,
  Top Rated, Genres) and the banner on or off, and drag them into your own order. Per person.
- **Music: CUE sheets.** An album ripped as one big file with a `.cue` sheet now shows as its separate tracks.
- **Music: playlists.** `.m3u`, `.m3u8` and `.pls` files in your music folders appear in a new Playlists tab.
- **Music: gapless playback.** Albums that run from one track into the next play without a pause.
- **Music: lossless conversion.** Settings → Music → *Converted music* can send FLAC instead of a compressed format.
- **Subtitles:** VobSub (`.idx` + `.sub`) subtitle files next to a video can be picked like any other subtitle.
- **Dolby audio pass-through:** if your device can play Dolby Digital (AC3/EAC3) itself, BAMS sends it unchanged
  (Sound menu in the player). If it turns out the device can't, the player switches to AAC by itself.

### Improved
- The same album found twice (for example in two folders) becomes one album once both are identified as the same
  release; a track found in both plays the better file.
- Music details from MusicBrainz are refreshed every few months, and downloaded covers and artist photos with them.
  Your own `cover.jpg` is never replaced.
- A `cover.jpg` you add to an album folder later now replaces the cover BAMS found before.
- Converting video entirely on the GPU now also works with Intel Quick Sync, AMD and Linux VAAPI (before: NVIDIA
  only). If the GPU fails on a video, BAMS remembers and uses the CPU for it next time.
- Videos with non-square pixels (some DVDs) are converted at the right shape.

### Fixed
- A subtitle line already on screen when you started burned-in subtitles part-way through was missing.
- A converted video could rarely fetch a half-written piece and stutter.

### When you update
- The database is upgraded on the first start (a backup is kept). The next music scan re-reads your music library
  once (for CUE sheets, playlists and covers), so it takes longer than usual.

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
