# Theatre mode: BAMS on a PC at a TV

Theatre mode turns a small PC plugged into a TV into a BAMS box you drive with a remote: the same screens as the BAMS
TV apps, full screen, with the arrows, OK and Back. A USB remote with a keyboard types searches. It's BAMS's TV page,
served by your BAMS server at:

    http://<server address>:8484/theatre/

Open it from BAMS in any browser (account menu → **Theatre mode**), or set a PC up to start in it (below).

## Using it

- **Arrows** move, **OK/Enter** selects, **Back** goes back (Escape, Backspace and a remote's Back key all work).
  Holding OK on a card, or the remote's **Menu** key, opens its menu (e.g. remove from Continue Watching).
- **Searching:** start typing anywhere and Search opens with what you typed; Enter jumps to the results.
- **In the player:** ◀ ▶ skip back 10 s / ahead 30 s, OK or Space pauses, ▲ ▼ show the controls (Sound,
  Subtitles, Next episode, Up next, Sleep); Up once more reaches the back arrow at the top left, which leaves the
  player. The remote's media keys work, and so do Windows Media Center remotes.
- **Home** on the remote goes to Home. A mouse or air mouse works too: the pointer shows while it moves.
- **Settings → This browser → Test the remote** shows what each button sends and what BAMS does with it. If a
  button does nothing, tell us its name.
- The first time, sign in with name and password on the remote's keyboard (if the browser is already signed in to
  BAMS's web pages, it also offers that account). A household viewer account is enough. The PC stays signed in, and
  shows under Settings → Your TVs and theatre PCs on the web, where you can sign it out.

**What plays as it is** depends on the browser. Chrome on Windows usually decodes HEVC; Edge decodes Dolby
Digital/Plus; Chrome and Firefox on Linux decode neither. Everything else the server converts, as for the web player:
sound only (cheap) or the whole video (busier). Sound reaches the TV or receiver as stereo or 5.1 PCM, never as a
Dolby/DTS bitstream, and DTS/TrueHD are always converted.

## Setting up a theatre PC

### 1. The PC signs in by itself

- **Linux Mint:** Menu → Login Window → Users → *Automatic login* → your user. (Ubuntu: Settings → Users →
  Automatic Login.)
- **Windows:** `netplwiz` → untick *Users must enter a user name and password* (or Sysinternals Autologon).

### 2. No lock screen, and the remote can wake it

- No password when the screen blanks or the PC wakes. Mint: System Settings → Screensaver → turn off *Lock the
  computer…*. Windows: Settings → Accounts → Sign-in options → *If you've been away…* → **Never**.
- The screen may turn off when idle; the browser keeps it on while a video plays.
- If the PC sleeps, let the remote's USB receiver wake it. Windows: Device Manager → the receiver (under Keyboards
  or Mice) → Power Management → *Allow this device to wake the computer*. Linux: enable the receiver's
  `power/wakeup` (a udev rule).
- To sleep it from the remote, set the OS's power-button action to *Suspend*/*Sleep* and use the remote's Power key.
- Windows: turn off the "finish setting up your device" and tips screens (Settings → System → Notifications →
  Additional settings), or they cover BAMS after an update.

### 3. BAMS starts at sign-in, full screen

Use a **Chrome or Chromium** browser in **kiosk mode, with a profile of its own**, so it keeps its BAMS sign-in.
Don't use Edge's `--kiosk`: it always runs a private (InPrivate) window, so it would forget the sign-in at every
start. Use the server's **IP address**, not its name.

BAMS shows these lines with your server's address filled in: on a computer, Settings → This browser → Theatre mode →
*Make a PC start it by itself*. They wait for the server first, so a PC that boots faster than the server doesn't
get stuck on an error page.

**Linux Mint / Ubuntu / Debian.** Save as `~/.local/bin/bams-theatre` and `chmod +x` it:

```sh
#!/bin/sh
until python3 -c "import urllib.request; urllib.request.urlopen('http://SERVER:8484/api/hello', timeout=3)" 2>/dev/null; do sleep 3; done
for b in google-chrome chromium chromium-browser; do command -v $b >/dev/null && break; done
exec $b --kiosk --user-data-dir="$HOME/.config/bams-theatre" --password-store=basic --no-first-run \
  --noerrdialogs --autoplay-policy=no-user-gesture-required http://SERVER:8484/theatre/
```

and as `~/.config/autostart/bams-theatre.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=BAMS Theatre
Exec=sh -c "$HOME/.local/bin/bams-theatre"
```

(`--password-store=basic` keeps Chrome from asking to unlock the keyring, which automatic sign-in leaves locked.)

**Windows.** Save as `%USERPROFILE%\bams-theatre.ps1`:

```powershell
while ($true) { try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 'http://SERVER:8484/api/hello' | Out-Null; break } catch { Start-Sleep 3 } }
& "$env:ProgramFiles\Google\Chrome\Application\chrome.exe" --kiosk --user-data-dir="$env:LOCALAPPDATA\BAMS-Theatre" `
  --no-first-run --noerrdialogs --autoplay-policy=no-user-gesture-required 'http://SERVER:8484/theatre/'
```

then make a shortcut in the Startup folder (Win+R → `shell:startup`) with *Run: Minimized* and the target:

    powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%USERPROFILE%\bams-theatre.ps1"

To leave kiosk mode for maintenance, press Alt+F4 (it starts again at the next sign-in).

## How it works

The page is the TV app (`tv/`), built once and served by the server at `/theatre/` (`server/bams/app.py`,
`TheatreFiles`); on a PC it scales to any window, maps PC and remote keys (`tv/src/pckeys.ts`), handles the mouse
(`pointer.ts`) and asks the browser what it decodes (`plan.ts`). It keeps its own storage apart from the web UI on
the same address, and signs in with its own token, never the web UI's cookie (`tv/src/platform.ts`, `api.ts`).
