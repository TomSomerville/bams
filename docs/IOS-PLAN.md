# BAMS for iPad: plan

Draft, 2026-11-05, checked against the Android app's code. Nothing is built yet.

## 1. What it is

An iPad app that is the BAMS web UI, plus what the Android app (0.2.4, `android/`) adds around it:

- **Online:** the server's own web pages.
- **Servers:** a server list where each server can have several addresses (home and away), tried in turn.
- **No server in reach:** its own bundled page instead.
- **Music:** songs play in Apple's own player, so they carry on with the screen locked and show on the lock screen and
  on headphone buttons.
- **Video:** the web player goes full screen from the start.
- **Updates:** the app updates itself from the GitHub releases.

Owner's decisions (2026-11-05):

- **For:** the owner's **iPad Air 2** (A8X chip, 2 GB RAM) on **iPadOS 15.8.8**, the last version it gets.
  **iPad only.**
- **Installed with TrollStore:** permanent, no Apple ID and no paid developer account (§3).
- **No downloads on the iPad.** Everything Android does for downloads is left out: Download buttons, the offline
  pages, the offline players, offline progress, storage settings.
  - The reason: Apple's player can't play most original files (MKV, DTS/TrueHD, AVI…), so iPad downloads would need
    extra work (§9 keeps what was found, in case downloads are wanted later).
  - Streaming isn't affected. The server already converts what the iPad can't play, which is why the web UI plays
    everything in Brave on the iPad.

Rules carried over from the Android app (STATUS.md decisions 10-13):

- **No FFmpeg in the app.** It uses Apple's own frameworks and no third-party libraries, so licensing stays as it is.
- The pages the app bundles are **shared with Android** (`web/src/android.ts`, `web/src/phone/`), so both apps look
  the same.

## 2. Will the web UI work in the app?

Yes, as far as can be checked without the app:

- The owner uses the web UI in **Brave on the iPad: "works perfect"**. Brave on iPadOS is built on WebKit (the same
  WKWebView the app will use), so the pages, video and music already work in that engine.
- **Vite 8 builds for iOS 16.4 by default**, newer than the iPad's iOS 15. A scan of the current bundle (and the
  libraries in it) found nothing iOS 15 lacks. Pinning the build target to iOS 15 (§7) keeps a future change from
  silently breaking the iPad.
