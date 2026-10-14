# BAMS for Fire TV

An Android app for **Fire TV devices on Fire OS 6 or later** (Fire TV Stick 4K / 4K Max / Lite / 3rd gen, the Cube,
TVs with Fire TV built in) that plays your BAMS library with the Fire TV remote. Sticks on Fire OS 5 (the 2nd-gen
stick from 2016 and older) are too old for ExoPlayer's current version.

It isn't a second app to keep in step: it **is the Samsung TV app** (`tv/`), bundled into an APK. The page runs in a
full-screen WebView; Android adds what a web page can't do itself:

- **Video through ExoPlayer** (`Video.kt`), drawn under the see-through page the way Samsung's AVPlay draws under
  it. Unlike Samsung's player, ExoPlayer seeks inside a file it streams, so files the Fire TV decodes play straight
  from `/stream`. Other files go through the server's copy-HLS (in fMP4, which keeps Dolby Vision) or a conversion.
- **What the device decodes** (`Caps.kt`): read from Android's decoders and the audio output, not from a table.
  Fire TV models differ a lot (4K or not, AV1, Dolby Vision, DTS only through an AV receiver), and `tv/src/plan.ts`
  decides from that. Conversions are never taller than the H.264 decoder takes.
- **The remote**: Back, OK and the media keys are passed to the page with the key codes the TV app already uses
  (`MainActivity.kt`); the arrows reach it directly. OK on a text box opens the Fire TV keyboard.
- **Device name and address** (`Bridge.kt`): the name you gave the Fire TV shows in BAMS under Settings → Your TVs;
  its address is used to look for servers on the same network.

The page side is `tv/src/firetv.ts` (the bridge), `ExoEngine` in `tv/src/engine.ts`, and Fire TV branches in
`tv/src/tizen.ts`, `plan.ts`, `screens/Player.tsx` and `screens/Settings.tsx`. `tv/test/firetv.test.ts` tests them
with a fake bridge (`cd tv && npm test`).

**Not for Vega OS.** The Fire TV Stick 4K Select (2025) and the Fire TV Stick HD (2026) run Amazon's Vega OS, which
installs no APKs. They would need a separate app made with Amazon's Vega SDK (React Native; Mac or Linux only).

## Build

Needs Node (for `tv/`), **JDK 17** and the **Android SDK** with platform 35 (Android Studio installs both; the SDK
is found through `ANDROID_HOME`, or the default `%LOCALAPPDATA%\Android\Sdk` / `~/Android/Sdk`).

```bash
cd tv
npm install
npm run build                 # tv/dist: the page
npm run firetv                # firetv/app/build/outputs/apk/debug/app-debug.apk
```

Gradle (8.11.1, through `firetv/gradlew`) copies `tv/dist` into the APK's `assets/www` on every build, so rebuild
`tv/` first after changing the page. The APK's version is `tv/package.json`'s.

To make the launcher icon and banner again after the logo changes: `python firetv/art.py` (needs Pillow).

## Put it on a Fire TV

1. On the Fire TV: **Settings → My Fire TV → Developer Options → ADB debugging: On.** If Developer Options isn't
   there, open **Settings → My Fire TV → About**, highlight the device name and press OK 7 times, then go back.
   (Amazon's [ADB guide](https://developer.amazon.com/docs/fire-tv/connecting-adb-to-device.html).)
2. Its address is under **Settings → My Fire TV → About → Network** (not Settings → Network).
3. On the PC:

   ```bash
   cd tv
   npm run firetv -- --install --run --device 192.168.1.50
   ```

   The first time, the Fire TV asks **"Allow USB debugging?"**: tick *Always allow from this computer* and press OK
   (if `adb` said "failed to authenticate", run the command again after accepting). `FIRETV=<address>` stands in
   for `--device`.

The app shows up under **Your Apps & Channels**. On first start it looks for BAMS servers on the network, then shows
a code to enter at `http://<server>:8484/link` (or sign in with name and password), as on a Samsung TV.

**Debugging:** debug builds let Chrome on the PC inspect the page: `chrome://inspect` → the Fire TV under Remote
Target (with adb connected). `adb logcat -s BAMS` shows the page's console and the app's own messages.

## Release builds

Android only installs an update signed with the same key as the copy already installed. Debug builds are signed with
this PC's debug key (`~/.android/debug.keystore`), so a debug build from another PC won't update one from this PC.
For builds to hand out, make a release key **once** and keep it (losing it means everyone reinstalls and signs in
again):

```bash
keytool -genkeypair -v -keystore C:\Users\<you>\bams-firetv.jks -alias bams -keyalg RSA -keysize 4096 -validity 36500
```

Then create `firetv/keystore.properties` (ignored by git; never commit it or the key):

```properties
storeFile=C:/Users/<you>/bams-firetv.jks
storePassword=<the keystore password>
keyAlias=bams
keyPassword=<the key password>
```

On the Linux PC the key lives next to the phone app's: `/mnt/Data/Sandboxes/Android/bams-firetv.jks`, with
`firetv/keystore.properties` pointing at it (`storeFile=/mnt/Data/Sandboxes/Android/bams-firetv.jks`); build with
`source /mnt/Data/Sandboxes/Android/env.sh` first. Keep the copy on the Windows PC as a backup.

`npm run firetv -- --release` then builds `app-release.apk` and copies it to `dist/BAMS-FireTV-<version>.apk`.
A release build doesn't install over a debug build (or the other way round): `adb uninstall media.bams.firetv`
first (the Fire TV forgets its servers and sign-in).
