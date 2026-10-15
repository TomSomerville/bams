import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api } from "../api";

type Device = { id: string; name: string; created_at: number; last_seen_at: number };

const when = (ts: number) => new Date(ts * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

/** Your TVs: link one with the code it shows (the BAMS TV app), see the linked ones, sign one out.
 *  Server: /api/devices (devices.py). `code` pre-fills the box (the TV's QR code opens /link?code=…). */
export function TvSettings({ code: initial = "" }: { code?: string }) {
  const [code, setCode] = useState(initial);
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get<Device[]>("/api/devices").then(setDevices).catch(() => setDevices([]));
  }, []);
  useEffect(load, [load]);

  const link = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.post<{ name: string }>("/api/devices/approve", { code });
      setCode("");
      setMsg({ ok: true, text: `Linked: ${r.name}. It signs in by itself within a few seconds.` });
      setTimeout(load, 4000);
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const remove = async (d: Device) => {
    await api.del(`/api/devices/${d.id}`).catch((e) => setMsg({ ok: false, text: (e as Error).message }));
    load();
  };

  return (
    <section className="lib-card settings-card" id="tv">
      <div className="lib-head"><h3>Your TVs and theatre PCs</h3></div>
      <p className="muted">To sign in the BAMS app on a Samsung TV or a Fire TV, enter the code it shows. It then uses your
        account (its watch history is yours). PCs in theatre mode sign in with name and password, and are listed here too.</p>
      <form className="key-row" onSubmit={link}>
        <input className="text-input" placeholder="Code it shows, e.g. K7P 2QX" value={code} maxLength={12}
          onChange={(e) => { setCode(e.target.value.toUpperCase()); setMsg(null); }} aria-label="Code it shows"
          autoFocus={!!initial} />
        <button className="btn small primary" disabled={busy || code.replace(/[^A-Za-z0-9]/g, "").length < 6}>Link</button>
      </form>
      {msg && <p className={`key-msg ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
      {devices && devices.length > 0 && (
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {devices.map((d) => (
            <li key={d.id} className="key-row">
              <span><strong>{d.name}</strong> <span className="muted">· linked {when(d.created_at)} · last used {when(d.last_seen_at)}</span></span>
              <span className="spacer" />
              <button type="button" className="btn small ghost" onClick={() => void remove(d)}>Sign out</button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
