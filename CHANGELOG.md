# Changelog

What changed in each BAMS release. To update, run the newer installer over the old one: it keeps your libraries,
accounts, watch history and settings ([docs/INSTALL.md](docs/INSTALL.md#updating)).

## 0.18.1 (2026-10-15)

### Fixed
- **Subtitles menu in theatre mode**: with several subtitles the selection went down out of sight and the options
  below (Check OpenSubtitles…) couldn't be reached. The list now scrolls. (TV apps: from their next release.)

### Added
- **Remove downloaded subtitles from the player** in theatre mode: press Right on a downloaded subtitle to reach
  **Remove** (whoever downloaded it, or an admin), as on the web.

## 0.18.0 (2026-10-15)

### Added
- **Theatre mode**: BAMS for a PC plugged into a TV, driven by a remote. The same screens as the BAMS TV apps, full
  screen, at `http://<server>:8484/theatre/`, or from the web UI's account menu → **Theatre mode**. Arrows, OK and
  Back move around; typing on a remote's keyboard (or any keyboard) opens Search; the player takes the remote's media
  keys, Space, and Windows Media Center remote buttons; a mouse or air mouse works too. It fits any screen size. Sign
  in once with name and password; the PC is listed under Settings → Your TVs and theatre PCs. To make a PC start in it
  by itself (automatic sign-in, Chrome in kiosk mode), see [docs/THEATRE.md](docs/THEATRE.md); Settings → This browser
  shows the start-up lines with your server's address. Use Chrome or Chromium: Edge's kiosk mode forgets the sign-in.

### Fixed
- After a server update or restart, a TV (or theatre PC) that had only slept showed no pictures and couldn't play
  until it was restarted: it now fetches fresh media access by itself (TV apps: from their next release).

Update the server with the new installer. The TV apps are unchanged (0.15.0).

## 0.17.1 (2026-10-14)

### Added
- **Lock-screen controls for music streamed in the Android app** (app 0.2.1). Music you play from your server in the
  app now plays through the phone's own player: it keeps playing with the screen locked, and shows on the lock screen,
  in the notification shade and on headphone/Bluetooth buttons (play/pause, next, previous, seek), like downloaded
  music already did. Songs the server converts while streaming can be seeked there too. With app 0.2.0 music plays
  as before.

Update the server with the new installer and the phone with `BAMS-Android-0.2.1.apk` (installs over 0.2.0). The
TV apps are unchanged (0.15.0).

## 0.17.0 (2026-10-14)

### Added
- **BAMS for Android (phones), 0.2.0.** An app for Android 8 or later that shows your BAMS server's own pages, plus
  **downloads**: movies, episodes, whole seasons and shows, songs, albums, artists and playlists, as the original
  files, to the phone or an SD card. With no connection the app opens your downloads and plays them (music keeps
  playing with the screen off, with lock-screen controls). Where you stop watching offline is sent to the server the
  next time it's reached. A server can have more than one address (home and away). Install `BAMS-Android-0.2.0.apk`
  from this release (copy it to the phone and open it).
- **Who may download** is set per account: Settings → Accounts → *Can download to the BAMS Android app* (admins
  always can). The web and TV apps still don't download.
- **Your own playlists.** Music → Playlists → **New playlist** (a name and a few words about it). Add a song with the
  small playlist icon on its row, or a whole album or artist with **Add to playlist**. On a playlist's page: drag
  songs into order, take them out, edit, delete. Your playlists are yours alone: other accounts don't see them.
  Playlists imported from playlist files stay as they are and get **Make a copy** to edit one.
- **Quality line.** Under the playing song's title and artist: its format and quality, like *FLAC · 24-bit / 96 kHz*
  or *MP3 · 320 kbps*; a song converted while streaming shows both (*ALAC 24-bit / 96 kHz → AAC 256 kbps*).

### Fixed
- On a phone-sized screen, libraries no longer stack on top of each other in the menu bar at the bottom.

Update the server with the new installer. The TV apps 0.15.0 (playlists and the quality line on the TV) need this
server or later.

## TV apps 0.15.0 (2026-10-14)

### Added
- **Your own playlists on the TV:** a *New playlist* tile in Music → Playlists (the name is typed with the TV's
  keyboard), *Add to playlist* on album and artist pages, and holding OK on a song to add it to one. In your own
  playlist, holding OK on a song moves it up or down or takes it out. *Make a copy* on imported playlists.
- **Quality line** under the playing song on the music bar.

## TV apps 0.14.0 (2026-10-12)

### Added
- **Play Random on the TV** (Samsung and Fire TV): on library, show and artist screens, as on the web (needs a server
  on 0.16.0 or later).
- **Up next on the TV:** in the player while a random selection plays, and from a new queue button on the music bar.
  Each row has ▲ / ▼ to move it and ✕ to take it out; OK on a row plays it.

## 0.16.0 (2026-10-12)

### Added
- **Play Random.** A *Play Random* button on every library page (next to the count), on each show (next to Fix
  match) and on each artist. It plays up to 100 random episodes, movies or tracks from there (Specials left out).
- **Up next for videos.** While a random selection plays, the list button in the player's controls opens *Up next*:
  drag a row by its grip (or use the arrow keys) to reorder, click one to jump to it, **×** to take it out. The player
  goes on to the next video in that list instead of the next episode.
- **Remove from the music queue.** The music queue's rows have a **×** too (not the track that's playing).

Update the server with the new installer, then the TV apps with `BAMS-SamsungTV-0.14.0.wgt` and
`BAMS-FireTV-0.14.0.apk` (TV apps 0.14.0 above), attached to the same 0.16.0 release.

## 0.15.0 (2026-10-12)

### Changed
- **Subtitles are saved next to a video only when you ask.** Downloaded subtitles now stay in BAMS's cache (the
  automatic copy next to every video from 0.14.0 is gone, and so is its setting). To keep one with the video, open
  Subtitles → **Check OpenSubtitles** while playing and press **Download locally** next to it under *Already on this
  video*. It's saved in the video's folder with the video's name: `Chernobyl - S01E02 - Please remain calm.mkv` gets
  `Chernobyl - S01E02 - Please remain calm.srt`. BAMS never overwrites a file there: if that name is taken, it adds
  the language (`….en.srt`). The button then shows the name it was saved as.
