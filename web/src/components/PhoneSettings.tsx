import { useEffect, useState } from "react";
import { appApi, DOWNLOADS_CHANGED, inApp, type AppInfo } from "../android";
import { useAuth } from "../auth";
import { fmtSize } from "../format";
import Icon from "./Icon";

/** The Android app's own settings (android.ts): where downloads go (the phone or an SD card), Wi-Fi only, and the
 *  way to the Downloads screen and the app's server list. Kept on the phone, not on the server. */
export function PhoneSettings() {
  const { user } = useAuth();
  const [info, setInfo] = useState<AppInfo | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!inApp) return;
    const load = () => appApi.info().then(setInfo).catch((e) => setErr(e.message));
    load();
    window.addEventListener(DOWNLOADS_CHANGED, load);
    return () => window.removeEventListener(DOWNLOADS_CHANGED, load);
  }, []);
  if (!inApp) return null;
  const set = (p: Promise<AppInfo>) => p.then(setInfo).catch((e) => setErr(e.message));

  return (
    <section className="lib-card settings-card" id="phone">
      <div className="lib-head">
        <h3>Downloads on this phone</h3>
        <button className="btn small ghost push" onClick={() => { appApi.openDownloads().catch(() => {}); }}>
          <Icon name="download" size={16} /> Open Downloads
        </button>
      </div>
      <p className="muted">Downloaded movies, shows and music play with no connection: when the app can't reach a
        server, it opens your downloads. Files are downloaded as they are on the server (original quality).
        {!user.can_download && " Your account can't download from this server: an admin can turn it on in Settings → Accounts."}
      </p>
      {info && (
        <>
          <div className="phone-volumes" role="radiogroup" aria-label="Where downloads go">
            {info.volumes.map((v) => (
              <label key={v.id} className={`phone-volume ${info.location === v.id ? "on" : ""}`}>
                <input type="radio" name="volume" checked={info.location === v.id}
                  onChange={() => set(appApi.setLocation(v.id))} />
                <span className="phone-volume-name">{v.label}</span>
                <span className="muted">{fmtSize(v.free)} free of {fmtSize(v.total)}</span>
              </label>
            ))}
          </div>
          <p className="muted fine-print">New downloads go to the one picked; ones already made stay where they are.
            Downloads are kept in the app's own folder, so uninstalling the app deletes them.</p>
          <label className="check">
            <input type="checkbox" checked={info.wifiOnly} onChange={(e) => set(appApi.setWifiOnly(e.target.checked))} />
            Download over Wi-Fi only (waits for Wi-Fi instead of using mobile data)
          </label>
          <p className="muted">Downloads take {fmtSize(info.used)} · BAMS for Android {info.version}</p>
        </>
      )}
      <div className="key-row">
        <button className="btn small ghost" onClick={() => { appApi.openServers().catch(() => {}); }}>
          <Icon name="server" size={16} /> Servers and addresses
        </button>
        <span className="muted">Add another server, or this one's address away from home.</span>
      </div>
      {err && <p className="key-msg bad">{err}</p>}
    </section>
  );
}
