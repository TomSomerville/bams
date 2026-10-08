import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { api, type TmdbStatus } from "../api";
import { useSettings } from "../settings";
import { keyKind, TMDB_SIGNUP_URL } from "../tmdb";
import Icon from "./Icon";

type Msg = { ok: boolean; text: string } | null;

export default function TmdbSettings() {
  const { tmdb, setTmdb, serverError } = useSettings();
  const { hash } = useLocation();
  const section = useRef<HTMLElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);
  const [reveal, setReveal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<Msg>(null);
  const [flash, setFlash] = useState(false);
  const configured = !!tmdb?.configured;
  const showForm = !configured || editing;

  // Arriving from the warning banner (/settings#tmdb): scroll here, focus the field, flash the card.
  useEffect(() => {
    if (hash !== "#tmdb" || !tmdb) return;
    section.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    input.current?.focus({ preventScroll: true });
    setFlash(true);
    const t = setTimeout(() => setFlash(false), 1600);
    return () => clearTimeout(t);
  }, [hash, tmdb]);

  const kind = keyKind(draft);
  const formatHint = draft.trim() && !kind ? "Doesn't look like a TMDB key yet." : null;

  // The server checks the key with TMDB before saving; a rejected key is not saved.
  const save = async () => {
    if (!kind) return;
    setBusy(true);
    setMsg(null);
    try {
      const s = await api.put<TmdbStatus>("/api/settings/tmdb-key", { key: draft.trim() });
      setTmdb(s);
      setDraft("");
      setEditing(false);
      setReveal(false);
      setMsg(s.verified_at ? { ok: true, text: "Saved. TMDB accepted the key." }
        : { ok: false, text: "Saved, but TMDB couldn't be reached to verify it yet." });
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
      input.current?.focus();
    } finally {
      setBusy(false);
    }
  };

  const test = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.post<{ ok: boolean; message: string }>("/api/settings/tmdb-key/test");
      setMsg({ ok: r.ok, text: r.ok ? "Key works. BAMS can fetch posters and descriptions." : r.message });
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    try {
      setTmdb(await api.del<TmdbStatus>("/api/settings/tmdb-key"));
      setMsg(null);
      setEditing(false);
      setTimeout(() => input.current?.focus(), 0);
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    }
  };

  return (
    <section id="tmdb" ref={section} className={`lib-card settings-card ${flash ? "flash" : ""}`}>
      <div className="lib-head">
        <h3>TMDB API key</h3>
        {tmdb && (configured
          ? <span className="status-pill ok"><Icon name="check" size={14} /> Configured</span>
          : <span className="status-pill warn"><Icon name="alert" size={14} /> Not configured</span>)}
      </div>
      <p className="muted">
        BAMS uses <a href="https://www.themoviedb.org" target="_blank" rel="noreferrer">TMDB</a> to identify your
        movies and shows and fetch posters, descriptions, cast and IMDb IDs. Each BAMS server uses its owner's own free
        key. Get one at{" "}
        <a href={TMDB_SIGNUP_URL} target="_blank" rel="noreferrer">themoviedb.org/settings/api</a> (free account,
        choose "Developer", personal use). Paste the <strong>API Read Access Token</strong> (preferred) or the
        <strong> API Key</strong>. New to this? Follow the{" "}
        <a href="/help/tmdb.html" target="_blank" rel="noreferrer">step-by-step guide</a>.
      </p>

      {serverError && !tmdb ? (
        <p className="key-msg bad">{serverError}</p>
      ) : !tmdb ? null : !showForm ? (
        <div className="key-row">
          <code className="key-saved">••••••••{tmdb.last4}</code>
          <span className="muted">{tmdb.kind === "token" ? "Read Access Token" : "API Key"} · saved on the server</span>
          <span className="spacer" />
          <button className="btn ghost small" onClick={test} disabled={busy}>
            <Icon name="refresh" size={16} /> {busy ? "Testing…" : "Test"}
          </button>
          <button className="btn ghost small" onClick={() => { setEditing(true); setMsg(null); setTimeout(() => input.current?.focus(), 0); }}>
            <Icon name="edit" size={16} /> Replace
          </button>
          <button className="btn ghost small danger" onClick={remove}>Remove</button>
        </div>
      ) : (
        <form className="key-form" onSubmit={(e) => { e.preventDefault(); save(); }}>
          <div className="key-input">
            <input
              ref={input}
              type={reveal ? "text" : "password"}
              value={draft}
              onChange={(e) => { setDraft(e.target.value); setMsg(null); }}
              placeholder="Paste your TMDB API Read Access Token or API Key"
              aria-label="TMDB API key"
              autoComplete="off"
              spellCheck={false}
            />
            <button type="button" className="icon-btn" onClick={() => setReveal(!reveal)}
              aria-label={reveal ? "Hide key" : "Show key"} title={reveal ? "Hide" : "Show"}>
              <Icon name={reveal ? "eyeOff" : "eye"} size={18} />
            </button>
          </div>
          <button type="submit" className="btn primary small" disabled={!kind || busy}>{busy ? "Checking…" : "Save"}</button>
          {configured && (
            <button type="button" className="btn ghost small" onClick={() => { setEditing(false); setDraft(""); setMsg(null); }}>
              Cancel
            </button>
          )}
        </form>
      )}

      {formatHint && showForm && <p className="key-msg warn">{formatHint}</p>}
      {msg && <p className={`key-msg ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}

      <p className="fine-print">
        This product uses the TMDB API but is not endorsed or certified by TMDB. The key is stored on the BAMS server
        and never sent back to the browser.
      </p>
    </section>
  );
}