- **The web player already handles Apple's player rules:**
  - MediaSource is on in an iPad's web view, so it uses hls.js as in Brave (native HLS where MediaSource is missing).
  - `canDecode()` covers HEVC and Dolby. The iPad Air 2 decodes AC-3/E-AC-3 (Apple's spec), but HEVC only in software.
- **Element full screen is off in an app's web view** unless the app turns it on (iOS 15.4+). The app turns it on so
  older servers' full-screen button works. Newer servers' pages ask the app for full screen instead
  (`videoFullscreen`), as on Android.

## 3. Installing it: TrollStore

TrollStore is an app that permanently installs other apps (IPA files). It relies on an iOS code-signing (CoreTrust) bug
that Apple never fixed on iPadOS 15.8.x. Its installer for 15.8.7–15.8.8, **TrollRestore**, uses a separate
backup-restore bug. The install guide (ios.cfw.guide) lists TrollRestore for the A8X iPads on exactly those versions.

- **No Apple ID, no expiry, no limit on the number of apps.**
- **Updates from inside an app:** TrollStore installs a new version over the old one. It should keep the app's data
  (sign-in, server list); step 3 checks that.
- **One-time setup on 15.8.8, with TrollRestore** (open source, runs on Linux) from the Linux PC, iPad on a USB cable:
  1. Turn **Find My** off on the iPad (it can go back on afterwards).
  2. TrollRestore puts TrollStore's helper in place of the **Tips** app.
  3. Open Tips and install TrollStore.
- **If iPadOS ever rebuilds its app list** (rare), apps from TrollStore stop opening until "Refresh App Registrations"
  is pressed in that helper (Tips).
- **Don't update iPadOS** if Apple ever ships a 15.8.9, until it's known that TrollStore still works on it.
- **Fallback if the setup fails:** SideStore with a free Apple ID. The app then expires every 7 days and SideStore
  renews it over Wi‑Fi. Apple's sign-in changes broke it several times in Sept–Oct 2026.

With TrollStore the app needs **no signing key**: TrollStore signs it on the iPad. So there's nothing like
`bams-android.jks` to guard.

## 4. Building it without a Mac

- **GitHub Actions builds the app** on a macOS runner (free for public repos; this one is public). Workflow
  `.github/workflows/ios-app.yml`, started by hand like the APKs are attached by hand:
  1. `npm ci && npm run build:app` in `web/` (the bundled pages).
  2. Generate the Xcode project from a readable `ios/project.yml` with XcodeGen, so there's no Xcode project file to
     edit in git.
  3. `xcodebuild archive` with signing off.
  4. Ad-hoc signing and zipping into `BAMS-iOS-<v>.ipa`.
  - **Pinned:** the runner image and Xcode version, so a GitHub image update can't change the build. The runners'
    Xcode (26/27) still builds for iOS 15.
  - **With a release tag:** the IPA goes on that release with SHA256SUMS, like the Windows `.exe`. Like an Android-only
    APK, it goes on the **current server release, never a release of its own**: that would become "latest", which the
    server's updater reads.
    - The Windows workflow rewrites SHA256SUMS.txt too, so both workflows share one `concurrency` group and neither
      loses a line.
  - **Without a tag:** a test build. GitHub keeps it as a workflow artifact, which needs a GitHub sign-in and comes
    zipped, so TrollStore can't fetch it itself. `gh run download` brings it to the Linux PC, the PC serves it on the
    home network, and a TrollStore link on the iPad installs it.
- **Day-to-day work:** the pages are the web UI, so most changes are tried in a browser against the sandbox server, as
  for Android. Only the native parts (bridge, music player, start and fallback, update) need a CI build on the iPad.
- **Debugging from Linux:** Safari's Web Inspector needs a Mac.
  - **The page's console and errors** are forwarded to the iPad's log by the app, as Android sends them to logcat.
  - That log is read over USB with `pymobiledevice3` (Python, in a venv in the PC's sandbox folder, like the Android
    tools; TrollRestore uses the same library; `usbmuxd` is already installed).
  - Its web inspector shell can run JavaScript in the page (test builds carry `get-task-allow`, and Web Inspector is on
    in the iPad's Safari settings).
  - Chrome's DevTools only half work with WebKit, so they aren't relied on. `ios-webkit-debug-proxy` isn't packaged for
    Debian 13.
- **Unit tests:** the app's logic (servers and addresses, version compare, the music queue and seek arithmetic) lives in
  a Foundation-only Swift package. `swift test` runs it in CI, and on Linux once a Swift toolchain is in the sandbox
  folder (step 0).
- **Testing:** against the sandbox server on the Linux PC (`BAMS_HOST=0.0.0.0`). The iPad is on the same network
  (owner).

## 5. How the app is put together

- **Language and target:** Swift with UIKit (SwiftUI is limited on iOS 15), deployment target **iOS 15.0**. Swift 5
  language mode: Swift 6 mode turns concurrency mistakes into crashes at run time, and many newer concurrency features
  need iOS 16 or later anyway.
- **Names:** app name **BAMS**, bundle id `media.bams.ios`, user agent tag `BAMS-iOS/<v>`. The version lives in
  `ios/project.yml`; bump it for every IPA given to the owner, as for Android.
- **Size:** about 1,200–1,800 lines of Swift, in `ios/BAMS/`.

**`WebController.swift`** (Android: `MainActivity.kt`), on WKWebView:

- **Start:** finds a server (last one first) and shows its web UI. When none answers, or the server's page fails to
  load, it shows the bundled pages. Cancelled loads (iOS error −999) don't count as failures.
- **Bundled pages:** `bams-app://app/…`, served by a WKURLSchemeHandler with real MIME types, or WebKit refuses the
  module scripts.
- **Fresh history at each switch** between a server and the bundled pages: Android clears it, and WKWebView can't, so
  it gets a new web view. Swiping back and forward then stays within one server's pages.
- **Links:** IMDb/TMDB/Wikipedia open in the iPad's browser. Most are `target="_blank"` (a new-window request in
  WKWebView): the server's own ones (`/help/…`) load in place, the rest go to the browser.
- **Full screen:** the status bar is hidden for full-screen video, and a new page load ends full screen (as on
  Android). Element full screen is on for older servers (§2).
- **Video and music:** page videos pause when the app goes to the background. The app's music pauses when page video
  starts (Android gets this from audio focus), and doesn't restart by itself mid-film.
- **Coming back to the foreground:** the bundled page looks for the server again (Android's `network` event). Network
  changes do the same (NWPathMonitor).
- **Recovery:** the page reloads when its process dies (2 GB of RAM).
- **Debugging:** the page's console goes to the iPad's log.

**`Bridge.swift`** (Android: `Bridge.kt`):

- **Shim:** a WKUserScript injected at **document start**, because `android.ts` reads the bridge once as the page loads.
  It gives the page `window.bamsApp`, with the same message protocol as `bamsAndroid` (`{id, type, …}` →
  `{reply, ok, data/error}`, events `{event, data}`).
- **Features:** the shim also says which features this app version has (`features: ["music", "fullscreen"]`), so the
  page knows straight away and nothing depends on version numbers.
- **Checks:** each message's origin (the app's servers and its own pages only), the main frame, and that `musicStream`
  is given only http(s) addresses (as on Android).

**`Servers.swift`, `Http.swift`** (Android: `Servers.kt`, `Http.kt`): same rules.

- A server is its `/api/hello` id with every address it was reached at. Typed addresses get the same candidates as on
  Android.
- **The sign-in cookie** (WKHTTPCookieStore) is shared between a server's addresses as Android does it: name and value
  with its expiry, without the `Secure` flag. The server sets that flag on https sign-ins; kept, the cookie would never
  reach the plain-http home address.

**`Music.swift`** (Android: `Music.kt`, `MusicService.kt`, `Streams.kt`):

- **Player:** AVQueuePlayer in an AVAudioSession playback session, with Now Playing info and remote commands (lock
  screen, Control Center, headphone/AirPods/Bluetooth buttons).
- **Interruptions:** pauses when headphones come out, and handles calls and Siri.
- **The whole queue is the app's own list,** because AVQueuePlayer drops songs once played. That list serves previous,
  jumping back, move/remove, and the queue sent in the state (the page compares it whole).
- **Songs:**
  - CUE tracks play as stretches of a file.
  - A converted track seeks by starting over at `?t=`.
  - A file Apple's player can't decode falls back to the conversion.
  - Songs arrive as media-ticket links (`/api/t/<ticket>/…`), because the player can't use the web view's cookie.

**`Updater.swift`** (Android: `Updater.kt`):

- Finds the newest `BAMS-iOS-<v>.ipa` across GitHub releases. It's offered once a day, with a button on the bundled
  Servers page. Test builds never offer one, as Android's debug builds don't.
- **The app downloads the IPA itself and checks GitHub's SHA-256,** then hands that same file to TrollStore (Open in…).
  TrollStore's install link would download its own, unchecked copy.

**`AppDelegate.swift`** (Android: `App.kt`): the long-lived parts.

As in the Android app, the page can't be pinch-zoomed, plays media without a tap, and the app's own requests
(`/api/hello`, GitHub) carry the `BAMS-iOS/<v>` user agent.

Info.plist:

- `UIBackgroundModes` `audio`, for music with the screen locked.
- `NSAppTransportSecurity`: `NSAllowsArbitraryLoads` only, because servers are often plain http, also by public name.
  Adding `…InWebContent`, `…ForMedia` or `NSAllowsLocalNetworking` next to it would make iOS ignore it.
- `NSLocalNetworkUsageDescription`, for iPadOS's one-time "find devices on your local network" question. The first
  request to a home server can fail before the person answers, so the start page tries again.
- iPad only, all four orientations, a launch screen (`UILaunchScreen`) and no `UIRequiresFullScreen`, so Split View and
  Slide Over work.

Not ported, because they're for downloads: `Store.kt`, `DownloadService.kt`, `Volumes.kt`, `PlayerActivity.kt`,
`Progress.kt`, `Caps.kt`, and the bridge's `download`, `status`, `remove`, `setLocation`, `setWifiOnly`, `openDownloads`,
`library`, `removeDownload`, `playVideo` and `musicPlay`.

## 6. Feature by feature

| Android app | iPad app |
|---|---|
| The server's own web UI, user agent `BAMS-Android/<v>` | same, `BAMS-iOS/<v>` |
| First start asks for the server's address; several servers, each with several addresses (home LAN, away) tried in turn, the last one first | same |
| "Looking for your server…" at start | same |
| No server answers, or its page stops loading: the offline Downloads pages, with "X can be reached · Go online" (looks again on network changes, on coming back to the app and every 30 s) | a bundled "Can't reach your server" page with the server list, Look again and the same Go online banner, looking again at the same moments |
| Back walks the page's history, which starts fresh at each switch | swipe back/forward within a server's pages; fresh at each switch |
| Signed in through the web view's cookie, shared between a server's addresses | same |
| Bridge only for the app's servers and its own pages | same |
| Download buttons, Downloads in the menu, storage and Wi‑Fi-only settings, offline video and music, offline progress | **not on the iPad (owner)** |
| Settings → This phone: version, "Servers and addresses" | Settings → This iPad: version, "Servers and addresses" |
| IMDb/TMDB/Wikipedia links open in the phone's browser | open in the iPad's default browser; the server's own help pages open in the app |
| Web player full screen from the start, no full-screen button; Back leaves full screen, then the player; a new page ends it | full screen from the start (status bar hidden), no full-screen button; the player's own ← leaves it; a new page ends it. The iPad has no Back key, and it rotates freely (no forced landscape) |
| Page video pauses when the app goes to the background; music plays on | same |
| Page video stops the app's music (audio focus) | same, done by the app |
| Streamed music in the app's own player: lock screen, headphone/Bluetooth buttons, screen off; converted tracks seek; falls back to the conversion; queue move/remove/jump/shuffle/volume/stop | same, with the lock screen, Control Center and AirPods/Bluetooth/headphone buttons |
| Page crash → start over | same |
| Updates itself from GitHub: once-a-day offer, button on the app's own page, SHA-256 check | same, installed through TrollStore |
| Version on the app's own page | same (Servers page) |
| Debug builds: page inspectable from a PC, console in logcat | test builds: console in the iPad's log, JavaScript shell from the Linux PC (§4) |

Something the iPad gets on its own: Split View and Slide Over. AirPlay is not one of them: the web player has no AirPlay
button, and conversions play through hls.js, which WebKit can't send over AirPlay.

## 7. Web changes (they ship in a server release)

The app works with older servers too: their pages don't know `window.bamsApp`, so they behave as in Safari (music
plays in the page, no lock-screen controls). The new behaviour comes with the server release that carries:

