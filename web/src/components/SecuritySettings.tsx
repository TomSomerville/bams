import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  api, type AccountLock, type AuthLogEntry, type FlowEntry, type IpEntry, type IpLists, type NetflowStatus,
  type SecuritySettings as Shape,
} from "../api";
import { useAuth } from "../auth";
import FolderPicker from "./FolderPicker";
import Icon from "./Icon";

const when = (ts: number) => new Date(ts * 1000).toLocaleString();
const GB = 1024 ** 3;
const bytes = (b: number) => (b >= GB ? `${(b / GB).toFixed(2)} GB` : b >= 1024 ** 2 ? `${(b / 1024 ** 2).toFixed(1)} MB`
  : b >= 1024 ? `${(b / 1024).toFixed(1)} KB` : `${b} B`);
const waits = (n: number) => Array.from({ length: Math.max(0, n - 1) }, (_, i) => `${2 ** i}`).join(", ");

/** Settings -> Security: everything here is admin-only on the server too. */
export default function SecuritySettings() {
  const [s, setS] = useState<Shape | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => api.get<Shape>("/api/security").then(setS).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);

  if (err) return <p className="key-msg bad">{err}</p>;
  if (!s) return null;
  return (
    <div className="lib-list">
      <LockoutCard threshold={s.lockout_threshold} onSaved={load} />
      <AccountLocks />
      <IpCard lists={s.ip} yourIp={s.your_ip} onSaved={load} />
      <AuthLog />
      <TrafficLog status={s.netflow} onSaved={load} />
    </div>
  );
}