- On Linux this still needs the one-time permission shown in Settings → Playback → OpenSubtitles.

Update the server with the new installer. The TV apps are unchanged: `BAMS-SamsungTV-0.13.0.wgt` and
`BAMS-FireTV-0.13.0.apk` from the 0.13.0 release are still current.

## 0.14.0 (2026-10-12)

### New
- **Downloaded subtitles are also saved next to the video**, for example `Episode name.en.srt`, so you keep them
  and other players (Jellyfin, VLC...) find them too. This is on by default; turn it off under **Settings → Playback →
  OpenSubtitles → Copies next to your videos**.
  - It's the only thing BAMS ever writes in your media folders, and it only **adds** subtitle files: it never
    overwrites one that's already there (a second English one becomes `.en.2.srt`), and never renames, changes or
    deletes anything. Removing a subtitle in BAMS leaves its copy; BAMS then lists it as one of the video's own.
  - After you pick a subtitle, the player says where the copy went (or why it couldn't be saved).
  - **Linux:** the BAMS service may only write in its own data folder, so the copies need your permission once.
    Settings → Playback → OpenSubtitles lists your TV and movie folders and shows the one command to run on the
    server (it asks for your password). Until then subtitles still work inside BAMS, just without the copy.
  - Picking a subtitle you downloaded before saves its copy too, so earlier downloads can be copied the same way.

Update the server with the new installer (the database is backed up and upgraded by itself). The TV apps are
unchanged: `BAMS-SamsungTV-0.13.0.wgt` and `BAMS-FireTV-0.13.0.apk` from the 0.13.0 release are still current.

## 0.13.2 (2026-10-12)

### Fixed
- **Signing in to an OpenSubtitles account gave a misleading error** when OpenSubtitles refused the server's API key:
  "didn't accept the API key" appeared under the account's name and password, so it looked like they were wrong.
  OpenSubtitles turns such a server away before it looks at the account at all. The message now says the API key was
  refused and the name and password weren't checked, and tells you to press **Test** next to the key (and paste it
  again from opensubtitles.com → your profile → **API consumers** if that fails too).

