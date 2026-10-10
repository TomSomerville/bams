// Settings: other BAMS servers this browser is connected to (servers.tsx). The web app is a client: each browser
// keeps its own list, signed in to each server with an account there; its libraries can be renamed and hidden here.

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useLocation } from "react-router-dom";
import type { RemoteLibrary, RemoteServer } from "../api";
import { LIB_TYPES } from "../format";
import { connectServer, removeServer, setLibrary, useRemotes } from "../servers";
import Icon from "./Icon";
import PasswordInput from "./PasswordInput";

/** Connect to a server (or sign in to one again): its address and an account there. */
export function ConnectServer({ again, onDone, onCancel }: {
  /** signing in again to this connection */
  again?: RemoteServer; onDone: () => void; onCancel: () => void;
}) {
  const [address, setAddress] = useState(again?.url ?? "");
  const [name, setName] = useState(again?.account ?? "");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await connectServer(again?.url ?? address, name, password);
      onDone();
    } catch (er) {
      setErr((er as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="lib-card add-lib" onSubmit={submit}>
      <div className="lib-head"><h3>{again ? `Sign in to ${again.name} again` : "Connect to another BAMS server"}</h3></div>
      <div className="form-grid">
        <label htmlFor="rs-address">Address</label>
        <div>
          <input id="rs-address" className="text-input" value={address} onChange={(e) => setAddress(e.target.value)}
            placeholder="192.168.1.2 or media.example.com" autoFocus={!again} disabled={!!again}
            autoComplete="off" spellCheck={false} />
          <p className="fine-print">The IP address or domain name of a computer running BAMS. Add the port if it isn't
            8484 (<code>host:9000</code>), or a full address (<code>https://…</code>).</p>
        </div>
        <label htmlFor="rs-name">Account</label>
        <input id="rs-name" className="text-input" value={name} onChange={(e) => setName(e.target.value)}
          autoComplete="off" autoFocus={!!again} />
        <label htmlFor="rs-password">Password</label>
        <div>
          <PasswordInput id="rs-password" className="text-input" value={password} autoComplete="off"
            onChange={(e) => setPassword(e.target.value)} />
          <p className="fine-print">An account on that server, not this one. What you watch there counts for that
            account. Your password isn't kept: this browser signs in once and keeps the sign-in, like the TV app.
            Each browser and TV has its own list of servers.</p>
        </div>
      </div>
      {err && <p className="key-msg bad">{err}</p>}
      <div className="lib-foot">
        <span className="spacer" />
        <button type="button" className="btn ghost small" onClick={onCancel}>Cancel</button>
        <button className="btn primary small" disabled={busy || !address.trim() || !name.trim() || !password}>
          {busy ? "Connecting…" : again ? "Sign in" : "Connect"}
        </button>
      </div>
    </form>
  );
}

/** One of the other server's libraries: rename it (here only) and show/hide it in the sidebar. */
function RemoteLibraryRow({ server, lib }: { server: RemoteServer; lib: RemoteLibrary }) {
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(lib.name);
  const save = (body: { name?: string; show?: boolean }) => setLibrary(server.id, lib.id, body);

  return (
    <div className="remote-lib">
      <Icon name={LIB_TYPES[lib.type].icon} size={18} />
      {renaming ? (
        <form className="rename" onSubmit={(e) => { e.preventDefault(); save({ name: name.trim() }); setRenaming(false); }}>
          <input value={name} onChange={(e) => setName(e.target.value)} autoFocus aria-label="Library name"
            placeholder={lib.own_name} />
          <button className="btn primary small">Save</button>
          <button type="button" className="btn ghost small" onClick={() => { setRenaming(false); setName(lib.name); }}>Cancel</button>
        </form>
      ) : (
        <>
          <span className="remote-lib-name">{lib.name}</span>
          {lib.name !== lib.own_name && <span className="muted">({lib.own_name} on {server.name})</span>}
          <button className="icon-btn subtle" onClick={() => setRenaming(true)} title="Rename (only here)"
            aria-label={`Rename ${lib.name}`}><Icon name="edit" size={15} /></button>
          {lib.name !== lib.own_name && (
            <button className="link-btn" onClick={() => { setName(lib.own_name); save({ name: "" }); }}>Use its own name</button>
          )}
        </>
      )}
      <label className="check remote-lib-show">
        <input type="checkbox" checked={lib.show} onChange={(e) => save({ show: e.target.checked })}
          aria-label={`Show ${lib.name} in the sidebar`} />
        Show in sidebar
      </label>
    </div>
  );
}

function RemoteCard({ s }: { s: RemoteServer }) {
  const [again, setAgain] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const disconnect = () => removeServer(s.id);

  if (again) return <ConnectServer again={s} onDone={() => setAgain(false)} onCancel={() => setAgain(false)} />;
  return (
    <div className="lib-card">
      <div className="lib-head">
        <Icon name="server" size={22} />
        <h3>{s.name}</h3>
        {!s.signed_in ? <span className="root-badge warn">signed out</span>
          : !s.online && <span className="root-badge bad">can't reach it{s.error && s.error !== "offline" ? ` (${s.error})` : ""}</span>}
        <span className="muted lib-counts">{s.url} · signed in as {s.account}{s.is_admin ? " (admin there)" : ""}</span>
      </div>
      <div className="remote-libs">
        {s.libraries.map((l) => <RemoteLibraryRow key={l.id} server={s} lib={l} />)}
        {!s.libraries.length && <p className="muted">{s.online ? "This server has no libraries yet." : "Its libraries show once it can be reached."}</p>}
      </div>
      {!s.signed_in && <p className="key-msg warn">{s.name} no longer accepts this browser's sign-in (signed out there,
        or the password changed). Sign in again to see its libraries.</p>}
      <div className="lib-foot">
        <span className="spacer" />
        {confirm ? (
          <span className="confirm">
            Disconnect from {s.name}? Nothing on it changes.
            <button className="btn ghost small danger" onClick={disconnect}>Disconnect</button>
            <button className="btn ghost small" onClick={() => setConfirm(false)}>Cancel</button>
          </span>
        ) : (
          <>
            <button className="btn ghost small danger" onClick={() => setConfirm(true)}>Disconnect</button>
            <button className="btn ghost small" onClick={() => setAgain(true)}><Icon name="refresh" size={16} /> Sign in again</button>
          </>
        )}
      </div>
    </div>
  );
}

/** This browser's other servers. `connecting`: the connect form is open (the button may sit elsewhere). */
export function RemoteServers({ connecting, setConnecting }: { connecting: boolean; setConnecting: (c: boolean) => void }) {
  const { servers } = useRemotes();
  const { hash } = useLocation();
  const list = useRef<HTMLDivElement>(null);
  const loaded = servers !== null;
  useEffect(() => {  // the sidebar's "offline" / "signed out" badge links here
    if (hash !== "#servers" || !loaded) return;
    // after App's scroll-to-top for the new page (a parent's effect runs after this one)
    const t = window.setTimeout(() => list.current?.scrollIntoView({ behavior: "smooth", block: "center" }), 50);
    return () => window.clearTimeout(t);
  }, [hash, loaded]);
  return (
    <div className="lib-list" ref={list}>
      {connecting && <ConnectServer onDone={() => setConnecting(false)} onCancel={() => setConnecting(false)} />}
      {servers?.map((s) => <RemoteCard key={s.id} s={s} />)}
      {servers && !servers.length && !connecting && (
        <p className="muted">Not connected to any other BAMS server. Connect to one to see its libraries in your sidebar,
          next to these.</p>
      )}
    </div>
  );
}