- **`web/src/android.ts`** (may be renamed `app.ts`; still no React, router or storage, since it's shared with the
  bundled pages):
  - Finds `window.bamsApp` as well as `bamsAndroid`, and reads `BAMS-iOS/<v>` from the user agent.
  - Splits "in the app" from "can download". `inApp` covers both apps (Theatre mode hidden, Settings section). A new
    `appDownloads` is Android only.
  - `appPlaysMusic` and `appVideoFullscreen` come from the iPad app's `features` list. Android keeps its version gates.
    `appAtLeast` stays Android-only: the iPad's 0.1.x numbers mean nothing next to Android's 0.2.x.
  - The page hands music to the iPad app only once the app says it has the player (step 2). Until then step-1 builds
    keep music in the page.
  - Gives the device's name ("phone"/"iPad") for wording.
- **Components:**
  - `Download.tsx`: its hooks (`useAppInfo`, `useDownloadState`) run before the button decides to show, so they check
    `appDownloads` too. Otherwise every track and episode row would message the iPad app.
  - The Sidebar's Downloads item depends on `appDownloads`.
  - `PhoneSettings.tsx` on the iPad shows the version and "Servers and addresses" only.
  - `pages/Settings.tsx` (two "This phone" headings) uses the device's name.
- **`web/src/phone/`:**
  - An iPad mode: Start, Servers and a new "Can't reach your server" page with the Go online banner.
  - No Downloads/Movies/TV Shows/Music sections, and no `library` call.
  - The update button on the Servers page.
  - Android's pages stay as they are.
