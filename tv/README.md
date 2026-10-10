# BAMS for Samsung TVs

A Tizen web app (React + TypeScript, built with Vite) that plays your BAMS library on a Samsung smart TV with
the TV remote. Made for Tizen 6.5 (2022 models, e.g. The Frame `QN50LS03BAFXZA`); it should run on Tizen 5+.

- **Finds the server** by asking every address of the TV's network for `/api/hello` on port 8484, or you type it.
- **Signs in** by showing a code (and a QR code) you enter at `http://<server>:8484/link`, or with name + password.
  The TV gets a session token (`Authorization: Bearer`); Settings → Your TVs on the web lists and signs out TVs.
- **Plays most files as they are** with Samsung's AVPlay (MKV, HEVC/HDR, VP9, AV1, AC3/EAC3...). DTS/TrueHD sound
  is converted by the server (video copied, HLS); codecs the TV can't decode (10-bit H.264, DV profile 5) are
  converted fully. Rules: `src/plan.ts`. If a file fails, it retries once with the server converting it.
- Text subtitles are drawn by the app from the server's WebVTT; picture subtitles (PGS/VobSub) are burned in by
  the server. Positions are saved like the web player (every 10 s, on pause, on leaving); Continue Watching,
  up-next countdown.
- Remote: arrows move, OK selects, Back goes back (exits from Home). In the player: ◀ ▶ skip −10 s / +30 s,
  OK or ⏯ pauses, ⏩ ⏪, ⏹, ▲ ▼ show the controls (Sound, Subtitles, Next episode).

Server side: `server/bams/devices.py` (link codes, media tickets), the `/api/hello`, `/api/auth/token`,
`/api/devices…` and `/api/media-ticket` routes in `app.py`, and CORS for the app's origin. Media URLs go through
`/api/t/<ticket>/…` because the TV's player and `<img>` can't send headers.

## Develop in a browser

```bash
cd tv && npm install && npm run dev        # http://localhost:5174, uses <video> + hls.js instead of AVPlay
```

Point it at a BAMS server (a test copy on another port). Arrows, Enter and Escape (= Back) act like the remote.
The browser uses a browser's codec rules (`plan.ts` `BROWSER`), so more files get converted than on the TV.

## Put it on the TV (one-time setup)

1. **Tizen Studio** with its CLI: <https://developer.tizen.org/development/tizen-studio/download> (needs Java 17;
   install to `C:\tizen-studio`). In its **Package Manager** → *Extension SDK*, install **TV Extensions** and
   **Samsung Certificate Extension**.
2. **Developer Mode on the TV:** Apps → press `1` `2` `3` `4` `5` on the remote → Developer mode **On** → Host PC
   IP = this PC's address (e.g. `192.168.1.40`) → OK, then turn the TV off and on.
3. **Connect:** `C:\tizen-studio\tools\sdb.exe connect <TV address>` (the TV shows its address under Settings →
   General → Network → Network Status → IP Settings).
4. **Samsung certificate:** Tizen Studio → Tools → **Certificate Manager** → `+` → **Samsung** → TV → profile name
   **BAMS** → sign in with a Samsung account → it adds the connected TV's DUID to the distributor certificate.
   Without a Samsung certificate made for this TV, the TV refuses to install the app.

## Build, package, install

```bash
cd tv
npm run build                              # tv/dist: one classic script (Tizen loads it from file://)
npm run package -- --install --run         # sign (profile BAMS, or TIZEN_PROFILE), install, start
```

The signed package is `tv/build/BAMS.wgt`. The app shows up under Apps on the TV and stays installed.

**Releases:** the app's `version` in `package.json` follows the server's (`server/bams/config.py`). `npm run package --
--release` also writes `dist/BAMS-SamsungTV-<version>.wgt`, published as its own asset next to the `.exe` and `.deb`
(deploy/README.md). That file is signed for the maintainer's TV; the README's "Samsung TV app" section tells everyone
else how to re-sign it with their own certificate.