Update the server with the new installer. The TV apps are unchanged: `BAMS-SamsungTV-0.13.0.wgt` and
`BAMS-FireTV-0.13.0.apk` from the 0.13.0 release are still current.

## 0.13.1 (2026-10-11)

### Changed
- **Keep in the Unrecognized list now works on files you identified by hand too**, not only on Auto fill's guesses.
  Pressing **Keep** says "this is right": the file leaves the list and stays where it is, across rescans. A kept
  guess is saved as a hand identification.

### Fixed
- **The OpenSubtitles API key box refused real keys** that were long or had dots in them ("That doesn't look like an
  OpenSubtitles API key"). It now accepts anything without spaces and lets OpenSubtitles say whether the key works.
  Pasting an OpenSubtitles sign-in token by mistake (it expires after a day) now says so and points to the page with
  the real API key (opensubtitles.com → your profile → **API consumers**).

Update the server with the new installer. The TV apps are unchanged: `BAMS-SamsungTV-0.13.0.wgt` and
`BAMS-FireTV-0.13.0.apk` from the 0.13.0 release are still current.

## 0.13.0 (2026-10-11)

### New
- **My Watch List.** Keep a list of what you mean to watch: movies, shows, single seasons and single episodes. It's
  in the sidebar right under Home (on the TV, in the menu under Home), and it's also a row on Home after Continue
  Watching (turn it off or move it in **Settings → Home page**).
  - **Add things** with the **+ My Watch List** button on a show's or movie's page, the **(season)** button above a
    season's episodes, or the bookmark beside each episode. Pointing at any poster shows a bookmark too. On the TV, use
    the button on a title's page, or **hold OK** on an episode.
  - **One list for every server.** Titles from every BAMS server you're connected to go on the same list, newest
    first. Each server remembers its own titles for your account, so the list is the same on every browser and TV
    signed in to those servers.
  - Opening an episode from the list takes you to its season with the episode picked out. Watching something doesn't
    take it off; use the bookmark (or hold OK on the TV) when you're done with it.
  - **Rename it** with the pencil next to its name on the list page.

Update the server with the new installer, and install the new TV apps (`BAMS-SamsungTV-0.13.0.wgt`,
`BAMS-FireTV-0.13.0.apk`) to get the watch list on the TV. Other servers you connect to need 0.13.0 too before their
titles can go on the list.

## 0.12.0 (2026-10-11)

### New
- **BAMS on Fire TV.** An app for Fire TV devices on Fire OS 6 or later (Fire TV Stick 4K / 4K Max / Lite / 3rd
  gen, the Cube, TVs with Fire TV built in): `BAMS-FireTV-0.12.0.apk`. It's the Samsung TV app with Android's
  video player underneath: it finds your server, signs in with a code (Settings → Your TVs on the web) and plays
  what the Fire TV decodes straight from the file, the rest through the server. To install it, turn on **ADB
  debugging** on the Fire TV and install the APK from a computer ([firetv/README.md](firetv/README.md)). The Fire
  TV Stick 4K Select (2025) and Fire TV Stick HD (2026) run Vega OS, which can't install it.
- **1080p and 4K in the web player's Quality menu.** The menu now lists sizes up to the video's own size, so a
  1080p video offers 1080p and a 4K video offers 4K (converted by the server). Picking the video's own size is a way
  to play it when the original won't play in your browser. 4K and 1440p are only offered when the server converts
  on a graphics card (it stops at 1080p on the CPU). A size you picked on another video only makes bigger videos
  smaller, so picking 1080p once doesn't convert every 1080p video after it.

Update the server with the new installer. The Samsung TV app (`BAMS-SamsungTV-0.12.0.wgt`) has no changes you'd
notice; installing it keeps the TV's version in step.

## 0.11.1 (2026-10-11)

### Changed
- **Your server's libraries are listed under its name** in the sidebar instead of under "Libraries", the same way
  other servers' libraries are. The name is the one an admin sets in **Settings → This server → Server name**; the
  sidebar shows a new name as soon as it's saved there.
- **Put another server's libraries in any order.** Drag them by the handle that shows when you point at one (or
  focus it and use the arrow keys), like your own server's. The order is kept in this browser, like the names you
  give them, so you don't need to be an admin there and nothing changes for that server's other users.

