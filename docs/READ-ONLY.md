# Media folders are read-only to BAMS

BAMS only ever **reads** the folders you add as Movies / TV Shows / Music libraries. It never
renames, moves, deletes, re-tags or touches them, and never drops artwork, `.nfo` or thumbnail
files next to your media. Everything BAMS learns goes into its own data folder.

**One exception (since 0.14.0, the owner's decision):** a subtitle you download from OpenSubtitles while playing is
also saved next to its video as a **new** `.srt` file (`Episode name.en.srt`), so other players find it too. BAMS
only ever *adds* such files: it never overwrites one that's there (it picks `.en.2.srt` instead), and never renames,
changes or deletes anything. It's a setting (Settings → Playback → OpenSubtitles → Copies next to your videos), on by
default; turn it off and BAMS writes nothing in media folders at all. The OS still decides (below).

BAMS's own data folder:

| OS | Data folder (default) |
|---|---|
| Windows (installed) | `C:\ProgramData\BAMS` |
| Windows (from source) | `%LOCALAPPDATA%\BAMS` (or `BAMS_DATA_DIR`) |
| Linux (service) | `/var/lib/bams` |
| Linux (user) | `~/.local/share/bams` |

## Three layers of enforcement

1. **Code.** All media access goes through `server/bams/readonly.py`, which only opens files
   read-only. Scanning reads directory listings, file sizes and dates, and the first and last
   64 KB of each new file (a fingerprint used to spot moved files).
2. **In-process guard.** At startup BAMS installs a Python audit hook that **refuses** any
   write-type operation inside a media folder, whoever in the process attempts it: open for
   write/append, create, delete, rename, mkdir/rmdir, chmod/chown, timestamp changes, copies,
   creating databases. The hook can't be removed once installed. Its only opening is the subtitle copy above:
   `readonly.create_sidecar` creates one new `.srt` in the video's folder ("exclusive create": it fails rather than
   open a file that exists), and only that call, on that thread, for that one path, gets through. `server/tests/test_readonly.py`
   attempts each of these and checks that every attempt fails and the folder stays byte-for-byte
   identical after a full scan.
3. **The operating system.** This is the real wall. Run BAMS as an account that only *has*
   read permission on the media. Layers 1 and 2 make sure BAMS never even tries to write.

BAMS also refuses library folders that contain its data folder (or vice versa), and folders that
overlap another library.

## Setting up OS-level read-only access

### Linux (Debian / Ubuntu / Mint)

The shipped unit [`deploy/linux/bams.service`](../deploy/linux/bams.service) runs with
`ProtectSystem=strict` and `ProtectHome=read-only`. **The kernel makes every path read-only to BAMS
except `/var/lib/bams`**, regardless of file permissions.

The `.deb` runs the service as the account that installed it (`BAMS_USER` in `/etc/default/bams`), so it can
*read* whatever that person can (home folder, USB drives) without any setup, and still can't write anywhere but its
data folder. Tested: `touch /home/<user>/x` inside the service fails with "Read-only file system".

If you run it as a dedicated `bams` account instead (`BAMS_USER=bams`, then `sudo dpkg-reconfigure bams`), grant
that account *read*:

```bash
# local disk / bind mount
sudo setfacl -R -m u:bams:rX /mnt/media
sudo setfacl -R -d -m u:bams:rX /mnt/media     # default ACL, so new files are readable too
```

Network shares: mount them read-only in `/etc/fstab`:

```
//nas/media  /mnt/media  cifs  ro,credentials=/etc/bams-smb,uid=bams,gid=bams,iocharset=utf8,_netdev  0 0
nas:/media   /mnt/media  nfs   ro,_netdev  0 0
```

Check: `sudo -u bams touch /mnt/media/x` must fail.

**Allowing subtitle copies (Linux service).** The sandbox above also stops the subtitle copies. To allow them in your
TV and movie folders only, add them to the service's writable paths. Settings → Playback → OpenSubtitles shows this
command with your folders filled in:

```bash
sudo mkdir -p /etc/systemd/system/bams.service.d && printf '%s\n' '[Service]' 'ReadWritePaths=-/mnt/media/TV -/mnt/media/Movies' | sudo tee /etc/systemd/system/bams.service.d/20-subtitles.conf && sudo systemctl daemon-reload && sudo systemctl restart bams
```

(`-`: a folder that's missing at start-up, like an unmounted drive, doesn't stop the service.) The account BAMS runs as
also needs write permission there, and a share mounted `ro` stays read-only whatever systemd allows. Updates keep the
file; `sudo rm /etc/systemd/system/bams.service.d/20-subtitles.conf` and a restart take the permission away again.

### Windows

The installer runs BAMS as the `BAMS` service under **LocalSystem** (owner decision, 2026-10-08: starts at boot
without anyone signing in). LocalSystem can read local drives and every user's folders, so on Windows the read-only
guarantee comes from layers 1 and 2. For an OS-level wall as well, change the service's account (services.msc →
BAMS Media Server → Log On) to a local user that has only **Read & execute** on the media:

```powershell
icacls "D:\Media" /grant "bams-reader:(OI)(CI)RX"
icacls "C:\ProgramData\BAMS" /grant "bams-reader:(OI)(CI)M"   # its own data folder (SYSTEM + admins only by default)
```

Network shares: use a share account whose **share permission** is Read, and add the library by
UNC path (`\\nas\media\TV`), because a service can't see drive letters mapped in your user session.

Check: as that account, creating a file in the media folder must fail with "Access is denied".

Subtitle copies on Windows: under LocalSystem they just work. Under a read-only account they fail ("isn't allowed to
write in that folder" in the player and Settings); grant that account **Write** (not Modify) on the folders where you
want them, or turn the setting off.

## What BAMS reports

`GET /api/libraries` shows, per folder: `exists`, `readable`, and on Linux `os_write_access`
(`true` means the OS *would* let BAMS write: for a TV/movie folder that's what subtitle copies need, for a music
folder tighten the permissions). On Windows that check can't see ACLs, so it reports `null`; use the `icacls` check
above. `GET /api/settings/opensubtitles-save` reports the same per TV/movie folder, with the Linux command.
