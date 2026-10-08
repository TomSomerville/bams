// Who is signed in. Until someone is, the app shows only the sign-in screen (or, on a brand-new server
// opened on the server itself, the "create the admin account" screen).
import { createContext, useCallback, useContext, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { api, SIGNED_OUT, type AuthState, type Prefs, type User } from "./api";
import PasswordInput from "./components/PasswordInput";

type Auth = {
  user: User;
  signOut: () => Promise<void>;
  /** after a password change, etc. */
  refresh: () => Promise<void>;
  /** this account's display preferences (saved on the server, so they follow you to other devices) */
  prefs: Prefs;
  setPrefs: (p: Partial<Prefs>) => Promise<void>;
};

const DEFAULT_PREFS: Prefs = { home_hero: true };

const Ctx = createContext<Auth | null>(null);

export function useAuth(): Auth {
  const a = useContext(Ctx);
  if (!a) throw new Error("useAuth outside AuthProvider");
  return a;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState | null>(null);
  const [down, setDown] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setState(await api.get<AuthState>("/api/auth/state"));
      setDown(false);
    } catch {
      setDown(true);
    }
  }, []);

  useEffect(() => {
    refresh();
    const out = () => setState((s) => (s && s.user ? { ...s, user: null } : s));
    window.addEventListener(SIGNED_OUT, out);
    return () => window.removeEventListener(SIGNED_OUT, out);
  }, [refresh]);

  const setPrefs = useCallback(async (p: Partial<Prefs>) => {
    const prefs = await api.put<Prefs>("/api/me/prefs", p);
    setState((s) => (s && s.user ? { ...s, user: { ...s.user, prefs } } : s));
  }, []);

  const signOut = useCallback(async () => {
    await api.post("/api/auth/logout").catch(() => {});
    setState((s) => s && { ...s, user: null });
  }, []);

  if (!state) {
    return down ? <Gate><p className="key-msg bad">Can't reach the BAMS server. Start it with <code>python -m bams serve</code>.</p>
      <button className="btn ghost small" onClick={refresh}>Try again</button></Gate> : <div className="gate" />;
  }
  if (!state.user) return <SignIn state={state} onDone={refresh} />;
  // keyed by user: signing in as someone else starts the app afresh (their watch state, their settings)
  return <Ctx.Provider key={state.user.id} value={{ user: state.user, signOut, refresh, prefs: { ...DEFAULT_PREFS, ...state.user.prefs }, setPrefs }}>{children}</Ctx.Provider>;
}

function Gate({ children }: { children: ReactNode }) {
  return (
    <div className="gate">
      <div className="gate-card">
        <img className="gate-logo" src="/brand/bams-wordmark.png" alt="BAMS — Bad Ass Media Server" />
        {children}
      </div>
    </div>
  );
}

function SignIn({ state, onDone }: { state: AuthState; onDone: () => void }) {
  const setup = state.setup;
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (setup && !state.setup_here) {
    return (
      <Gate>
        <h1>Welcome to BAMS</h1>
        <p className="muted">This server has no accounts yet. For safety, the first (admin) account can only be created
          on the server itself: open <code>http://localhost:8484</code> there, or run
          <code>bams user add YOUR-NAME --admin</code> on it.</p>
      </Gate>
    );
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (setup && password !== again) return setErr("The two passwords don't match.");
    setBusy(true);
    setErr(null);
    try {
      await api.post(setup ? "/api/auth/setup" : "/api/auth/login", { name: name.trim(), password });
      onDone();
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  };

  return (
    <Gate>
      <h1>{setup ? "Create your admin account" : "Sign in"}</h1>
      {setup && <p className="muted">You're the first one here. This account manages the libraries, settings and other
        people's accounts. Everyone else gets their own account later, from Settings.</p>}
      <form className="gate-form" onSubmit={submit}>
        <label htmlFor="g-name">Name</label>
        <input id="g-name" className="text-input" value={name} onChange={(e) => setName(e.target.value)}
          autoComplete="username" autoFocus required maxLength={40} />
        <label htmlFor="g-pw">Password</label>
        <PasswordInput id="g-pw" className="text-input" value={password} onChange={(e) => setPassword(e.target.value)}
          autoComplete={setup ? "new-password" : "current-password"} required minLength={setup ? 8 : undefined} />
        {setup && <>
          <label htmlFor="g-pw2">Password again</label>
          <PasswordInput id="g-pw2" className="text-input" value={again} onChange={(e) => setAgain(e.target.value)}
            autoComplete="new-password" required />
        </>}
        {err && <p className="key-msg bad">{err}</p>}
        <button className="btn primary" disabled={busy || !name.trim() || !password}>
          {busy ? "One moment…" : setup ? "Create account" : "Sign in"}
        </button>
      </form>
      {!setup && <p className="fine-print">Forgot your password? An admin can set a new one in Settings → Accounts.</p>}
    </Gate>
  );
}
