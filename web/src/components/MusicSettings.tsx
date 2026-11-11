import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import Icon from "./Icon";

type Output = "aac" | "flac";
type LbStatus = { configured: boolean; last4: string | null; user: string | null };

/** On/off for online music identification (no key needed: the services are open), the ListenBrainz token Top Played
 *  Songs needs, and what music browsers can't play is converted to. */
export default function MusicSettings() {
  const [on, setOn] = useState<boolean | null>(null);
  const [output, setOutput] = useState<Output | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [lb, setLb] = useState<LbStatus | null>(null);

  useEffect(() => {
    api.get<{ music_lookup: boolean; music_output: Output; listenbrainz?: LbStatus }>("/api/settings")
      .then((s) => { setOn(s.music_lookup); setOutput(s.music_output); setLb(s.listenbrainz ?? null); })
      .catch((e) => setErr(e.message));
  }, []);

  const pickOutput = async (o: Output) => {
    setErr(null);
    try {
      setOutput((await api.put<{ music_output: Output }>("/api/settings/music-output", { output: o })).music_output);
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const toggle = async () => {
    setErr(null);
    try {
      setOn((await api.put<{ music_lookup: boolean }>("/api/settings/music-lookup", { enabled: !on })).music_lookup);
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <section className="lib-card settings-card">
      <div className="lib-head">
        <h3>Music identification</h3>
        {on !== null && (on
          ? <span className="status-pill ok"><Icon name="check" size={14} /> On</span>
          : <span className="status-pill warn">Off</span>)}
      </div>
      <p className="muted">
        After each scan of a music library, BAMS looks up new albums and artists on{" "}
        <a href="https://musicbrainz.org" target="_blank" rel="noreferrer">MusicBrainz</a> (album names, original
        release years, track titles for untagged files), takes missing covers from the{" "}
        <a href="https://coverartarchive.org" target="_blank" rel="noreferrer">Cover Art Archive</a>, and artist
        bios and photos from Wikipedia and Wikimedia Commons. No account or key is needed for this. Your own tags, genres and
        cover images always come first. When it's off, music is identified from tags and folders only.
      </p>
      <div className="key-row">
        <button className={`btn small ${on ? "ghost" : "primary"}`} onClick={toggle} disabled={on === null}>
          {on ? "Turn off" : "Turn on"}
        </button>
        <span className="muted">Albums it couldn't identify can be fixed from the album page ("Fix match").</span>
      </div>
      <p className="fine-print">
        Only artist and album names are sent to these services. MusicBrainz data is CC0; Wikipedia text is CC BY-SA
        and each photo shows its own author and licence. Identified albums and artists are looked up again every
        few months.
      </p>

      {lb && <ListenBrainzToken status={lb} onChange={setLb} />}

      <h4 className="settings-sub">Converted music</h4>
      <p className="muted">
        Formats browsers can't play (ALAC, AIFF, WMA, APE, WavPack, DSD…) are converted while they stream. FLAC is
        lossless and plays gaplessly, but uses about four times the data of AAC: best on your home network.
      </p>
      <div className="segmented" role="radiogroup" aria-label="Convert music to">
        {([["aac", "AAC 256 kbps"], ["flac", "FLAC (lossless)"]] as const).map(([k, label]) => (
          <button key={k} role="radio" aria-checked={output === k} className={output === k ? "on" : ""}
            disabled={output === null} onClick={() => output !== k && pickOutput(k)}>
            {label}
          </button>
        ))}
      </div>
      {err && <p className="key-msg bad">{err}</p>}
    </section>
  );
}

/** The admin's own ListenBrainz token: its popularity data (Top Played Songs) now needs one. Checked with ListenBrainz
 *  before it's saved; the server never sends it back (only its last 4 characters and the account name). */
function ListenBrainzToken({ status, onChange }: { status: LbStatus; onChange: (s: LbStatus) => void }) {
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const showForm = !status.configured || editing;

  const save = async () => {
    if (!draft.trim()) return;
    setBusy(true);
    setMsg(null);
    try {
      const s = await api.put<LbStatus & { checked: boolean }>("/api/settings/listenbrainz-token", { key: draft.trim() });
      onChange(s);
      setDraft("");
      setEditing(false);
      setMsg(s.checked ? { ok: true, text: "Saved. ListenBrainz accepted the token." }
        : { ok: false, text: "Saved, but ListenBrainz couldn't be reached to check it yet." });
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
      input.current?.focus();
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    try {
      onChange(await api.del<LbStatus>("/api/settings/listenbrainz-token"));
      setMsg(null);
      setEditing(false);
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    }
  };

  return (
    <div id="listenbrainz">
      <h4 className="settings-sub">ListenBrainz token (Top Played Songs)</h4>
      <p className="muted">
        Top Played Songs on artist pages comes from{" "}
        <a href="https://listenbrainz.org" target="_blank" rel="noreferrer">ListenBrainz</a>, which now asks for a
        token. It's free: sign in to ListenBrainz with a MusicBrainz account, then copy the "User token" from{" "}
        <a href="https://listenbrainz.org/settings/" target="_blank" rel="noreferrer">listenbrainz.org/settings</a>.
        Only artist ids are sent with it.
      </p>
      {!showForm ? (
        <div className="key-row">
          <code className="key-saved">••••••••{status.last4}</code>
          <span className="muted">{status.user ? `ListenBrainz account ${status.user}` : "saved on the server"}</span>
          <span className="spacer" />
          <button className="btn ghost small" onClick={() => { setEditing(true); setMsg(null); setTimeout(() => input.current?.focus(), 0); }}>
            <Icon name="edit" size={16} /> Replace
          </button>
          <button className="btn ghost small danger" onClick={remove}>Remove</button>
        </div>
      ) : (
        <form className="key-form" onSubmit={(e) => { e.preventDefault(); save(); }}>
          <div className="key-input">
            <input ref={input} type="password" value={draft} onChange={(e) => { setDraft(e.target.value); setMsg(null); }}
              placeholder="Paste your ListenBrainz user token" aria-label="ListenBrainz token" autoComplete="off" spellCheck={false} />
          </div>
          <button type="submit" className="btn primary small" disabled={!draft.trim() || busy}>{busy ? "Checking…" : "Save"}</button>
          {status.configured && (
            <button type="button" className="btn ghost small" onClick={() => { setEditing(false); setDraft(""); setMsg(null); }}>Cancel</button>
          )}
        </form>
      )}
      {msg && <p className={`key-msg ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
    </div>
  );
}
