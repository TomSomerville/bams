import { useEffect, useState, type FormEvent } from "react";
import { api, type WatchSettings as Shape } from "../api";

/** When a movie or episode counts as started (Continue Watching) and as watched. For every account. */
export default function WatchSettings() {
  const [saved, setSaved] = useState<Shape | null>(null);
  const [percent, setPercent] = useState("");
  const [after, setAfter] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    api.get<{ watch: Shape }>("/api/settings").then(({ watch }) => {
      setSaved(watch);
      setPercent(String(watch.watched_percent));
      setAfter(String(watch.resume_after));
    }).catch((e) => setMsg({ ok: false, text: e.message }));
  }, []);

  const p = Number(percent), a = Number(after);
  const valid = percent !== "" && after !== "" && Number.isInteger(p) && p >= 50 && p <= 100
    && Number.isInteger(a) && a >= 0 && a <= 600;
  const changed = saved && (p !== saved.watched_percent || a !== saved.resume_after);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setMsg(null);
    try {
      setSaved(await api.put<Shape>("/api/settings/watch", { watched_percent: p, resume_after: a }));
      setMsg({ ok: true, text: "Saved." });
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    }
  };

  return (
    <section className="lib-card settings-card">
      <div className="lib-head"><h3>Watched and Continue Watching</h3></div>
      <p className="muted">When a movie or episode counts as started (its place is saved and it shows in Continue
        Watching) and when it counts as watched. These apply to every account.</p>
      {saved && (
        <form className="watch-form" onSubmit={save}>
          <label htmlFor="resume-after">Started after</label>
          <span><input id="resume-after" className="text-input num-input" type="number" min={0} max={600} step={1}
            value={after} onChange={(e) => { setAfter(e.target.value); setMsg(null); }} /> seconds of watching</span>
          <label htmlFor="watched-percent">Watched at</label>
          <span><input id="watched-percent" className="text-input num-input" type="number" min={50} max={100} step={1}
            value={percent} onChange={(e) => { setPercent(e.target.value); setMsg(null); }} /> % of its length</span>
          <span />
          <span><button className="btn small primary" disabled={!valid || !changed}>Save</button></span>
        </form>
      )}
      {!valid && saved && <p className="key-msg bad">Started after: 0–600 seconds. Watched at: 50–100%.</p>}
      {msg && <p className={`key-msg ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
      <p className="fine-print">Players report where they are every 10 seconds, so a short "started after" can take
        that long to count.</p>
    </section>
  );
}
