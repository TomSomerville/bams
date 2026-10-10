import { useEffect, useState } from "react";
import { api, getServer, hello, removeExtra, updateExtra } from "../api";
import { useFocusOnReady, useNav } from "../App";
import { prefs, setPref } from "../prefs";
import { appVersion, deviceName } from "../tizen";
import { hasAvplay } from "../engine";

/** This TV: which server, which account, playback choices. */
export default function Settings() {
  const nav = useNav();
  const [server, setServerInfo] = useState<{ version: string } | null>(null);
  const [name, setName] = useState<string | null>(null);  // what its admin calls it (Settings on the web)
  const [, redraw] = useState(0);
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

  return (
    <div className="page settings">
      <div className="page-head"><h1>Settings</h1></div>

      <section className="panel">
        <h2>Server</h2>
        <p className="big">{name && <strong>{name}  ·  </strong>}{getServer()?.replace(/^https?:\/\//, "")}{server ? `  ·  BAMS ${server.version}` : ""}</p>
        <button className="btn" data-fid="server" onClick={nav.changeServer}>Change server</button>
      </section>

      <section className="panel">
        <h2>Account</h2>
        <p className="big">Signed in as <strong>{nav.user?.name}</strong>.</p>
        <p>What you've watched, where you stopped, Continue Watching and your Home rows belong to this account and are
          kept on the server: the same here as on the web, and the TV and a computer can play at the same time. To use
          another account's, switch: then link the TV again from a browser signed in as that person.</p>
        <button className="btn" data-fid="signout" onClick={nav.signOut}>Switch account (sign out of this TV)</button>
      </section>

      <section className="panel">
        <h2>Other BAMS servers</h2>
        <p>More servers on this TV, each linked to an account there. Their libraries appear in the menu under the
          server's name. This list is this TV's own: another TV or a browser has its own.</p>
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
                Remove from this TV
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
            <small>Only for troubleshooting: the TV plays most files as they are, which looks best and spares the server.</small>
          </span>
        </button>
        <button className="toggle" data-fid="dts" onClick={() => toggle("dts")}>
          <span className={`switch ${prefs.dts ? "on" : ""}`} />
          <span>
            <strong>This TV plays DTS sound</strong>
            <small>Most Samsung TVs from 2018 on don't, so BAMS converts DTS to AAC. Turn on only if yours does.</small>
          </span>
        </button>
      </section>

      <section className="panel">
        <h2>About</h2>
        <p>{deviceName()} · BAMS TV {appVersion()} · player: {hasAvplay() ? "Samsung AVPlay" : "HTML video"}</p>
      </section>
    </div>
  );
}
