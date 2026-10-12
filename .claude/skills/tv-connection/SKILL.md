---
name: tv-connection
description: Turn this PC's connection to the owner's Samsung TV (sdb, Tizen Developer Mode) on or off, or check it. Use when the owner says "connect to the TV", "disconnect the TV", "turn the TV connection on/off", "is the TV connected", or before installing the TV app (npm run package -- --install) when the TV isn't connected.
---

# TV connection (sdb)

The PC talks to the TV with Samsung's `sdb` (Tizen Studio), over the home network. What's involved:

| What | Value |
|---|---|
| sdb | `C:\tizen-studio\tools\sdb.exe` |
| TV | Samsung The Frame QN50LS03BAFXZA, `192.168.1.211`, port `26101` (sdb's default) |
| This PC | `192.168.1.40`: the TV's Developer Mode only accepts this "Host PC IP" |

There are two layers. Only the first one is yours to switch:

1. **The PC side (this skill):** whether `sdb` on this PC is connected to the TV. Turning it on or off changes
   nothing on the TV and is safe to do any time.
2. **The TV side (the owner only):** Developer Mode on the TV. While it's on, the TV accepts a connection from
   `192.168.1.40`. You can't switch it remotely. When the owner wants the TV fully closed, tell them the steps under
   "TV side" below.

Run the commands with the Bash tool (Git Bash). The path below is the Git Bash form.

## Check

```bash
/c/tizen-studio/tools/sdb.exe devices
```

- The line `192.168.1.211:26101   device   QN50LS03BAFXZA` means it's **on** (connected).
- An empty list means it's **off**.
- `offline` or `unauthorized` means connected but not usable: turn it off, then on again.

## On

```bash
/c/tizen-studio/tools/sdb.exe start-server
/c/tizen-studio/tools/sdb.exe connect 192.168.1.211
/c/tizen-studio/tools/sdb.exe devices
```

It worked if `connect` prints `connected to 192.168.1.211:26101` (or `is already connected`) **and** `devices` lists
`QN50LS03BAFXZA` as `device`. Report that to the owner.

If it fails (`failed to connect`, timeout, or an empty `devices` list), check these in order and tell the owner which
one it is:
1. **The TV is off or in standby:** ask the owner to turn it on. Sometimes The Frame's Art Mode doesn't answer: ask
   for TV mode.
2. **The TV's address changed** (DHCP): ask the owner for it (TV: Settings → General → Network → Network Status →
   IP Settings), then connect to that address. If it changed for good, update this file, the "Samsung TV app" line in
   `CLAUDE.md` and the memory note.
3. **This PC's address changed:** run `ipconfig` and look at the IPv4 address. If it isn't `192.168.1.40`, the TV
   refuses it: the owner has to enter the new address as the Host PC IP (TV side below).
4. **Developer Mode is off on the TV:** the owner has to turn it on (TV side below).

## Off

```bash
/c/tizen-studio/tools/sdb.exe disconnect 192.168.1.211
/c/tizen-studio/tools/sdb.exe devices
```

It's off when `devices` no longer lists the TV. Tell the owner the TV still *accepts* a new connection from this PC
until Developer Mode is turned off on the TV. Offer the TV-side steps if they want it fully closed.

Ask the owner before you stop sdb's background server on this PC (`sdb.exe kill-server`): Tizen Studio uses it too
if it's open. It's only needed if the owner wants nothing of sdb running. Use `kill-server`, never
`taskkill /IM sdb.exe` (see "Never kill processes by name" in `CLAUDE.md`).

## TV side (tell the owner; you can't do this)

From Samsung's guide (<https://developer.samsung.com/smarttv/develop/getting-started/using-sdk/tv-device.html>):

- **On:** Apps → App Settings → type `1 2 3 4 5` on the remote → Developer mode **On** → Host PC IP `192.168.1.40`
  → OK → turn the TV off and on. "Develop Mode" then shows at the top of the Apps panel.
- **Off:** the same popup (Apps → App Settings → `1 2 3 4 5`) → Developer mode **Off** → restart the TV. Samsung's
  page doesn't describe turning it off, so say this step is inferred from the same popup. If the owner's screens look
  different, ask for a photo and search for the current steps (global CLAUDE.md: look it up, don't rely on memory).

With Developer Mode off, the TV app can't be installed or updated from this PC. The installed BAMS app should keep
working, but that isn't confirmed on this model yet: ask the owner to check that BAMS still opens. Turn Developer
Mode back on for the next install.

## Installing the app afterwards

With the connection on: `cd tv && npm run package -- --install --run` (see `tv/README.md`). It signs with the
"BAMS" certificate profile. Only that certificate installs on this TV.
