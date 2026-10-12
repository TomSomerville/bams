import { useEffect, useRef, useState } from "react";
import { api, type OpenSubtitlesStatus, type SaveCheck } from "../api";
import Icon from "./Icon";
import PasswordInput from "./PasswordInput";

const CONSUMERS_URL = "https://www.opensubtitles.com/en/consumers";  // where an account makes an API key

type Msg = { ok: boolean; text: string } | null;

/** Settings → Playback: this server's OpenSubtitles API key (admins), like the TMDB key, and an optional
 *  OpenSubtitles account that raises the daily download limit. */
export default function OpenSubtitlesSettings() {
  const [st, setSt] = useState<OpenSubtitlesStatus | null>(null);
  const [msg, setMsg] = useState<Msg>(null);

  useEffect(() => {
    api.get<{ opensubtitles: OpenSubtitlesStatus }>("/api/settings").then((s) => setSt(s.opensubtitles))
      .catch((e) => setMsg({ ok: false, text: e.message }));
  }, []);

  return (
    <section className="lib-card settings-card" id="opensubtitles">
      <div className="lib-head">
        <h3>OpenSubtitles</h3>
        {st && (st.configured
          ? <span className="status-pill ok"><Icon name="check" size={14} /> Configured</span>
          : <span className="status-pill warn">Not configured</span>)}
      </div>
      <p className="muted">
        With a key, the subtitles menu of a playing movie or episode gets <strong>Check OpenSubtitles</strong>: it
        finds subtitles for it on <a href="https://www.opensubtitles.com" target="_blank" rel="noreferrer">
        OpenSubtitles.com</a>, and the one picked is kept on this server (not in your media folders) for everyone who
        plays that file. Each BAMS server uses its owner's own free key: sign in at OpenSubtitles.com, open{" "}
        <a href={CONSUMERS_URL} target="_blank" rel="noreferrer">API consumers</a> in your profile, create one (any
        name, e.g. "BAMS") and paste its <strong>API key</strong> here.
      </p>
      {st && <KeyForm st={st} setSt={setSt} />}
      {st?.configured && <AccountForm st={st} setSt={setSt} />}
      {st?.configured && <SaveBeside st={st} setSt={setSt} />}
      {msg && <p className={`key-msg ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
    </section>
  );
}

function KeyForm({ st, setSt }: { st: OpenSubtitlesStatus; setSt: (s: OpenSubtitlesStatus) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);
  const [reveal, setReveal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<Msg>(null);
  const showForm = !st.configured || editing;

  // The server checks the key with OpenSubtitles before saving; a refused key is not saved.
  const save = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const s = await api.put<OpenSubtitlesStatus>("/api/settings/opensubtitles-key", { key: draft.trim() });
      setSt(s);
      setDraft("");
      setEditing(false);
      setReveal(false);
      setMsg(s.verified_at ? { ok: true, text: "Saved. OpenSubtitles accepted the key." }
        : { ok: false, text: "Saved, but OpenSubtitles couldn't be reached to check it yet." });
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
      const r = await api.post<{ ok: boolean; message: string }>("/api/settings/opensubtitles-key/test");
      setMsg({ ok: r.ok, text: r.message });
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    try {
      setSt(await api.del<OpenSubtitlesStatus>("/api/settings/opensubtitles-key"));
      setMsg(null);
      setEditing(false);
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    }
  };

  return <>
    {!showForm ? (
      <div className="key-row">
        <code className="key-saved">••••••••{st.last4}</code>
        <span className="muted">API key · saved on the server</span>
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
          <input ref={input} type={reveal ? "text" : "password"} value={draft}
            onChange={(e) => { setDraft(e.target.value); setMsg(null); }}
            placeholder="Paste your OpenSubtitles API key" aria-label="OpenSubtitles API key"
            autoComplete="off" spellCheck={false} />
          <button type="button" className="icon-btn" onClick={() => setReveal(!reveal)}
            aria-label={reveal ? "Hide key" : "Show key"} title={reveal ? "Hide" : "Show"}>
            <Icon name={reveal ? "eyeOff" : "eye"} size={18} />
          </button>
        </div>
        <button type="submit" className="btn primary small" disabled={!draft.trim() || busy}>{busy ? "Checking…" : "Save"}</button>
        {st.configured && (
          <button type="button" className="btn ghost small" onClick={() => { setEditing(false); setDraft(""); setMsg(null); }}>
            Cancel</button>
        )}
      </form>
    )}
    {msg && <p className={`key-msg ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
  </>;
}

/** Optional: the OpenSubtitles account downloads are made with (more a day than without one). */
function AccountForm({ st, setSt }: { st: OpenSubtitlesStatus; setSt: (s: OpenSubtitlesStatus) => void }) {
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<Msg>(null);
  const acc = st.account;

  const save = async () => {
    setBusy(true);
    setMsg(null);
    try {
      setSt(await api.put<OpenSubtitlesStatus>("/api/settings/opensubtitles", { username: user.trim(), password }));
      setEditing(false);
      setPassword("");
      setMsg({ ok: true, text: "Signed in. OpenSubtitles accepted the account." });
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  const signOut = async () => {
    setMsg(null);
    try {
      setSt(await api.del<OpenSubtitlesStatus>("/api/settings/opensubtitles"));
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    }
  };

  return (
    <div className="os-account">
      <h4>Account <span className="muted">(optional)</span></h4>
      <p className="muted">OpenSubtitles allows 5 downloads a day without an account, 20 a day with a free{" "}
        <a href="https://www.opensubtitles.com/en/users/sign_up" target="_blank" rel="noreferrer">account</a>, more with
        VIP. Sign in here so this server downloads with yours. Searching never counts.</p>
      {st.error && <p className="key-msg bad">{st.error}</p>}
      {st.user && !editing ? (
        <div className="key-row">
          <code className="key-saved">{st.user}</code>
          <span className="muted">
            {[acc?.level, acc?.vip ? "VIP" : null,
              acc?.allowed_downloads != null ? `${acc.allowed_downloads} downloads a day` : null].filter(Boolean).join(" · ")}
          </span>
          <span className="spacer" />
          <button className="btn ghost small" onClick={() => { setEditing(true); setUser(st.user ?? ""); setMsg(null); }}>
            <Icon name="edit" size={16} /> Change
          </button>
          <button className="btn ghost small danger" onClick={signOut}>Sign out</button>
        </div>
      ) : (
        <form className="key-form" onSubmit={(e) => { e.preventDefault(); save(); }}>
          <input className="text-input" value={user} onChange={(e) => { setUser(e.target.value); setMsg(null); }}
            placeholder="OpenSubtitles user name" aria-label="OpenSubtitles user name" autoComplete="off" spellCheck={false} />
          <PasswordInput className="text-input" value={password} onChange={(e) => { setPassword(e.target.value); setMsg(null); }}
            placeholder="Password" aria-label="OpenSubtitles password" autoComplete="new-password" />
          <button type="submit" className="btn primary small" disabled={!user.trim() || !password || busy}>
            {busy ? "Signing in…" : "Sign in"}</button>
          {editing && (
            <button type="button" className="btn ghost small" onClick={() => { setEditing(false); setPassword(""); setMsg(null); }}>
              Cancel</button>
          )}
        </form>
      )}
      {msg && <p className={`key-msg ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
      <p className="fine-print">The key and password are kept in this server's database, like the TMDB key, so the
        server can sign in again each day. Subtitles from OpenSubtitles.com.</p>
    </div>
  );
}

/** A copy of each downloaded subtitle next to its video ("Episode.en.srt"), so other players (Jellyfin, VLC...) have
 *  it too. On by default (owner, 2026-10-12); the only thing BAMS ever writes in your media folders, and it never
 *  overwrites, renames or deletes anything there. */
function SaveBeside({ st, setSt }: { st: OpenSubtitlesStatus; setSt: (s: OpenSubtitlesStatus) => void }) {
  const [check, setCheck] = useState<SaveCheck | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!st.save_beside) return setCheck(null);
    api.get<SaveCheck>("/api/settings/opensubtitles-save").then(setCheck).catch((e) => setErr(e.message));
  }, [st.save_beside]);

  const toggle = async () => {
    setErr(null);
    try {
      setSt(await api.put<OpenSubtitlesStatus>("/api/settings/opensubtitles-save", { enabled: !st.save_beside }));
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  const copy = (text: string) => {
    navigator.clipboard?.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000); },
      () => {});
  };

  const blocked = check?.roots.filter((r) => r.exists && r.writable === false) ?? [];
  return (
    <div className="os-account">
      <h4>Copies next to your videos</h4>
      <p className="muted">Each subtitle you download is also saved next to its video, for example{" "}
        <code>Episode name.en.srt</code>, so other players such as Jellyfin or VLC find it too. This is the only thing
        BAMS ever writes in your media folders: it only adds new subtitle files and never changes, renames or deletes
        anything there (a second English one becomes <code>.en.2.srt</code>). Removing a subtitle in BAMS leaves its copy.</p>
      <div className="key-row">
        <button className={`btn small ${st.save_beside ? "ghost" : "primary"}`} onClick={toggle}>
          {st.save_beside ? "Turn off" : "Turn on"}</button>
        <span className="muted">{st.save_beside ? "On: copies are saved next to the videos." : "Off: downloads stay inside BAMS only."}</span>
      </div>
      {st.save_beside && check && check.roots.length > 0 && (
        <ul className="os-folders">
          {check.roots.map((r) => (
            <li key={r.path}><code>{r.path}</code>{" "}
              {!r.exists ? <span className="root-badge bad">offline / not found</span>
                : r.writable === false ? <span className="root-badge warn">BAMS can't save here</span>
                : r.writable ? <span className="root-badge ok">can save here</span>
                : <span className="muted">(Windows: depends on the service account's permissions)</span>}
            </li>
          ))}
        </ul>
      )}
      {st.save_beside && blocked.length > 0 && (check?.fix ? (
        <div className="os-fix">
          <p className="muted">This Linux server only lets BAMS write in its own data folder. To allow subtitle copies
            in the folders above, run this once in a terminal on the server (it asks for your password):</p>
          <pre><code>{check.fix}</code></pre>
          <button className="btn ghost small" onClick={() => copy(check.fix!)}>{copied ? "Copied" : "Copy command"}</button>
        </div>
      ) : (
        <p className="muted">The account BAMS runs as isn't allowed to write in those folders. Give it write permission
          there, or turn this off.</p>
      ))}
      {st.save_beside && st.save_error && (
        <p className="key-msg warn">Last copy not saved{st.save_error.folder ? ` in ${st.save_error.folder}` : ""}:{" "}
          {st.save_error.why}</p>
      )}
      {err && <p className="key-msg bad">{err}</p>}
    </div>
  );
}
