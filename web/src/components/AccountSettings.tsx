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
      <TwoFactor />
    </section>
  );
}

/** The QR code as SVG markup. The library is loaded only when someone sets up two-step sign-in. */
async function qrSvg(text: string): Promise<string> {
  const qrcode = (await import("qrcode-generator")).default;
  const q = qrcode(0, "M");
  q.addData(text);
  q.make();
  return q.createSvgTag({ cellSize: 4, margin: 2, scalable: true });
}

/** Two-step sign-in: after the password, a code from an authenticator app (Google Authenticator, Microsoft
 *  Authenticator, 1Password…). Server: auth.py TOTP, /api/auth/2fa. */
function TwoFactor() {
  const { user, refresh } = useAuth();
  const [setup, setSetup] = useState<{ secret: string; uri: string; qr: string } | null>(null);
  const [turningOff, setTurningOff] = useState(false);
  const [code, setCode] = useState("");
  const [pw, setPw] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const on = !!user.two_factor;
  const digits = code.replace(/\s/g, "");

  const reset = () => { setSetup(null); setTurningOff(false); setCode(""); setPw(""); };
  const run = async (f: () => Promise<unknown>, done: string) => {
    setBusy(true);
    setMsg(null);
    try {
      await f();
      reset();
      setMsg({ ok: true, text: done });
      await refresh();
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };
  const start = async () => {
    setMsg(null);
    try {
      const s = await api.post<{ secret: string; uri: string }>("/api/auth/2fa/setup");
      setSetup({ ...s, qr: await qrSvg(s.uri) });
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    }
  };

  return (
    <div className="two-factor">
      <div className="user-line">
        <strong>Two-step sign-in</strong>
        <span className={`status-pill ${on ? "ok" : ""}`}>{on ? "On" : "Off"}</span>
        <span className="spacer" />
        {!on && !setup && <button className="btn small ghost" onClick={start}>Turn on</button>}
        {on && !turningOff && <button className="btn small ghost" onClick={() => { setTurningOff(true); setMsg(null); }}>Turn off</button>}
      </div>
      <p className="muted">{on
        ? "Signing in asks for your password and then a code from your authenticator app."
        : "After your password, BAMS also asks for a code from an app on your phone, such as Google Authenticator, so a password alone isn't enough."}</p>
      {setup && (
        <form className="two-factor-setup" onSubmit={(e) => {
          e.preventDefault();
          run(() => api.post("/api/auth/2fa", { secret: setup.secret, code: digits, password: pw }),
            "Two-step sign-in is on. Next time you sign in, have your phone ready.");
        }}>
          <div className="qr" role="img" aria-label="QR code for your authenticator app"
            dangerouslySetInnerHTML={{ __html: setup.qr }} />
          <div className="two-factor-steps">
            <ol>
              <li>In Google Authenticator, tap <strong>+</strong>, then <strong>Scan a QR code</strong>, and scan this one.</li>
              <li>Can't scan it? Choose <strong>Enter a setup key</strong> instead and type{" "}
                <code className="setup-key">{setup.secret.match(/.{1,4}/g)?.join(" ")}</code> (time based).</li>
              <li>Type the 6-digit code the app now shows for BAMS, and your password.</li>
            </ol>
            <div className="key-row">
              <input className="text-input code-input" placeholder="123456" value={code} onChange={(e) => setCode(e.target.value)}
                inputMode="numeric" autoComplete="one-time-code" maxLength={7} aria-label="Code from the app" />
              <PasswordInput className="text-input" placeholder="Your password" value={pw} onChange={(e) => setPw(e.target.value)}
                autoComplete="current-password" aria-label="Your password" />
              <button className="btn small primary" disabled={busy || digits.length !== 6 || !pw}>Turn on</button>
              <button type="button" className="btn small ghost" onClick={reset}>Cancel</button>
            </div>
          </div>
        </form>
      )}
      {turningOff && (
        <form className="key-row" onSubmit={(e) => {
          e.preventDefault();
          run(() => api.post("/api/auth/2fa/off", { password: pw }), "Two-step sign-in is off. Your password alone signs you in.");
        }}>
          <PasswordInput className="text-input" placeholder="Your password" value={pw} onChange={(e) => setPw(e.target.value)}
            autoComplete="current-password" aria-label="Your password" autoFocus />
          <button className="btn small primary" disabled={busy || !pw}>Turn off two-step sign-in</button>
          <button type="button" className="btn small ghost" onClick={reset}>Cancel</button>
        </form>
      )}
      {msg && <p className={`key-msg ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
    </div>
  );
}

function UserRow({ u, me, onChange }: { u: User; me: User; onChange: () => void }) {
  const [resetting, setResetting] = useState(false);
  const [pw, setPw] = useState("");
  const [mustChange, setMustChange] = useState(true);
  const [confirm, setConfirm] = useState(false);
  const [confirm2fa, setConfirm2fa] = useState(false);
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
        {u.two_factor && <span className="tag" title="Signs in with a password and an authenticator app's code">Two-step</span>}
        <span className="spacer" />
        {u.id !== me.id && (
          <button className="btn ghost small" onClick={() => run(() => api.patch(`/api/users/${u.id}`, { is_admin: !u.is_admin }))}>
            {u.is_admin ? "Make viewer" : "Make admin"}
          </button>
        )}
        {u.id !== me.id && <button className="btn ghost small" onClick={() => setResetting(!resetting)}>New password</button>}
        {u.id !== me.id && u.two_factor && (confirm2fa ? (
          <span className="confirm">
            Turn off {u.name}'s two-step sign-in?
            <button className="btn ghost small danger" onClick={() => run(() => api.del(`/api/users/${u.id}/2fa`)).then(() => setConfirm2fa(false))}>Turn off</button>
            <button className="btn ghost small" onClick={() => setConfirm2fa(false)}>Cancel</button>
          </span>
        ) : <button className="btn ghost small" title="For a lost phone: they sign in with their password alone and can set it up again"
          onClick={() => setConfirm2fa(true)}>Turn off two-step</button>)}
        {u.id !== me.id && (confirm ? (
          <span className="confirm">
            Remove {u.name} and their watch history?
            <button className="btn ghost small danger" onClick={() => run(() => api.del(`/api/users/${u.id}`))}>Remove</button>
            <button className="btn ghost small" onClick={() => setConfirm(false)}>Cancel</button>
          </span>
        ) : <button className="btn ghost small danger" onClick={() => setConfirm(true)}>Remove</button>)}
      </div>
      {u.id !== me.id && (
        <label className="check must-change">
          <input type="checkbox" checked={!!u.must_change_password}
            onChange={(e) => run(() => api.patch(`/api/users/${u.id}`, { must_change_password: e.target.checked }))} />
          Must change password at next sign-in
          {u.must_change_password && <span className="muted">(signed out; they pick their own password when they sign in)</span>}
        </label>
      )}
      {resetting && (
        <form className="key-row" onSubmit={(e) => {
          e.preventDefault();
          run(() => api.patch(`/api/users/${u.id}`, { password: pw, must_change_password: mustChange }))
            .then(() => { setPw(""); setResetting(false); });
        }}>
          <PasswordInput className="text-input" placeholder="New password (8+ characters)" value={pw}
            onChange={(e) => setPw(e.target.value)} autoComplete="new-password" aria-label={`New password for ${u.name}`} />
          <label className="check"><input type="checkbox" checked={mustChange} onChange={(e) => setMustChange(e.target.checked)} />
            Must change at next sign-in</label>
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
  const [mustChange, setMustChange] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const load = () => api.get<User[]>("/api/users").then(setUsers).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  const add = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    try {
      await api.post("/api/users", { name: name.trim(), password: pw, is_admin: admin, must_change_password: mustChange });
      setName("");
      setPw("");
      setAdmin(false);
      setMustChange(true);
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
          <label className="check"><input type="checkbox" checked={mustChange} onChange={(e) => setMustChange(e.target.checked)} />
            Must change password at first sign-in</label>
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
