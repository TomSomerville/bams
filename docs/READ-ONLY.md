# Media folders are read-only to BAMS

BAMS only ever **reads** the folders you add as Movies / TV Shows / Music libraries. It never
renames, moves, deletes, re-tags or touches them, and never drops artwork, `.nfo` or thumbnail
files next to your media. Everything BAMS learns goes into its own data folder:

| OS | Data folder (default) |
|---|---|
| Windows | `%LOCALAPPDATA%\BAMS` (or `BAMS_DATA_DIR`) |
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

The shipped unit [`deploy/linux/bams.service`](../deploy/linux/bams.service) runs as a `bams`
system user with `ProtectSystem=strict`. **The kernel makes every path read-only to BAMS
except `/var/lib/bams`**, regardless of file permissions. You still need to grant *read*:

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

Run BAMS as its own service account and grant that account **Read & execute** only:

```powershell
# virtual service account created with the service (packaging comes later); or a local user
icacls "D:\Media" /grant "NT SERVICE\BAMS:(OI)(CI)RX"
```

Network shares: use a share account whose **share permission** is Read, and add the library by
UNC path (`\\nas\media\TV`), because a service can't see drive letters mapped in your user session.

Check: as that account, creating a file in the media folder must fail with "Access is denied".

## What BAMS reports

`GET /api/libraries` shows, per folder: `exists`, `readable`, and on Linux `os_write_access`
(`true` means the OS *would* let BAMS write, so tighten the permissions). On Windows that check
can't see ACLs, so it reports `null`; use the `icacls` check above.