- **Build target:** `build.target`/`cssTarget` pinned to include iOS 15, in both `vite.config.ts` and
  `vite.app.config.ts`.
- **Server (Python), probably needed:** songs in formats the iPad can't decode (Ogg/Opus, WMA, APE, DSD…) play through
  the live conversion (`/api/files/{id}/audio?t=`). That is streamed with no Range support, and Apple's player
  generally refuses that. The fix is a variant it accepts: an AAC stream like internet radio, or a short HLS list.
  Step 0 tries both outputs an admin can pick (AAC and FLAC).
- **Docs:** STATUS (work log, decisions), CODEBASE, `ios/README.md` (build, install, TrollStore guide), CLAUDE.md
  pitfalls.

## 8. Steps

Each step ends with something to try on the iPad and the owner's sign-off. Docs are updated as CLAUDE.md asks.

0. **Prove the tool chain (first, small).**
   - **Owner:** install TrollStore with TrollRestore from the Linux PC (Find My off for that). The USB tools and a Swift
     toolchain (for `swift test`) go in the sandbox folder.
   - **CI builds a throwaway test app.** It shows the sandbox server in a WKWebView. It plays songs in Apple's player
     with the screen locked and lock-screen controls, all through media-ticket links as step 2 will use them: an MP3 and
     a FLAC from `/stream`, and converted songs from `/audio` in both AAC and FLAC output.
   - **Install** it with a TrollStore link.
   - **The page's own player too:** the test app loads today's web UI, which doesn't know the app yet, so the page plays
     music itself. WebKit lets audio-only media play on in the background and puts it on the lock screen, but reports
     differ on whether the *next* song can start there.
   - **Settles:** that the install route and the CI build work, that the web UI runs in the app, the Local Network
     question, and the shape of the §7 server change.
   - **Owner's choice afterwards:** if the page's own player covers it fully (lock screen, next song with the screen
     locked, headphone buttons), keep music in the page and drop step 2 for a smaller app. Otherwise use Apple's player,
     as planned and as on Android.
