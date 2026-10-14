# BAMS for Android (phones)

An Android app (Android 8 or later) that is the BAMS web UI, plus **downloads**. You can download movies, episodes,
seasons, whole shows, songs, albums, artists and playlists to the phone (the original files), and play them with no
connection.

- **Online** it shows your server's own web UI in a WebView: the same pages as in a browser. Inside the app those
  pages also show Download buttons, a Downloads item in the menu and a "This phone" section in Settings
  (`web/src/android.ts`, `components/Download.tsx`, `components/PhoneSettings.tsx`). The server only offers them to
  accounts allowed to download: admins always, others when an admin ticks *Can download to the BAMS Android app*
  in Settings → Accounts.
- **Offline**, when no server answers, it opens its own Downloads pages. These are built from the web UI's own
  styles and parts (`web/src/phone/`, `npm run build:app`) and bundled in the APK. They list what's on the phone and
  play it. When the server answers again, a banner offers to go back online.
- **Videos** play in Android's player (Media3 ExoPlayer, `PlayerActivity.kt`) straight from the file, with
  downloaded subtitles. If a file's sound is in a format the phone can't decode (DTS, TrueHD, AC3 on some phones),
  another sound track is used if the file has one. If it has none, the video plays without sound. The Download
  button warns about this before downloading (`Caps.kt` tells the page what the phone decodes).
- **Music** plays in a media session (`MusicService.kt`), so it carries on with the screen off and shows on the lock
  screen and on headphone/Bluetooth buttons.
- **Where you stopped** watching offline is kept and sent to the server the next time it's reached
  (`Progress.kt`).

## How it fits together

| Part | What it does |
|---|---|
| `MainActivity.kt` | WebView (server page or `https://appassets.androidplatform.net/app/…`), finding a server at start, falling back to Downloads when the server's page fails to load, full-screen video, Back, insets |
| `Bridge.kt` | `window.bamsAndroid` (a WebMessageListener, only for the app's servers' addresses and its own pages): `download`, `status`, `remove`, `info`, settings; plus, for its own pages only, `library`, `playVideo`, `musicPlay`, servers |
| `Servers.kt` | servers known by their `/api/hello` `id`, each with every address it was reached at (home LAN and away); tries them in turn |
| `Store.kt` | the catalog (`downloads.json`): *roots* (what was asked for, with the server's manifest) and *files* (each original once, deleted when no root needs it) |
| `DownloadService.kt` | foreground service: one file at a time, resumes with HTTP Range, Wi-Fi only (setting, on by default), pictures and subtitles too |
| `Volumes.kt` | where downloads can go: the app's folder on the phone's storage or an SD card (no permission needed; Android deletes them with the app) |

Server side: `GET /api/items/{id}/download` and `GET /api/playlists/{id}/download` (the manifest: items as the API
shows them, music's queue, files, pictures) and `GET /api/files/{id}/download` (the original file, with Range),
all refused (403) unless the account may download (`users.can_download`, schema v14). `/api/hello` gives the
server's `id`.

Sign-in: for the server whose page is showing, the app uses the WebView's own session cookie. For another server the
web UI is connected to, it uses that server's token.

## Build

Needs Node (for `web/`), **JDK 17** and the **Android SDK** with platform 35. On the Linux PC these live in
`~/sandboxes/Android` (`source ~/sandboxes/Android/env.sh` sets `JAVA_HOME`, `ANDROID_HOME` and
the Gradle cache).

```bash
cd web && npm install && npm run build:app          # web/dist-app: the app's own pages
cd ../android && ./gradlew assembleDebug             # app/build/outputs/apk/debug/app-debug.apk
```

Gradle copies `web/dist-app` into the APK (`assets/app`) on every build, so rebuild it after changing
`web/src/phone/`, `android.ts` or `styles.css`. The pages shown online come from the server: changing those means a
server release (`npm run build` in `web/`). The app's version is `bamsVersion` in `gradle.properties`.

**Emulator** (Android 16): AVD `bams36` in `~/sandboxes/Android/.android/avd`. Start it with
`emulator -avd bams36` (add `-sdcard <img>` to test SD cards). A server on the PC is `10.0.2.2:<port>` from the
emulator. Debug builds can be inspected from Chrome on the PC at `chrome://inspect`.

## Install on a phone

Copy the APK to the phone and open it. Android asks once to allow installing apps from that source (the Files app or
the browser). On first start the app asks for the server's address; then you sign in with your BAMS account as in a
browser. To use the server away from home too, add its other address under Settings → This phone → *Servers and
addresses*.

Android only installs an update signed with the same key as the copy already installed. Debug builds are signed
with the build PC's debug key (`~/sandboxes/Android/.android/debug.keystore` on the Linux PC). A release key
works like the Fire TV app's (`firetv/README.md`, "Release builds"), with `android/keystore.properties`. Never
commit the key or its passwords.
