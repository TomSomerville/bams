import { useEffect, useState } from "react";
import { api, getServer } from "../api";
import { useFocusOnReady, useNav } from "../App";
import { prefs, setPref } from "../prefs";
import { appVersion, deviceName } from "../tizen";
import { hasAvplay } from "../engine";

/** This TV: which server, which account, playback choices. */
export default function Settings() {
  const nav = useNav();
  const [server, setServerInfo] = useState<{ version: string } | null>(null);
  const [, redraw] = useState(0);
  useEffect(() => {
    api.get<{ version: string }>("/api/status").then(setServerInfo).catch(() => undefined);
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
        <p className="big">{getServer()?.replace(/^https?:\/\//, "")}{server ? `  ·  BAMS ${server.version}` : ""}</p>
        <button className="btn" data-fid="server" onClick={nav.changeServer}>Change server</button>
      </section>

      <section className="panel">
        <h2>Account</h2>
        <p className="big">Signed in as <strong>{nav.user?.name}</strong>. This TV keeps its own watch history under this
          account, the same as the web.</p>
        <button className="btn" data-fid="signout" onClick={nav.signOut}>Sign out of this TV</button>
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
