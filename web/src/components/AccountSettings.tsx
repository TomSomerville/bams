import { useEffect, useRef, useState, type FormEvent } from "react";
import { useLocation } from "react-router-dom";
import { api, type User } from "../api";
import { useAuth } from "../auth";
import Icon from "./Icon";
import PasswordInput from "./PasswordInput";

/** Your own account: who you are, a new password, signing out. */
export function AccountSettings() {
  const { user, signOut, refresh } = useAuth();
  const { hash } = useLocation();
  const card = useRef<HTMLElement>(null);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (hash === "#account") card.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [hash]);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (next !== again) return setMsg({ ok: false, text: "The two new passwords don't match." });
    setBusy(true);
    setMsg(null);
    try {
      await api.put("/api/auth/password", { current, new: next });
      setCurrent("");
      setNext("");
      setAgain("");
      setMsg({ ok: true, text: "Password changed. Other devices signed in as you have been signed out." });
      refresh();
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section ref={card} className="lib-card settings-card" id="account">
      <div className="lib-head">
        <h3>{user.name}</h3>
        <span className="status-pill ok">{user.is_admin ? "Admin" : "Viewer"}</span>
      </div>
      <p className="muted">Your watch history (what you've watched, where you stopped) belongs to this account.</p>
      <form className="key-row" onSubmit={save}>
        <PasswordInput className="text-input" placeholder="Current password" value={current}
          onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" aria-label="Current password" />
        <PasswordInput className="text-input" placeholder="New password (8+ characters)" value={next}
          onChange={(e) => { setNext(e.target.value); setMsg(null); }} autoComplete="new-password" aria-label="New password" />
        <PasswordInput className="text-input" placeholder="New password again" value={again}
          onChange={(e) => { setAgain(e.target.value); setMsg(null); }} autoComplete="new-password" aria-label="Confirm new password" />
        <button className="btn small primary" disabled={busy || !current || next.length < 8 || !again}>Change password</button>
        <span className="spacer" />
        <button type="button" className="btn small ghost" onClick={signOut}>Sign out</button>
      </form>
      {msg && <p className={`key-msg ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
    </section>
  );
}

function UserRow({ u, me, onChange }: { u: User; me: User; onChange: () => void }) {
  const [resetting, setResetting] = useState(false);
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = async (f: () => Promise<unknown>) => {
    setErr(null);
    try {
      await f();
      onChange();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <li className="user-row">
      <div className="user-line">
        <span className="avatar small">{u.name.slice(0, 1).toUpperCase()}</span>
        <strong>{u.name}</strong>
        {u.id === me.id && <span className="muted">(you)</span>}
        <span className="tag">{u.is_admin ? "Admin" : "Viewer"}</span>
        <span className="spacer" />
        {u.id !== me.id && (
          <button className="btn ghost small" onClick={() => run(() => api.patch(`/api/users/${u.id}`, { is_admin: !u.is_admin }))}>
            {u.is_admin ? "Make viewer" : "Make admin"}
          </button>
        )}
        {u.id !== me.id && <button className="btn ghost small" onClick={() => setResetting(!resetting)}>New password</button>}
        {u.id !== me.id && (confirm ? (
          <span className="confirm">
            Remove {u.name} and their watch history?
            <button className="btn ghost small danger" onClick={() => run(() => api.del(`/api/users/${u.id}`))}>Remove</button>
            <button className="btn ghost small" onClick={() => setConfirm(false)}>Cancel</button>
          </span>
        ) : <button className="btn ghost small danger" onClick={() => setConfirm(true)}>Remove</button>)}
      </div>
      {resetting && (
        <form className="key-row" onSubmit={(e) => {
          e.preventDefault();
          run(() => api.patch(`/api/users/${u.id}`, { password: pw })).then(() => { setPw(""); setResetting(false); });
        }}>
          <PasswordInput className="text-input" placeholder="New password (8+ characters)" value={pw}
            onChange={(e) => setPw(e.target.value)} autoComplete="new-password" aria-label={`New password for ${u.name}`} />
          <button className="btn small primary" disabled={pw.length < 8}>Set password</button>
          <span className="muted">Signs {u.name} out everywhere.</span>
        </form>
      )}
      {err && <p className="key-msg bad">{err}</p>}
    </li>
  );
}

/** Admins: everyone's accounts. */
export function UsersSettings() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<User[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [pw, setPw] = useState("");
  const [admin, setAdmin] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = () => api.get<User[]>("/api/users").then(setUsers).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  const add = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    try {
      await api.post("/api/users", { name: name.trim(), password: pw, is_admin: admin });
      setName("");
      setPw("");
      setAdmin(false);
      setAdding(false);
      load();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <section className="lib-card settings-card">
      <div className="lib-head">
        <h3>Who can sign in</h3>
        {!adding && <button className="btn small primary push" onClick={() => setAdding(true)}><Icon name="plus" size={16} /> Add account</button>}
      </div>
      <p className="muted">Everyone who watches gets their own account, so each person has their own Continue
        Watching and watched list. Viewers can watch and download; admins can also change libraries, settings and
        accounts.</p>
      {adding && (
        <form className="key-row" onSubmit={add}>
          <input className="text-input" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)}
            autoFocus maxLength={40} aria-label="Name" />
          <PasswordInput className="text-input" placeholder="Password (8+ characters)" value={pw}
            onChange={(e) => setPw(e.target.value)} autoComplete="new-password" aria-label="Password" />
          <label className="check"><input type="checkbox" checked={admin} onChange={(e) => setAdmin(e.target.checked)} /> Admin</label>
          <button className="btn small primary" disabled={!name.trim() || pw.length < 8}>Add</button>
          <button type="button" className="btn small ghost" onClick={() => setAdding(false)}>Cancel</button>
        </form>
      )}
      {err && <p className="key-msg bad">{err}</p>}
      <ul className="user-list">
        {users?.map((u) => <UserRow key={u.id} u={u} me={me} onChange={load} />)}
      </ul>
    </section>
  );
}
