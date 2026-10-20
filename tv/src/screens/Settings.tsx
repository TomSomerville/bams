import { useEffect, useRef, useState } from "react";
import { api, getServer, hello, removeExtra, updateExtra } from "../api";
import { useFocusOnReady, useNav } from "../App";
import { prefs, setPref } from "../prefs";
import { appVersion, deviceName, isBack } from "../tizen";
import { hasAvplay, hasExo } from "../engine";
import { setKeyHandler } from "../keys";
import { focus } from "../nav";
import { watchKeys } from "../pckeys";
import { deviceWord, pc, theatre } from "../platform";

/** The web UI's flag "start in theatre mode on this browser" (web/src/main.tsx). */
const START_THEATRE = "bams.startTheatre";

/** This TV or PC: which server, which account, playback choices. */
export default function Settings() {
  const nav = useNav();
  const w = deviceWord();
  const [server, setServerInfo] = useState<{ version: string } | null>(null);
  const [name, setName] = useState<string | null>(null);  // what its admin calls it (Settings on the web)
  const [, redraw] = useState(0);
  const [testing, setTesting] = useState(false);
  const [leaving, setLeaving] = useState(false);
  useEffect(() => {
    api.get<{ version: string }>("/api/status").then(setServerInfo).catch(() => undefined);
    const url = getServer();
    if (url) void hello(url).then((h) => setName(h?.name ?? null));
  }, []);
  useFocusOnReady(true);

  const toggle = (k: "alwaysConvert" | "dts") => {
    setPref(k, !prefs[k]);
    redraw((n) => n + 1);
  };

  // the "Leave theatre mode?" question: Back closes it (rather than leaving Settings)
  useEffect(() => {
    if (!leaving) return;
    setKeyHandler((e) => {
      if (!isBack(e)) return false;
      setLeaving(false);
      setTimeout(() => focus(document.querySelector<HTMLElement>('[data-fid="leave"]')));
      return true;
    });
    return () => setKeyHandler(null);
  }, [leaving]);

  const leave = () => {
    try {
      localStorage.removeItem(START_THEATRE);
    } catch { /* storage unavailable */ }
    location.assign("/");
  };

  return (
    <div className="page settings">
      <div className="page-head"><h1>Settings</h1></div>

      <section className="panel">
        <h2>Server</h2>
        <p className="big">{name && <strong>{name}  ·  </strong>}{getServer()?.replace(/^https?:\/\//, "")}{server ? `  ·  BAMS ${server.version}` : ""}</p>
        {/* theatre mode: the server is the one this page came from */}
        {!theatre() && <button className="btn" data-fid="server" onClick={nav.changeServer}>Change server</button>}
      </section>

      <section className="panel">
        <h2>Account</h2>
        <p className="big">Signed in as <strong>{nav.user?.name}</strong>.</p>
        <p>What you've watched, where you stopped, Continue Watching and your Home rows belong to this account and are
          kept on the server: the same here as on the web, and this {w} and a computer can play at the same time. To use
          another account's, switch: then sign this {w} in again as that person.</p>
        {theatre()
          ? <div className="button-row">
              <button className="btn" data-fid="accounts" onClick={() => nav.reset({ name: "accounts" })}>Switch account</button>
              <button className="btn" data-fid="signout" onClick={nav.signOut}>Sign out</button>
            </div>
          : <button className="btn" data-fid="signout" onClick={nav.signOut}>Switch account (sign out of this {w})</button>}
      </section>

      <section className="panel">
        <h2>Other BAMS servers</h2>
        <p>More servers on this {w}, each linked to an account there. Their libraries appear in the menu under the
          server's name. This list is this {w}'s own: another TV or a browser has its own.</p>
        {nav.servers.map((s) => (
          <div key={s.id} className="extra-server">
            <p className="big"><strong>{s.name}</strong>  ·  {s.url.replace(/^https?:\/\//, "")}
              {s.user ? `  ·  ${s.user.name}` : ""}{s.state ? `  ·  ${s.state}` : ""}</p>
            {s.libraries.map((l) => (
              <button key={l.id} className="toggle" data-fid={`srv-${s.id}-lib-${l.id}`} onClick={() => {
                updateExtra(s.id, (e) => ({ ...e, hidden: { ...e.hidden, [l.id]: !e.hidden[l.id] } }));
                nav.reloadServers();
              }}>
                <span className={`switch ${s.hidden[l.id] ? "" : "on"}`} />
                <span><strong>{l.name}</strong><small>Show in the menu</small></span>
              </button>
            ))}
            <div className="button-row">
              <button className="btn" data-fid={`srv-${s.id}-relink`} onClick={() => nav.addServer({ url: s.url, name: s.name })}>
                Link again
              </button>
              <button className="btn" data-fid={`srv-${s.id}-remove`} onClick={() => { removeExtra(s.id); nav.reloadServers(); }}>
                Remove from this {w}
              </button>
            </div>
          </div>
        ))}
        <button className="btn" data-fid="add-server" onClick={() => nav.addServer()}>Add a server</button>
      </section>

      <section className="panel">
        <h2>Playback</h2>
        <button className="toggle" data-fid="convert" data-autofocus onClick={() => toggle("alwaysConvert")}>
          <span className={`switch ${prefs.alwaysConvert ? "on" : ""}`} />
          <span>
            <strong>Always convert on the server</strong>
            <small>Only for troubleshooting: the {w} plays most files as they are, which looks best and spares the server.</small>
          </span>
        </button>
        {!hasExo() && !pc() && <button className="toggle" data-fid="dts" onClick={() => toggle("dts")}>
          <span className={`switch ${prefs.dts ? "on" : ""}`} />
          <span>
            <strong>This TV plays DTS sound</strong>
            <small>Most Samsung TVs from 2018 on don't, so BAMS converts DTS to AAC. Turn on only if yours does.</small>
          </span>
        </button>}
      </section>

      {pc() && (
        <section className="panel">
          <h2>This browser</h2>
          <p>For a PC at a TV, start the browser in kiosk mode when the PC starts: then the remote's Back stays Back and
            nothing leaves full screen. How to set that up is under Settings → This browser in BAMS on a computer.</p>
          <div className="button-row">
            <button className="btn" data-fid="fullscreen" onClick={() => void document.documentElement.requestFullscreen?.().catch(() => undefined)}>
              Full screen (Escape leaves it)
            </button>
            <button className="btn" data-fid="remote" onClick={() => setTesting(true)}>Test the remote</button>
            {theatre() && <button className="btn" data-fid="leave" onClick={() => setLeaving(true)}>Leave theatre mode</button>}
          </div>
        </section>
      )}

      <section className="panel">
        <h2>About</h2>
        <p>{deviceName()} · {theatre() ? "BAMS theatre mode" : `BAMS TV ${appVersion()}`} · player: {hasAvplay() ? "Samsung AVPlay" : hasExo() ? "ExoPlayer" : "HTML video"}</p>
      </section>

      {testing && <RemoteTest onClose={() => { setTesting(false); setTimeout(() => focus(document.querySelector<HTMLElement>('[data-fid="remote"]'))); }} />}
      {leaving && (
        <div className="menu over-page" data-trap>
          <h2>Leave theatre mode?</h2>
          <p className="os-note">This opens BAMS's ordinary web pages in this browser, which need a mouse. To come back,
            choose Theatre mode in the account menu there.</p>
          <div className="button-row">
            <button className="btn" ref={(b) => b?.focus()} onClick={() => setLeaving(false)}>Stay</button>
            <button className="btn" onClick={leave}>Leave</button>
          </div>
        </div>
      )}
    </div>
  );
}

/** Settings → Test the remote: every key pressed, by name, and what BAMS does with it. Back closes it. */
function RemoteTest({ onClose }: { onClose: () => void }) {
  const [keys, setKeys] = useState<{ n: number; name: string; means: string }[]>([]);
  const n = useRef(0);
  useEffect(() => {
    watchKeys((e, means) => {
      const name = e.key === " " ? "Space" : e.key || `keyCode ${e.keyCode}`;
      const mods = [e.ctrlKey && "Ctrl", e.altKey && "Alt", e.shiftKey && e.key.length > 1 && "Shift", e.metaKey && "Meta"].filter(Boolean);
      setKeys((k) => [{ n: ++n.current, name: [...mods, name].join("+"), means }, ...k].slice(0, 8));
    });
    // nothing else reacts while testing; Back (the remote's, Escape, Backspace, BrowserBack) closes
    setKeyHandler((e) => {
      if (isBack(e)) onClose();
      return true;
    });
    return () => {
      watchKeys(null);
      setKeyHandler(null);
    };
  }, [onClose]);
  return (
    <div className="menu over-page" data-trap>
      <h2>Test the remote</h2>
      <p className="os-note">Press the remote's buttons. Back closes this.</p>
      <div className="menu-list">
        {!keys.length && <p className="muted">Waiting for a key…</p>}
        {keys.map((k) => (
          <div key={k.n} className="menu-item"><strong>{k.name}</strong>&nbsp;→ {k.means}</div>
        ))}
      </div>
    </div>
  );
}