function LockoutCard({ threshold, onSaved }: { threshold: number; onSaved: () => void }) {
  const [n, setN] = useState(String(threshold));
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const v = Number(n);
  const valid = Number.isInteger(v) && v >= 1 && v <= 50;

  const save = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.put("/api/security/lockout", { threshold: v });
      setMsg({ ok: true, text: "Saved." });
      onSaved();
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    }
  };

  return (
    <section className="lib-card settings-card">
      <div className="lib-head"><h3>Wrong passwords</h3></div>
      <p className="muted">After each wrong password, that account has to wait before the next try: 1 second after the
        first, then twice as long after each one more. After this many wrong passwords in a row the account is locked
        until an admin unlocks it. A right password resets the count. This applies to every account, admins too.</p>
      <form className="watch-form" onSubmit={save}>
        <label htmlFor="lockout">Lock after</label>
        <span><input id="lockout" className="text-input num-input" type="number" min={1} max={50} step={1} value={n}
          onChange={(e) => { setN(e.target.value); setMsg(null); }} /> wrong passwords in a row</span>
        <span />
        <span><button className="btn small primary" disabled={!valid || v === threshold}>Save</button></span>
      </form>
      {!valid && <p className="key-msg bad">Between 1 and 50.</p>}
      {valid && v > 1 && <p className="fine-print">Waits before that: {waits(v)} seconds.</p>}
      {msg && <p className={`key-msg ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
      <p className="fine-print">If every admin is locked out, run <code>bams user unlock NAME</code> on the server.</p>
    </section>
  );
}

function AccountLocks() {
  const { user: me } = useAuth();
  const [rows, setRows] = useState<AccountLock[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => api.get<AccountLock[]>("/api/security/accounts").then(setRows)
    .catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);

  const lock = (u: AccountLock, locked: boolean) => {
    setErr(null);
    api.put(`/api/security/accounts/${u.id}/lock`, { locked }).then(load).catch((e) => setErr(e.message));
  };

  return (
    <section className="lib-card settings-card">
      <div className="lib-head">
        <h3>Account locks</h3>
        <button className="icon-btn subtle push" onClick={load} title="Refresh"><Icon name="refresh" size={16} /></button>
      </div>
      <p className="muted">A locked account can't sign in. Locking an account here also signs it out everywhere.</p>
      {err && <p className="key-msg bad">{err}</p>}
      <ul className="user-list">
        {rows?.map((u) => (
          <li key={u.id} className="user-row">
            <div className="user-line">
              <span className="avatar small">{u.name.slice(0, 1).toUpperCase()}</span>
              <strong>{u.name}</strong>
              {u.id === me.id && <span className="muted">(you)</span>}
              {u.locked
                ? <span className="root-badge bad">Locked {u.locked_by ? `by ${u.locked_by}` : "after wrong passwords"}
                  {u.locked_at ? ` · ${when(u.locked_at)}` : ""}</span>
                : u.failures > 0 && <span className="root-badge warn">{u.failures} wrong password{u.failures === 1 ? "" : "s"}
                  {u.wait_until ? ` · waiting until ${new Date(u.wait_until * 1000).toLocaleTimeString()}` : ""}</span>}
              <span className="spacer" />
              {u.locked
                ? <button className="btn ghost small" onClick={() => lock(u, false)}>Unlock</button>
                : u.id !== me.id && <button className="btn ghost small danger" onClick={() => lock(u, true)}>Lock</button>}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function IpListEditor({ title, entries, onChange, hint }: {
  title: string; entries: IpEntry[]; onChange: (e: IpEntry[]) => void; hint: string;
}) {
  const [cidr, setCidr] = useState("");
  const [note, setNote] = useState("");
  const add = (e: FormEvent) => {
    e.preventDefault();
    if (!cidr.trim()) return;
    onChange([...entries, { cidr: cidr.trim(), note: note.trim() }]);
    setCidr("");
    setNote("");
  };
  return (
    <div className="ip-list">
      <h4>{title} <span className="muted">({entries.length})</span></h4>
      <p className="fine-print">{hint}</p>
      {entries.length > 0 && (
        <ul>
          {entries.map((e, i) => (
            <li key={`${e.cidr}-${i}`}>
              <code>{e.cidr}</code>{e.note && <span className="muted">{e.note}</span>}
              <span className="spacer" />
              <button className="icon-btn subtle" title="Remove" aria-label={`Remove ${e.cidr}`}
                onClick={() => onChange(entries.filter((_, j) => j !== i))}><Icon name="close" size={15} /></button>
            </li>
          ))}
        </ul>
      )}
      <form className="key-row" onSubmit={add}>
        <input className="text-input" placeholder="192.168.1.20 or 192.168.1.0/24" value={cidr}
          onChange={(e) => setCidr(e.target.value)} aria-label={`Address for the ${title.toLowerCase()}`} maxLength={60} />
        <input className="text-input" placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)}
          aria-label="Note" maxLength={100} />
        <button className="btn small ghost" disabled={!cidr.trim()}><Icon name="plus" size={15} /> Add</button>
      </form>
    </div>
  );
}

function IpCard({ lists, yourIp, onSaved }: { lists: IpLists; yourIp: string; onSaved: () => void }) {
  const [draft, setDraft] = useState<IpLists>(lists);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => setDraft(lists), [lists]);
  const changed = JSON.stringify(draft) !== JSON.stringify(lists);
  const set = (p: Partial<IpLists>) => { setDraft({ ...draft, ...p }); setMsg(null); };

  const save = async () => {
    try {
      await api.put("/api/security/ip", draft);
      setMsg({ ok: true, text: "Saved. It applies to new requests straight away." });
      onSaved();
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    }
  };

  return (
    <section className="lib-card settings-card">
      <div className="lib-head"><h3>Who can connect</h3></div>
      <p className="muted">Addresses or ranges (IPv4 or IPv6, like <code>192.168.1.0/24</code>). The block list always
        wins. The server's own computer (localhost) is always let in, so you can't lock yourself out of it. Your address
        right now: <code>{yourIp}</code>.</p>
      <div className="segmented" role="radiogroup" aria-label="Who can connect">
        <button type="button" role="radio" aria-checked={draft.mode === "allow_all"} className={draft.mode === "allow_all" ? "on" : ""}
          onClick={() => set({ mode: "allow_all" })}>Allow everyone except the block list</button>
        <button type="button" role="radio" aria-checked={draft.mode === "allowlist"} className={draft.mode === "allowlist" ? "on" : ""}
          onClick={() => set({ mode: "allowlist" })}>Block everyone except the allow list</button>
      </div>
      <div className="ip-lists">
        <IpListEditor title="Block list" entries={draft.block} onChange={(block) => set({ block })}
          hint="Never let in, in either mode." />
        <IpListEditor title="Allow list" entries={draft.allow} onChange={(allow) => set({ allow })}
          hint={draft.mode === "allowlist" ? "Only these can connect." : "Used when you choose \"Block everyone except the allow list\"."} />
      </div>
      <div className="lib-foot">
        {draft.mode === "allowlist" && !draft.allow.some((e) => e.cidr === yourIp) && (
          <button className="btn ghost small" onClick={() => set({ allow: [...draft.allow, { cidr: yourIp, note: "added from Settings" }] })}>
            <Icon name="plus" size={15} /> Allow my address
          </button>
        )}
        <span className="spacer" />
        {changed && <button className="btn ghost small" onClick={() => { setDraft(lists); setMsg(null); }}>Undo changes</button>}
        <button className="btn primary small" disabled={!changed} onClick={save}>Save</button>
      </div>
      {msg && <p className={`key-msg ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
      <p className="fine-print">Behind a reverse proxy on another computer every visitor has the proxy's address, so lists
        can't tell them apart there. If they shut you out, run <code>bams security allow-all</code> on the server.</p>
    </section>
  );
}

const RESULTS = [["", "All"], ["ok", "Successful"], ["failed", "Failed"], ["admin", "Locks / unlocks"]] as const;

function AuthLog() {
  const [result, setResult] = useState("");
  const [rows, setRows] = useState<AuthLogEntry[]>([]);
  const [next, setNext] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async (before?: number) => {
    setErr(null);
    try {
      const q = new URLSearchParams({ limit: "50", ...(result ? { result } : {}), ...(before ? { before: String(before) } : {}) });
      const r = await api.get<{ entries: AuthLogEntry[]; next: number | null }>(`/api/security/auth-log?${q}`);
      setRows((old) => (before ? [...old, ...r.entries] : r.entries));
      setNext(r.next);
    } catch (e) {
      setErr((e as Error).message);
    }
  }, [result]);
  useEffect(() => { load(); }, [load]);

  return (
    <section className="lib-card settings-card">
      <div className="lib-head">
        <h3>Sign-in log</h3>
        <button className="icon-btn subtle push" onClick={() => load()} title="Refresh"><Icon name="refresh" size={16} /></button>
      </div>
      <p className="muted">Every sign-in, successful or not, and every lock and unlock. The newest 100,000 are kept.</p>
      <div className="segmented" role="radiogroup" aria-label="Show">
        {RESULTS.map(([v, label]) => (
          <button key={v} type="button" role="radio" aria-checked={result === v} className={result === v ? "on" : ""}
            onClick={() => setResult(v)}>{label}</button>
        ))}
      </div>
      {err && <p className="key-msg bad">{err}</p>}
      <div className="log-wrap">
        <table className="log-table">
          <thead><tr><th>When</th><th>Result</th><th>Name</th><th>Address</th><th>Details</th></tr></thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.id}>
                <td>{when(e.at)}</td>
                <td><span className={`root-badge ${e.result === "ok" ? "ok" : e.result === "failed" ? "bad" : "warn"}`}>
                  {e.event === "sign-in" ? (e.result === "ok" ? "Signed in" : "Failed") : e.event === "lock" ? "Locked" : "Unlocked"}
                </span></td>
                <td>{e.name ?? "—"}</td>
                <td><code>{e.ip ?? "—"}</code></td>
                <td title={e.user_agent ?? undefined}>{e.reason ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && !err && <p className="muted">Nothing logged yet.</p>}
      </div>
      {next && <button className="btn ghost small" onClick={() => load(next)}>Show older</button>}
    </section>
  );
}