1. **The app online.**
   - Servers (add, several addresses, last first), the Start page, the "Can't reach" page with Go online.
   - The bridge, shared sign-in, links, full screen, fresh history per switch, crash reload, the console in the log, the
     user agent.
   - The §7 web changes, with music still in the page.
   - → BAMS works in the app like in Brave, with full-screen video and the server list.
2. **Music in Apple's player.**
   - Lock screen and remote commands, the app's own queue, CUE tracks, fallback to the conversion, seeking converted
     tracks, pausing for page video, state events.
   - The `music` feature in the shim.
   - The §7 server change for converted music.
3. **Updates and releases.**
   - First the release workflow, so a real IPA is on a release.
   - Then the in-app update: download, SHA-256, hand the file to TrollStore. To try it, build an older version number:
     it finds the real release and installs over itself, keeping the sign-in.
   - `ios/README.md` and the docs.

To test on the iPad:

- Add a server by address, and by name:port; add a second address.
- Start with the server off ("Can't reach"), turn it on (Go online), and leave and come back to the app.
- Sign-in kept after closing the app, and at the other address, including an https one.
- Play a movie: as it is, Dolby remux, and HLS conversion. Full screen, rotate, leave. Music pauses for it.
- Music: an album, lock screen controls, headphones out, seek, next/previous and jumping back, a converted song, a CUE
  album.
- IMDb and help links. Split View.
- The update.

Automated: `swift test`, web/phone `tsc` and builds, TV `tsc` (shared files), server tests for the §7 server change.

## 9. If downloads are wanted later

What this plan found, so it needn't be found again:

- **Apple's player plays** MP4/M4V/MOV with H.264 (HEVC without a hardware decoder on the A8X) and AAC/MP3/ALAC/FLAC/AC-3/
  E-AC-3, and subtitles built into the file.
- **It doesn't play** MKV, AVI, WebM, Ogg, VP9, AV1, MPEG-2, Xvid, DTS, TrueHD, sidecar subtitles or picture subtitles.
- **So the options are:**
  - **A.** The server makes an iPad copy: MP4, video copied, unsupported sound converted, text subtitles built in,
    deleted after the download.
  - **B.** The iPad repackages MKV itself with Apple's AVAssetWriter. No server change, but no DTS/TrueHD sound and no
    AVI/VP9/AV1.
  - **C.** A VLC-based player in the app. That reverses "no FFmpeg in the app".
- **The parts to port:** `Store.kt`, `DownloadService.kt` (a background URLSession), `PlayerActivity.kt`
  (AVPlayerViewController), `Progress.kt`, `Caps.kt`.
- **Background downloads:** a background URLSession carries on while the app is suspended. But swiping the app away
  cancels every transfer, and downloads started while the app is in the background are delayed by the system.

## 10. Risks

- **TrollRestore fails, or Apple ships a 15.8.9 that closes the bug.** Fall back to SideStore. Don't update iPadOS
  before checking.
- **No Simulator and no Safari inspector on Linux.** Native parts are tried on the iPad itself, so each try is a CI
  build (about 5–10 minutes). The pages, most of the app, are tried in a browser as before.
- **iOS 15 WebKit differs a little from Brave's settings.** The app sets autoplay without a tap, inline video and
  element full screen explicitly. Step 0 shows the real thing.
- **2 GB of RAM:** iPadOS may kill the page's process during long use. The app reloads it (Android does the same).
- **Converted music:** probably needs the §7 server change; step 0 shows which variant.
- **How iOS shares sound between the page's video and the app's player** is only known on the device. The rule (music
  pauses for video, never restarts mid-film) is tested in step 2.
