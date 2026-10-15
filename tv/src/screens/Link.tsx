import { useEffect, useRef, useState } from "react";
import qrcode from "qrcode-generator";
import { api, ApiError, getServer, linkWithWebUser, publicPostTo, setSession, webUser, type User } from "../api";
import { deviceWord, theatre } from "../platform";
import { focusFirst } from "../nav";
import { deviceName } from "../tizen";

type Start = { code: string; secret: string; expires_in: number };
type Poll = { status: "waiting" | "expired" | "linked"; token?: string; user?: User };

/** Sign this TV in: show a code to enter on a phone or computer (with a QR code that opens the page), or type a
 *  name and password with the remote. Server side: devices.py, /api/devices/link. `target`: another server being
 *  added to this TV (its token is handed back; the TV's first server and session stay as they are). */
export default function Link({ onLinked, onChangeServer, target }: {
  onLinked: () => void; onChangeServer: () => void;
  target?: { url: string; name: string; onDone: (token: string, user: User | null) => void };
}) {
  const [code, setCode] = useState<Start | null>(null);
  const [err, setErr] = useState<string | null>(null);
  // theatre mode (a PC with a keyboard) signs in with name and password only, no link code (owner, 2026-10-15)
  const codes = !theatre();
  const [withPassword, setWithPassword] = useState(!codes);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [code2, setCode2] = useState("");          // two-step sign-in: the authenticator app's code
  const [askCode, setAskCode] = useState(false);
  const [busy, setBusy] = useState(false);
  // theatre mode, opened from the web UI: the account signed in there, offered (never used silently: it may be an
  // admin, and a theatre box is better off with a viewer account)
  const [web, setWeb] = useState<User | null>(null);
  const alive = useRef(true);
  const linked = useRef(onLinked);  // App passes a new function every render: don't restart the code for that
  linked.current = onLinked;
  const server = target?.url ?? getServer() ?? "";
  const post = <T,>(p: string, b: unknown) => (target ? publicPostTo<T>(target.url, p, b) : api.publicPost<T>(p, b));
  const done = useRef((t: string, u: User | null) => { setSession(t, u); linked.current(); });
  if (target) done.current = target.onDone;

  // a code, then a poll every 3 s; a fresh code when it runs out
  useEffect(() => {
    alive.current = true;
    if (!codes) return () => { alive.current = false; };
    let timer: ReturnType<typeof setTimeout>;
    const begin = async () => {
      try {
        const s = await post<Start>("/api/devices/link", { name: deviceName() });
        if (!alive.current) return;
        setCode(s);
        setErr(null);
        poll(s);
      } catch (e) {
        if (!alive.current) return;
        setErr((e as Error).message);
        timer = setTimeout(begin, 10000);
      }
    };
    const poll = (s: Start) => {
      timer = setTimeout(async () => {
        try {
          const r = await post<Poll>("/api/devices/link/poll", { secret: s.secret });
          if (!alive.current) return;
          if (r.status === "linked" && r.token) {
            done.current(r.token, r.user ?? null);
          } else if (r.status === "expired") void begin();
          else poll(s);
        } catch {
          if (alive.current) poll(s);  // the server was briefly away; keep trying
        }
      }, 3000);
    };
    void begin();
    return () => {
      alive.current = false;
      clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    setTimeout(() => focusFirst());
  }, [withPassword, web]);

  useEffect(() => {
    if (!target) void webUser().then((u) => alive.current && setWeb(u));
  }, [target]);

  const linkWebAccount = async () => {
    setBusy(true);
    setErr(null);
    try {
      const r = await linkWithWebUser(deviceName());
      done.current(r.token, r.user);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const signIn = async () => {
    setBusy(true);
    setErr(null);
    try {
      const r = await post<{ token: string; user: User }>("/api/auth/token",
        { name, password, device: deviceName(), ...(askCode ? { code: code2.replace(/\s/g, "") } : {}) });
      done.current(r.token, r.user);
    } catch (e) {
      if (e instanceof ApiError && e.data?.code_required) {
        setErr(askCode ? e.message : null);
        setAskCode(true);
        setCode2("");
        setTimeout(() => (document.querySelector(".signin .code-input") as HTMLElement | null)?.focus());
      } else setErr(e instanceof ApiError ? e.message : "Couldn't sign in.");
    } finally {
      setBusy(false);
    }
  };

  const linkUrl = code ? `${server}/link?code=${code.code}` : "";
  const qr = code ? qrSvg(linkUrl) : "";

  if (withPassword) {
    return (
      <div className="center-screen link">
        <img className="wordmark" src="bams-wordmark.png" alt="BAMS" />
        <h1>{target ? `Sign in to ${target.name}` : "Sign in"}</h1>
        <form className="signin" onSubmit={(e) => { e.preventDefault(); void signIn(); }}>
          <input className="text-input" placeholder="Name" value={name} onChange={(e) => { setName(e.target.value); setAskCode(false); }} data-autofocus />
          <input className="text-input" type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
          {askCode && <input className="text-input code-input" inputMode="numeric" maxLength={7}
            placeholder="Code from your authenticator app" value={code2} onChange={(e) => setCode2(e.target.value)} />}
          <button className="btn primary" disabled={busy || !name || !password || (askCode && code2.replace(/\s/g, "").length !== 6)}>
            {busy ? "Signing in…" : "Sign in"}</button>
        </form>
        {err && <p className="error">{err}</p>}
        {web && (
          <button className="btn" disabled={busy} onClick={() => void linkWebAccount()}>
            Use {web.name}'s account (signed in on this browser)
          </button>
        )}
        {codes && <button className="btn ghost" onClick={() => { setErr(null); setWithPassword(false); }}>Use a code instead</button>}
        {!codes && target && <button className="btn ghost" onClick={onChangeServer}>Pick another server</button>}
      </div>
    );
  }

  return (
    <div className="center-screen link">
      <img className="wordmark" src="bams-wordmark.png" alt="BAMS" />
      <h1>{target ? `Link this ${deviceWord()} to ${target.name}` : `Link this ${deviceWord()} to your BAMS account`}</h1>
      <div className="link-body">
        <div className="link-steps">
          <p>On your phone, scan the code. Or on any computer, open</p>
          <p className="link-url">{server.replace(/^https?:\/\//, "")}/link</p>
          <p>sign in, and enter:</p>
          <div className="link-code">{code ? `${code.code.slice(0, 3)} ${code.code.slice(3)}` : "··· ···"}</div>
          <p className="muted small">The {deviceWord()} signs in by itself once the code is entered. A new code appears every ten minutes.</p>
        </div>
        {qr && <div className="qr" dangerouslySetInnerHTML={{ __html: qr }} />}
      </div>
      {err && <p className="error">{err}</p>}
      <div className="button-row">
        <button className="btn" data-autofocus onClick={() => { setErr(null); setWithPassword(true); }}>Sign in with name and password</button>
        <button className="btn ghost" onClick={onChangeServer}>{target ? "Pick another server" : "Change server"}</button>
      </div>
    </div>
  );
}

function qrSvg(text: string): string {
  const q = qrcode(0, "M");
  q.addData(text);
  q.make();
  return q.createSvgTag({ cellSize: 8, margin: 2, scalable: true });
}
