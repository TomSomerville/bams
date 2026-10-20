import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import Icon from "./Icon";
import PasswordInput from "./PasswordInput";

// Switch account (sidebar, above Settings): the accounts signed in on this browser, to swap between with no password.
// The server keeps the other accounts' sessions in an HttpOnly cookie: this page never sees a token.

type Account = { id: number; name: string; is_admin: boolean; current: boolean };

/** Start the app afresh as whoever is current now (their home, their settings, their servers). */
const restart = () => window.location.assign("/");

export function AccountsButton() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className="nav-item" onClick={() => setOpen(true)} title={`Signed in as ${user.name}: switch account`}>
        <Icon name="users" /> <span>{user.name}</span>
      </button>
      {open && <Accounts onClose={() => setOpen(false)} />}
    </>
  );
}

function Accounts({ onClose }: { onClose: () => void }) {
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const load = () => api.get<Account[]>("/api/auth/accounts").then(setAccounts).catch((e) => setErr((e as Error).message));
  useEffect(() => { void load(); }, []);

  const switchTo = async (a: Account) => {
    setErr(null);
    try {
      await api.post("/api/auth/switch", { user_id: a.id });
      restart();
    } catch (e) {
      setErr((e as Error).message);
      void load();
    }
  };
  const remove = async (a: Account) => {
    setErr(null);
    await api.del(`/api/auth/accounts/${a.id}`).catch((e) => setErr((e as Error).message));
    void load();
  };

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal accounts" role="dialog" aria-modal="true" aria-label="Switch account">
        <div className="modal-head">
          <h3>{adding ? "Add an account" : "Switch account"}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="close" size={20} /></button>
        </div>
        {err && <p className="key-msg bad">{err}</p>}
        {adding ? <AddAccount onCancel={() => setAdding(false)} /> : <>
          <ul className="account-list">
            {accounts?.map((a) => (
              <li key={a.id} className={a.current ? "on" : ""}>
                <button className="account-pick" disabled={a.current} onClick={() => void switchTo(a)}>
                  <span className="account-avatar">{a.name.slice(0, 1).toUpperCase()}</span>
                  <span className="account-name">{a.name}</span>
                  {a.is_admin && <span className="muted">admin</span>}
                  {a.current && <span className="muted">· now</span>}
                </button>
                {!a.current && (
                  <button className="icon-btn" onClick={() => void remove(a)} aria-label={`Sign ${a.name} out of this browser`}
                    title="Sign out of this browser"><Icon name="close" size={16} /></button>
                )}
              </li>
            ))}
          </ul>
          <p className="muted accounts-note">Accounts signed in here switch with no password. Signing out (Settings) moves to
            the next one.</p>
          <div className="modal-foot">
            <button className="btn ghost small" onClick={() => setAdding(true)} disabled={!accounts || accounts.length >= 5}>
              <Icon name="plus" size={16} /> Add account</button>
          </div>
        </>}
      </div>
    </div>
  );
}

function AddAccount({ onCancel }: { onCancel: () => void }) {
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [askCode, setAskCode] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await api.post("/api/auth/accounts", { name: name.trim(), password, ...(askCode ? { code: code.replace(/\s/g, "") } : {}) });
      restart();
    } catch (e) {
      if (e instanceof ApiError && e.data?.code_required) {
        setErr(askCode ? e.message : null);
        setAskCode(true);
        setCode("");
      } else setErr((e as Error).message);
      setBusy(false);
    }
  };

  return (
    <form className="gate-form accounts-form" onSubmit={submit}>
      <label htmlFor="a-name">Name</label>
      <input id="a-name" className="text-input" value={name} onChange={(e) => { setName(e.target.value); setAskCode(false); }}
        autoComplete="off" autoFocus required maxLength={40} />
      <label htmlFor="a-pw">Password</label>
      <PasswordInput id="a-pw" className="text-input" value={password} onChange={(e) => setPassword(e.target.value)}
        autoComplete="off" required />
      {askCode && <>
        <label htmlFor="a-code">Code from the authenticator app</label>
        <input id="a-code" className="text-input code-input" value={code} onChange={(e) => setCode(e.target.value)}
          inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]*" maxLength={7} placeholder="123456" autoFocus required />
      </>}
      {err && <p className="key-msg bad">{err}</p>}
      <div className="accounts-actions">
        <button type="button" className="btn ghost" onClick={onCancel}>Back</button>
        <button className="btn primary" disabled={busy || !name.trim() || !password || (askCode && code.replace(/\s/g, "").length !== 6)}>
          {busy ? "One moment…" : "Sign in and switch"}</button>
      </div>
    </form>
  );
}