Update the server with the new installer. The Samsung TV app is unchanged: `BAMS-SamsungTV-0.11.0.wgt` from the
0.11.0 release is still current.

## 0.11.0 (2026-10-11)

### New
- **Remove a title from Continue Watching.** Long-press a card in the Continue Watching row (or right-click it with
  a mouse) and choose **Remove from Continue Watching**; on the Samsung TV app, hold OK on the card. For an episode
  the whole show leaves the row, not just that episode. It comes back by itself as soon as you watch it again
  (opening it for a few seconds doesn't count). Only your own account's row changes.

Update the server with the new installer (the database is backed up and upgraded by itself), and install
`BAMS-SamsungTV-0.11.0.wgt` on the TV for holding OK. Removing needs a 0.11.0 server: on an older one the TV app and
the web page show an error in the menu and the card stays.

## 0.10.0 (2026-10-11)

### New
- **Subtitles from OpenSubtitles.com.** While a movie or episode plays, the subtitles menu has **Check
  OpenSubtitles** (web and Samsung TV app). It lists what OpenSubtitles has for that title in the language you pick,
  the ones made for your exact file first ("made for this file"). Pick one and it shows at once; if it doesn't fit,
  open the list again and try another. A picked subtitle is kept on the server (never in your media folders) and
  offered to everyone who plays that file; whoever downloaded it, or an admin, can remove it again.
  - To turn it on, an admin pastes their own free OpenSubtitles API key under **Settings → Playback →
    OpenSubtitles**, like the TMDB key: sign in at OpenSubtitles.com, open **API consumers** in your profile, create
    one and copy its API key. BAMS checks the key before saving it.
  - Optional: sign in with your OpenSubtitles account in the same place. OpenSubtitles allows 5 downloads a day
    without an account and 20 with a free one (more with VIP). Searching never counts.
- **Sleep mode**: a bed-with-stars button next to the volume button (web) or a **Sleep** button (TV app). On an
  episode it plays this one and 2 more, then stops; on a movie it stops at the end. Press it again to turn it off.
- **Fix match shows where the files are**: the dialog lists the show's folders on the server (with how many files
  each) or the movie's files, so you can check you're fixing the right one.

### Fixed
- **Titles with a hyphen were cut at the hyphen**: a show in a folder named `Catch-22` was identified as "Catch",
  and names like `Ant-Man.2015.1080p.mkv`, `Spider-Man.Far.From.Home…` or `Obi-Wan.Kenobi.S01…` lost the part
  before the dash ("She-Ra and the Princesses of Power" became "She"). This happened on Windows and Linux alike. The
  next scan after updating reads every file name again, so affected titles are fixed by themselves.

Update the server with the new installer (the database is backed up and upgraded by itself). The Samsung TV app has
a new version too: install `BAMS-SamsungTV-0.10.0.wgt` for sleep mode and OpenSubtitles on the TV.

## 0.9.2 (2026-10-10)

### Fixed
- **Videos that need converting didn't play on Debian/Ubuntu servers** (for example HEVC episodes with AC3 sound):
  after a long wait the player said "The converted stream stopped". Two causes:
  - Converting only the sound failed with the FFmpeg that Ubuntu 24.04 and Debian ship (6.1 and older): it wrote
    one of its files to a folder that doesn't exist.
  - On Intel graphics with Ubuntu's standard driver, converting the picture on the GPU failed every time: that
    driver encodes at a constant quality only and refused BAMS's bitrate settings. BAMS now tests the encoder with
    the settings it really uses and switches to constant quality when that's all the driver offers.

### Changed
- **Files can't be downloaded from BAMS any more.** The Download buttons are gone (title page, player, the player's
  error message), and so is the download link in the server's API. Files are only streamed for playing.

Update the server with the new installer. The Samsung TV app is unchanged: `BAMS-SamsungTV-0.8.0.wgt` from the 0.8.0
release is still current.

## 0.9.1 (2026-10-10)

### New
- **Best guess** button in the identify form (next to "Fill in"): fills the fields from the file's folders and name.
  It also works on files Auto fill leaves alone, like a movie in its own folder in a TV library. Nothing is saved
  until you press Save.

