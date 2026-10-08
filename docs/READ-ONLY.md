# Media folders are read-only to BAMS

BAMS only ever **reads** the folders you add as Movies / TV Shows / Music libraries. It never
renames, moves, deletes, re-tags or touches them, and never drops artwork, `.nfo` or thumbnail
files next to your media. Everything BAMS learns goes into its own data folder:

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
   creating databases. The hook can't be removed once installed. `server/tests/test_readonly.py`
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

## What BAMS reports

`GET /api/libraries` shows, per folder: `exists`, `readable`, and on Linux `os_write_access`
(`true` means the OS *would* let BAMS write, so tighten the permissions). On Windows that check
can't see ACLs, so it reports `null`; use the `icacls` check above.