function TrafficLog({ status, onSaved }: { status: NetflowStatus; onSaved: () => void }) {
  const [folder, setFolder] = useState(status.folder);
  const [gb, setGb] = useState(String(+(status.max_bytes / GB).toFixed(2)));
  const [picking, setPicking] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<FlowEntry[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { setFolder(status.folder); setGb(String(+(status.max_bytes / GB).toFixed(2))); }, [status]);
  const size = Math.round(Number(gb) * GB);
  const sizeOk = Number.isFinite(size) && size >= 10 * 1024 ** 2 && size <= 100 * 1024 ** 4;
  const changed = folder.trim() !== status.folder || size !== status.max_bytes;

  const save = async (body: { folder?: string; max_bytes?: number }) => {
    setMsg(null);
    try {
      await api.put("/api/security/netflow", body);
      setMsg({ ok: true, text: body.folder !== undefined && body.folder !== status.folder
        ? `Saved. New entries go to the new folder; files already written stay in ${status.folder}.` : "Saved." });
      onSaved();
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    }
  };

  const search = useCallback(async (before?: string) => {
    setBusy(true);
    try {
      const p = new URLSearchParams({ limit: "100", ...(q.trim() ? { q: q.trim() } : {}), ...(before ? { before } : {}) });
      const r = await api.get<{ entries: FlowEntry[]; next: string | null }>(`/api/security/netflow/entries?${p}`);
      setRows((old) => (before ? [...old, ...r.entries] : r.entries));
      setNext(r.next);
    } catch (e) {
      setMsg({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }, [q]);
  useEffect(() => { search(); }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <section className="lib-card settings-card">
      <div className="lib-head"><h3>Traffic log</h3></div>
      <p className="muted">Every request that reaches BAMS, blocked ones too: when, from which address and port, what
        was asked for, the answer, bytes each way, how long it took and who was signed in. When the log reaches its size
        limit the oldest entries are deleted.</p>
      <p className="muted">Now: {bytes(status.bytes)} in {status.files} file{status.files === 1 ? "" : "s"}
        {status.oldest ? `, since ${when(status.oldest)}` : ""}.
        {status.dropped > 0 && ` ${status.dropped} entries were skipped because the disk couldn't keep up.`}</p>
      <form className="watch-form" onSubmit={(e) => {
        e.preventDefault();
        save({ ...(folder.trim() !== status.folder ? { folder: folder.trim() } : {}), ...(size !== status.max_bytes ? { max_bytes: size } : {}) });
      }}>
        <label htmlFor="nf-folder">Folder</label>
        <span className="key-row tight">
          <input id="nf-folder" className="text-input wide" value={folder} onChange={(e) => { setFolder(e.target.value); setMsg(null); }} />
          <button type="button" className="btn ghost small" onClick={() => setPicking(true)}><Icon name="folder" size={15} /> Browse…</button>
          {status.custom && <button type="button" className="btn ghost small" onClick={() => save({ folder: "" })}>Use the default</button>}
        </span>
        <label htmlFor="nf-size">Size limit</label>
        <span><input id="nf-size" className="text-input num-input" type="number" min={0.01} step={0.01} value={gb}
          onChange={(e) => { setGb(e.target.value); setMsg(null); }} /> GB (all files together)</span>
        <span />
        <span><button className="btn small primary" disabled={!changed || !sizeOk || !folder.trim()}>Save</button></span>
      </form>
      {!sizeOk && <p className="key-msg bad">Between 0.01 GB and 100,000 GB.</p>}
      {msg && <p className={`key-msg ${msg.ok ? "ok" : "bad"}`}>{msg.text}</p>}
      <p className="fine-print">A folder on the server, not inside a media library. Default: <code>{status.default_folder}</code>.
        Each file is one JSON object per line.</p>

      <form className="key-row" onSubmit={(e) => { e.preventDefault(); search(); }}>
        <input className="text-input wide" placeholder="Search: an address, a path, a name, a status…" value={q}
          onChange={(e) => setQ(e.target.value)} aria-label="Search the traffic log" />
        <button className="btn small ghost" disabled={busy}><Icon name="search" size={15} /> Search</button>
      </form>
      <div className="log-wrap">
        <table className="log-table">
          <thead><tr><th>When</th><th>From</th><th>Request</th><th>Status</th><th>In / out</th><th>Time</th><th>User</th></tr></thead>
          <tbody>
            {rows.map((e, i) => (
              <tr key={i} className={e.action === "block" ? "blocked" : undefined}>
                <td>{when(e.time)}</td>
                <td><code>{e.client}{e.client_port ? `:${e.client_port}` : ""}</code></td>
                <td className="req" title={e.user_agent ?? undefined}><code>{e.method} {e.path}{e.query ? `?${e.query}` : ""}</code></td>
                <td>{e.action === "block" ? <span className="root-badge bad">blocked</span> : e.status ?? "—"}</td>
                <td>{bytes(e.bytes_in)} / {bytes(e.bytes_out)}</td>
                <td>{e.duration_ms < 1000 ? `${Math.round(e.duration_ms)} ms` : `${(e.duration_ms / 1000).toFixed(1)} s`}</td>
                <td>{e.user ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && !busy && <p className="muted">{q.trim() ? "Nothing found in the part searched." : "Nothing logged yet."}</p>}
      </div>
      {next && <button className="btn ghost small" disabled={busy} onClick={() => search(next)}>{q.trim() ? "Search older" : "Show older"}</button>}
      {picking && <FolderPicker onClose={() => setPicking(false)} onPick={(p) => { setPicking(false); setFolder(p); setMsg(null); }} />}
    </section>
  );
}
