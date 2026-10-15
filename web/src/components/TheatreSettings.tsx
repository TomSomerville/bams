import { useState } from "react";

/** The flag "start in theatre mode on this browser": main.tsx sends "/" to "/theatre/" (theatre Settings clears it). */
export const START_THEATRE = "bams.startTheatre";

function flag(): boolean {
  try {
    return localStorage.getItem(START_THEATRE) === "1";
  } catch {
    return false;
  }
}

/** Settings → This browser → Theatre mode: BAMS's TV page (served at /theatre/) for a PC at a TV, driven by a remote.
 *  Opening it, starting this browser in it, and how to make a PC start it by itself (docs/THEATRE.md has the rest). */
export function TheatreSettings() {
  const [on, setOn] = useState(flag);
  const host = location.host;
  const local = /^(localhost|127\.|\[::1\])/.test(location.hostname);
  const page = `${location.protocol}//${host}/theatre/`;
  const hello = `${location.protocol}//${host}/api/hello`;
  const toggle = () => {
    try {
      if (on) localStorage.removeItem(START_THEATRE);
      else localStorage.setItem(START_THEATRE, "1");
    } catch { /* storage unavailable */ }
    setOn(!on);
  };
  const linux = `#!/bin/sh
# ~/.local/bin/bams-theatre (chmod +x): waits for the server, then BAMS in theatre mode, full screen
until python3 -c "import urllib.request; urllib.request.urlopen('${hello}', timeout=3)" 2>/dev/null; do sleep 3; done
for b in google-chrome chromium chromium-browser; do command -v $b >/dev/null && break; done
exec $b --kiosk --user-data-dir="$HOME/.config/bams-theatre" --password-store=basic --no-first-run \\
  --noerrdialogs --autoplay-policy=no-user-gesture-required ${page}`;
  const desktop = `# ~/.config/autostart/bams-theatre.desktop
[Desktop Entry]
Type=Application
Name=BAMS Theatre
Exec=sh -c "$HOME/.local/bin/bams-theatre"`;
  const windows = `# %USERPROFILE%\\bams-theatre.ps1: waits for the server, then BAMS in theatre mode, full screen
while ($true) { try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 '${hello}' | Out-Null; break } catch { Start-Sleep 3 } }
& "$env:ProgramFiles\\Google\\Chrome\\Application\\chrome.exe" --kiosk --user-data-dir="$env:LOCALAPPDATA\\BAMS-Theatre" \`
  --no-first-run --noerrdialogs --autoplay-policy=no-user-gesture-required '${page}'

# Start-up shortcut (Win+R, shell:startup), "Run: Minimized":
#   powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%USERPROFILE%\\bams-theatre.ps1"`;
  return (
    <section className="lib-card settings-card" id="theatre">
      <div className="lib-head"><h3>Theatre mode</h3></div>
      <p className="muted">BAMS for a PC at a TV, driven by a remote: the same screens as the BAMS TV apps, full
        screen, with the arrows, OK and Back (a remote's keyboard types searches).</p>
      <div className="key-row">
        <a className="btn small primary" href="/theatre/">Open theatre mode</a>
        <label className="check"><input type="checkbox" checked={on} onChange={toggle} /> Start in theatre mode on this browser</label>
      </div>
      <details>
        <summary>Make a PC start it by itself</summary>
        <p className="muted">Let the PC sign in to its desktop by itself, then start the browser like this when it does.
          Use a Chrome or Chromium browser: Edge's kiosk mode forgets the sign-in at every start.
          {local && " This page's address is this computer's own: use the server's network address (its IP) on the PC instead."}</p>
        <h4>Linux Mint, Ubuntu, Debian</h4>
        <pre className="code-block">{linux}</pre>
        <pre className="code-block">{desktop}</pre>
        <h4>Windows</h4>
        <pre className="code-block">{windows}</pre>
      </details>
    </section>
  );
}
