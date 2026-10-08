# Installing BAMS

One file to download, double-click, done. Updates are the same: run the newer installer over the old one.
Your libraries, accounts, watch history and settings stay as they are.

| | Windows 10 (1809+) / 11, 64-bit | Debian 12+, Ubuntu 24.04+, Linux Mint 22+ |
|---|---|---|
| File | `BAMS-Setup-<version>.exe` | `bams_<version>_all.deb` |
| Runs as | a Windows service (starts with the computer, no sign-in needed) | a systemd service, as your own account |
| Address | http://localhost:8484 | http://localhost:8484 |
| Your data | `C:\ProgramData\BAMS` | `/var/lib/bams` |
| FFmpeg | downloaded by the installer from its publisher (about 96 MB) | installed by apt (`ffmpeg`) |

## Windows

1. Double-click `BAMS-Setup-<version>.exe`.
   - Windows may show **"Windows protected your PC"** because the installer isn't code-signed. Click
     **More info**, then **Run anyway**.
   - Click **Yes** when Windows asks to allow changes (BAMS installs a service).
2. Choose:
   - **Let other devices on my home network watch BAMS**: on by default. Opens port 8484 in Windows Firewall for
     *private* networks only. Turn it off if only this computer should use BAMS.
   - **Desktop shortcut**.
3. Click **Install**. The installer downloads FFmpeg (BAMS uses it to read and convert video), installs everything,
   starts BAMS and waits until it answers.
4. Leave **Open BAMS now** ticked and click **Finish**. Then [set it up](#first-steps).

The Start menu gets **BAMS** (opens it in your browser) and **BAMS - How to get a TMDB key**.

**Other devices** open `http://<computer-name>:8484` (the installer's last page shows the exact address). If they
can't connect, check that Windows calls your home network *Private* (Settings → Network & internet → your network →
Network profile type).

**Network drives (NAS):** the BAMS service runs as the computer, not as you, so it doesn't see drive letters you
mapped (like `Z:`). Add the folder by its network path instead, e.g. `\\NAS\Videos`. The share has to allow
this computer to read it (guest/everyone read access, the usual setting for a media share).

## Debian / Ubuntu / Linux Mint

1. Double-click `bams_<version>_all.deb`. Your software installer (Software Manager, GDebi, App Center) opens:
   click **Install** and enter your password. It installs Python and FFmpeg for you if they're missing.
   From a terminal instead:
   ```bash
   sudo apt install ./bams_0.2.0_all.deb      # the file name you downloaded
   ```
2. Open **BAMS** from the applications menu (or http://localhost:8484) and [set it up](#first-steps).

BAMS runs in the background as **your** account (the one that installed it), so it can read every folder you can,
including your home folder and USB drives. It can never change them: systemd makes the whole disk read-only to
BAMS except its own data folder. Other devices on your network can reach it at `http://<computer-name>:8484`; if
the firewall (ufw) is on, the installer opened port 8484.

Settings live in `/etc/default/bams` (which account BAMS runs as, the address and port). After changing it run
`sudo dpkg-reconfigure bams`. Updates never overwrite that file.

## First steps

1. **Create the admin account.** The first visit asks for a name and password. This only works in a browser **on
   the BAMS computer itself** (so nobody else on the network can claim it).
2. **Add your TMDB key.** BAMS shows an orange bar until you do. TMDB is where posters and descriptions come from; it's
   free, and the step-by-step guide with pictures is built into BAMS: click the bar, or open
   http://localhost:8484/help/tmdb.html.
3. **Add your folders.** Settings → Add library: pick TV Shows, Movies or Music, then the folder. BAMS scans it right
   away and again every few hours.
4. **Add people.** Settings → Accounts. Everyone gets their own sign-in, watch history and Continue Watching.
5. **Check for files BAMS couldn't identify.** Settings → *Unrecognized files* (or the *Unrecognized* tab on a
   library) lists files whose names didn't say what they are. Paste a TMDB or IMDb link for each, or type the show,
   season and episode (the fields suggest what's already there). Better still, rename them
   (`Show Name/Season 01/Show Name - S01E01.mkv`, `Movie Name (Year)/Movie Name (Year).mkv`).

## Updating

Download the newer installer and run it, exactly like the first time. On Windows it skips the questions (it
remembers your choices) and shows **Install**; on Linux the software installer says **Upgrade**. BAMS stops for a
few seconds, updates, and starts again. If the database needs changes, BAMS makes them on its first start and
keeps a backup in its data folder (`backups`). What's new: [CHANGELOG.md](../CHANGELOG.md).

## Uninstalling

- **Windows:** Settings → Apps → BAMS → Uninstall. It asks whether to delete BAMS's own data as well (default: keep
  it, so a reinstall picks up where you left off).
- **Linux:** `sudo apt remove bams` keeps your data and settings; `sudo apt purge bams` deletes them too.

Your media files are never touched by BAMS, installing, updating or uninstalling.

## Trouble

| Problem | Fix |
|---|---|
| Forgot the admin password | Windows: open *Command Prompt as administrator* and run `"C:\Program Files\BAMS\bams.cmd" user passwd NAME`. Linux: `sudo bams user passwd NAME` |
| BAMS doesn't open after a restart | Windows: Services → **BAMS Media Server** → Start. Linux: `sudo systemctl restart bams`. Logs: `C:\ProgramData\BAMS\logs` / `journalctl -u bams` |
| Videos have no picture or sound | FFmpeg is missing (Settings shows a warning). Windows: run the installer again while online. Linux: `sudo apt install ffmpeg` |
| A show, episode or movie is missing | Its file name probably didn't say what it is: Settings → *Unrecognized files* lists those, with a hint and an *Identify* button |
| Another program already uses port 8484 | BAMS can't start while it does. Windows: stop that program. Linux: change `BAMS_PORT` in `/etc/default/bams`, then `sudo dpkg-reconfigure bams` |
