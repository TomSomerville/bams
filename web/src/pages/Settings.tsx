import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, type ServerLibrary, type ServerStatus } from "../api";
import { useAuth } from "../auth";
import { AccountSettings, UsersSettings } from "../components/AccountSettings";
import FolderPicker from "../components/FolderPicker";
import Icon from "../components/Icon";
import { UnrecognizedFiles } from "../components/Identify";
import MusicSettings from "../components/MusicSettings";
import TranscodeSettings from "../components/TranscodeSettings";
import WatchSettings from "../components/WatchSettings";
import TmdbSettings from "../components/TmdbSettings";
import { LIB_TYPES, type LibType } from "../format";

const INTERVALS = [1, 2, 3, 6, 12, 24, 48, 168];
const hours = (h: number) => (h >= 24 && h % 24 === 0 ? `${h / 24} day${h > 24 ? "s" : ""}` : `${h} hour${h === 1 ? "" : "s"}`);

function ago(ts: number | null) {
  if (!ts) return "never";
  const s = Date.now() / 1000 - ts;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} days ago`;
}

const gb = (b: number) => (b >= 1e12 ? `${(b / 1e12).toFixed(1)} TB` : `${(b / 1e9).toFixed(1)} GB`);

/** "N files couldn't be identified": a link to the library's Unrecognized tab, where they can be identified. */
function Unrecognized({ lib }: { lib: ServerLibrary }) {
  const n = lib.files.unrecognized;
  if (!n) return null;
  return (
    <div className="unrecognized">
      <Link className="link-btn warn" to={`/library/${lib.id}?tab=unrecognized`}>
        <Icon name="alert" size={14} /> {n} file{n === 1 ? "" : "s"} couldn't be identified: identify them
      </Link>
    </div>
  );
}

function LibraryCard({ lib, status, onChange }: { lib: ServerLibrary; status: ServerStatus | null; onChange: () => void }) {
  const [err, setErr] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(lib.name);

  const running = status?.scans.running?.library_id === lib.id ? status.scans.running : null;
  const queued = status?.scans.queued.some((q) => q.library_id === lib.id);
  const kindLabel = LIB_TYPES[lib.type].label;
  const counts = lib.type === "show"
    ? `${lib.counts.show ?? 0} shows · ${lib.counts.episode ?? 0} episodes`
    : lib.type === "music"
      ? `${lib.counts.artist ?? 0} artists · ${lib.counts.album ?? 0} albums · ${lib.counts.track ?? 0} tracks`
      : `${lib.counts.movie ?? 0} movies`;

  const run = async (f: () => Promise<unknown>) => {
    setErr(null);
    try {
      await f();
      onChange();
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  const patch = (body: object) => run(() => api.patch(`/api/libraries/${lib.id}`, body));

  return (
    <div className="lib-card">
      <div className="lib-head">
        <Icon name={LIB_TYPES[lib.type].icon} size={22} />
        {renaming ? (
          <form className="rename" onSubmit={(e) => { e.preventDefault(); patch({ name }).then(() => setRenaming(false)); }}>
            <input value={name} onChange={(e) => setName(e.target.value)} autoFocus aria-label="Library name" />
            <button className="btn primary small" disabled={!name.trim()}>Save</button>
            <button type="button" className="btn ghost small" onClick={() => { setRenaming(false); setName(lib.name); }}>Cancel</button>
          </form>
        ) : (
          <>
            <h3>{lib.name}</h3>
            <button className="icon-btn subtle" onClick={() => setRenaming(true)} title="Rename"><Icon name="edit" size={15} /></button>
            <span className="tag">{kindLabel}</span>
          </>
        )}
        <span className="muted lib-counts">{counts} · {gb(lib.files.bytes)}</span>
      </div>

      <div className="lib-paths">
        {lib.roots.map((r) => (
          <div key={r.path} className="path">
            <Icon name="folder" size={16} /> <code>{r.path}</code>
            {!r.exists && <span className="root-badge bad">offline / not found</span>}
            {r.exists && !r.readable && <span className="root-badge bad">no read permission</span>}
            {r.os_write_access && <span className="root-badge warn" title="BAMS never writes here, but the OS would let it. See docs/READ-ONLY.md">writable by BAMS's account</span>}
            {lib.roots.length > 1 && (
              <button className="icon-btn subtle remove-root" title="Remove this folder from the library (files are not touched)"
                onClick={() => patch({ remove_paths: [r.path] })}>
                <Icon name="close" size={16} />
              </button>
            )}
          </div>
        ))}
        <button className="link-btn" onClick={() => setPicking(true)}><Icon name="plus" size={14} /> Add folder</button>
      </div>

      <div className="lib-foot">
        <label className="sort">
          Scan every
          <select value={lib.scan_interval_hours} onChange={(e) => patch({ scan_interval_hours: Number(e.target.value) })}>
            {[...new Set([...INTERVALS, lib.scan_interval_hours])].sort((a, b) => a - b).map((h) => (
              <option key={h} value={h}>{hours(h)}</option>
            ))}
          </select>
        </label>
        <span className="muted">
          {running ? <>Scanning: {running.step}</> : queued ? "Scan queued" : <>Last scan: {ago(lib.last_scan_at)}
            {lib.last_scan_status && lib.last_scan_status !== "ok" && <span className="root-badge warn">{lib.last_scan_status}</span>}</>}
        </span>
        <span className="spacer" />
        {confirmDelete ? (
          <span className="confirm">
            Forget this library? Your files are not touched.
            <button className="btn ghost small danger" onClick={() => run(() => api.del(`/api/libraries/${lib.id}`))}>Remove</button>
            <button className="btn ghost small" onClick={() => setConfirmDelete(false)}>Cancel</button>
          </span>
        ) : (
          <>
            <button className="btn ghost small danger" onClick={() => setConfirmDelete(true)}>Remove</button>
            <button className="btn ghost small" disabled={!!running || queued}
              onClick={() => run(() => api.post(`/api/libraries/${lib.id}/scan`))}>
              <Icon name="refresh" size={16} /> {running ? "Scanning…" : queued ? "Queued" : "Scan now"}
            </button>
          </>
        )}
      </div>
      {running && <div className="progress inline indeterminate"><div /></div>}
      {!running && <Unrecognized lib={lib} />}
      {err && <p className="key-msg bad">{err}</p>}
      {picking && <FolderPicker onClose={() => setPicking(false)}
        onPick={(p) => { setPicking(false); patch({ add_paths: [p] }); }} />}
    </div>
  );
}

function AddLibrary({ onDone, onCancel }: { onDone: () => void; onCancel: () => void }) {
  const [type, setType] = useState<LibType>("show");
  const [name, setName] = useState("TV Shows");
  const [nameTouched, setNameTouched] = useState(false);
  const [paths, setPaths] = useState<string[]>([]);
  const [interval, setInterval_] = useState(6);
  const [picking, setPicking] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const pickType = (t: LibType) => {
    setType(t);
    if (!nameTouched) setName(LIB_TYPES[t].label);
  };

  const create = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api.post("/api/libraries", { name: name.trim(), type, paths, scan_interval_hours: interval });
      onDone();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="lib-card add-lib">
      <div className="lib-head"><h3>New library</h3></div>
      <div className="form-grid">
        <label>Type</label>
        <div className="segmented" role="radiogroup">
          {(Object.keys(LIB_TYPES) as LibType[]).map((t) => (
            <button key={t} type="button" role="radio" aria-checked={type === t} className={type === t ? "on" : ""}
              onClick={() => pickType(t)}>
              <Icon name={LIB_TYPES[t].icon} size={16} /> {LIB_TYPES[t].label}
            </button>
          ))}
        </div>

        <label htmlFor="lib-name">Name</label>
        <input id="lib-name" className="text-input" value={name} onChange={(e) => { setName(e.target.value); setNameTouched(true); }} />

        <label>Folders</label>
        <div>
          {paths.map((p) => (
            <div key={p} className="path">
              <Icon name="folder" size={16} /> <code>{p}</code>
              <button className="icon-btn subtle remove-root" onClick={() => setPaths(paths.filter((x) => x !== p))} title="Remove">
                <Icon name="close" size={16} />
              </button>
            </div>
          ))}
          <button className="btn ghost small" onClick={() => setPicking(true)}><Icon name="folder" size={16} /> Browse…</button>
          <p className="fine-print">Folders on the server. BAMS only ever reads them; it never changes, renames or adds files there.</p>
        </div>

        <label>Scan every</label>
        <select className="text-input" value={interval} onChange={(e) => setInterval_(Number(e.target.value))}>
          {INTERVALS.map((h) => <option key={h} value={h}>{hours(h)}</option>)}
        </select>
      </div>
      {err && <p className="key-msg bad">{err}</p>}
      <div className="lib-foot">
        <span className="spacer" />
        <button className="btn ghost small" onClick={onCancel}>Cancel</button>
        <button className="btn primary small" disabled={busy || !name.trim() || !paths.length} onClick={create}>
          {busy ? "Adding…" : "Add library"}
        </button>
      </div>
      {picking && <FolderPicker onClose={() => setPicking(false)}
        onPick={(p) => { setPicking(false); setPaths((ps) => (ps.includes(p) ? ps : [...ps, p])); }} />}
    </div>
  );
}

export default function Settings() {
  const { user } = useAuth();
  if (!user.is_admin) {
    return (
      <div className="page narrow">
        <div className="page-head"><h1>Settings</h1></div>
        <div className="section-head"><h2 className="section-title">Your account</h2></div>
        <div className="lib-list"><AccountSettings /></div>
        <p className="muted">Libraries and server settings are managed by an admin.</p>
      </div>
    );
  }
  return <AdminSettings />;
}

function AdminSettings() {
  const [libs, setLibs] = useState<ServerLibrary[] | null>(null);
  const [status, setStatus] = useState<ServerStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const wasBusy = useRef(false);

  const load = useCallback(async () => {
    try {
      setLibs(await api.get<ServerLibrary[]>("/api/libraries"));
      setErr(null);
    } catch (e) {
      setErr((e as Error).message);
    }
  }, []);

  // Poll scan status; reload library counts when a scan finishes.
  useEffect(() => {
    load();
    let alive = true;
    const tick = async () => {
      try {
        const s = await api.get<ServerStatus>("/api/status");
        if (!alive) return;
        setStatus(s);
        const busy = !!s.scans.running || s.scans.queued.length > 0;
        if (wasBusy.current && !busy) load();
        wasBusy.current = busy;
      } catch {
        /* server down: the banner says so */
      }
    };
    tick();
    const t = setInterval(tick, 2000);
    return () => { alive = false; clearInterval(t); };
  }, [load]);

  // After any change (add, scan, edit): reload now, and again once the server is idle, even if a
  // quick scan started and finished between two status polls.
  const changed = () => {
    wasBusy.current = true;
    load();
    api.get<ServerStatus>("/api/status").then(setStatus).catch(() => {});
  };

  return (
    <div className="page narrow">
      <div className="page-head"><h1>Settings</h1></div>

      <div className="section-head">
        <h2 className="section-title">Libraries</h2>
        {!adding && <button className="btn primary small" onClick={() => setAdding(true)} disabled={!libs}>
          <Icon name="plus" size={16} /> Add library
        </button>}
      </div>
      <p className="muted">
        Folders can be local drives or mounted network shares. On Windows, use UNC paths (<code>\\nas\media</code>) when
        BAMS runs as a service, because a service can't see drive letters mapped in your session. On Linux, use the mount
        point (<code>/mnt/media</code>).
      </p>
      {status && !status.ffprobe && (
        <p className="key-msg warn">FFmpeg (ffprobe) wasn't found by the server, so codec and resolution come from file names
          only. Install FFmpeg and restart the server.</p>
      )}
      <div className="lib-list">
        {adding && <AddLibrary onCancel={() => setAdding(false)} onDone={() => { setAdding(false); changed(); }} />}
        {err && <p className="key-msg bad">{err}</p>}
        {libs?.map((l) => <LibraryCard key={l.id} lib={l} status={status} onChange={changed} />)}
        {libs && !libs.length && !adding && <p className="muted">No libraries yet. Add one to start indexing.</p>}
      </div>

      <div className="section-head" id="unrecognized"><h2 className="section-title">Unrecognized files</h2></div>
      <p className="muted">Files the scan found but couldn't place from their names. Paste a TMDB or IMDb link, or say
        what each one is. They stay hidden from the libraries until they're identified, and what you enter is kept
        across rescans.</p>
      <UnrecognizedFiles reloadKey={libs?.map((l) => l.files.unrecognized).join()} onChange={changed} />

      <div className="section-head"><h2 className="section-title">Metadata</h2></div>
      <TmdbSettings />
      <div className="lib-list"><MusicSettings /></div>

      <div className="section-head"><h2 className="section-title">Playback</h2></div>
      <div className="lib-list"><TranscodeSettings status={status} /><WatchSettings /></div>

      <div className="section-head"><h2 className="section-title">Accounts</h2></div>
      <div className="lib-list"><AccountSettings /><UsersSettings /></div>
    </div>
  );
}