### Changed
- **Movies and specials of a show** stored in the show's folder go to that show's **Specials (Season 00)**, also
  when the film has its own subfolder: `Daria Complete Series/Daria Is It College Yet 2002 …/…avi` is now a Daria
  special instead of unrecognised. "Complete Series", "Complete Collection" and "Box Set" are dropped from guessed
  show names, so these join the show you already have.
- Guessed episode titles are tidier: leading tags like "(En_Jp)" are dropped and " _ " reads as " - ".

Update the server with the new installer; the first scan re-guesses files that couldn't be placed. The Samsung TV
app is unchanged (0.8.0).

## 0.9.0 (2026-10-10)

Auto fill: files BAMS couldn't identify from their names are now placed by a best guess.

### New
- **Auto fill** (Settings → Unrecognized files, on by default). When a file's name doesn't follow the naming rules,
  BAMS guesses from its folders and name and puts it in the library anyway: the show from the folder, the season
  from "Season", "Volume" or "Level" folders, the episode number from names like "Part 3", "Lesson 12" or
  "01 - Name", and files with no number become extras of the show. A film sitting in its show's folder goes to
  Specials. A movie in its own folder in a TV library is still flagged instead (it belongs in a Movies library).
- **Review the guesses** in the Unrecognized list (Settings, or a library's Unrecognized tab): each guessed file shows
  what BAMS made of it, with **Keep** (lock it in), **Change** (fix it by hand) and **Don't place** (leave it out of
  the library). Library cards say how many files were placed by a guess.
- Turning Auto fill off takes every guess out at once; what you kept or identified by hand stays.

Update the server with the new installer. Files that were unrecognised are guessed on the first scan after the update.
The Samsung TV app is unchanged (0.8.0 still works).

## 0.8.0 (2026-10-10)

Safer accounts: people pick their own passwords, and two-step sign-in with an authenticator app.

### New
- **"Must change password at next sign-in"** for each account (Settings → Accounts, admins). It's ticked by default
  when you add an account or set a new password for someone, so you can hand out a temporary password and they pick
  their own when they first sign in. Until they do, BAMS shows them only that. Ticking it later signs them out.
  The TV can't ask for a new password: it tells them to sign in in a web browser first.
- **Two-step sign-in** (Settings → Your account → Two-step sign-in): scan the QR code with Google Authenticator (or
  any authenticator app), and from then on signing in asks for the app's 6-digit code after your password. Works on
  the web, on the TV's name-and-password sign-in and when connecting from another BAMS server. A wrong code counts
  like a wrong password (waits, lockout); each code works once.
- **Lost phone?** An admin can turn someone's two-step sign-in off in Settings → Accounts; on the server,
  `bams user 2fa-off NAME` does it too. New: `bams user add|passwd NAME --must-change`.
- The sign-in log shows two-step sign-in being turned on or off, and wrong codes.

Update the server with the new installer; the database gets three new account columns when it starts (a backup is
taken first). Update the TV app with `BAMS-SamsungTV-0.8.0.wgt` for the code box on its sign-in screen.

## 0.7.1 (2026-10-10)

Getting around the Samsung TV app with the remote.

### Fixed
- **The cursor could get stuck in the menu on the left.** Right from the menu now goes back to where you were on the
  page (before, from Home next to the big banner, or from Settings beside a short page, it went nowhere).
- **Home starts with a poster selected.** Before, nothing was selected until the rows had loaded, and the first
  arrow press dropped you into the menu. Coming back to a screen puts the cursor back where it was.
- **Up/Down no longer jump between the page and the menu**: only Left goes into the menu, and Up/Down stay in it.
- An arrow press after the selected item disappeared (a list reloading) picks up on the page, not in the menu.
- A long menu (many libraries) scrolls to show the selected item.
- Left/Right on the music bar stay on the bar; posters behind the bar scroll up above it when selected.
- A title opened from a library keeps that library lit in the menu, and Left lands on it.
- **The play bar hides 5 seconds after your last button press** once the video plays. Before, if the video was
  still starting (or restarting after a skip) at that moment, the bar stayed up until you pressed something.

Update the TV app with the new `BAMS-SamsungTV-0.7.1.wgt` as in the README. The server is unchanged apart from the
version number.

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
