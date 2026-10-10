import { useCallback, useEffect, useState } from "react";
import { api, type ServerStatus } from "../api";
import { fmtSize } from "../format";
import Icon from "./Icon";

type Asset = { name: string; url: string; size: number | null; sha256: string | null };
type UpdateStatus = {
  current: string; install: "windows" | "deb" | "source"; checked_at: number | null; error: string | null;
  latest: { version: string; name: string | null; notes: string; url: string; published: string | null;
            assets: Partial<Record<"windows" | "deb", Asset>> } | null;
  newer: boolean; can_download: boolean; updates_dir: string;
  job: { state: "idle" | "downloading" | "ready" | "installing" | "error"; version?: string; got?: number;
         size?: number | null; file?: string; error?: string };
};

const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString() : "");

/** Settings -> About: the version running, the newest release on GitHub, and updating to it. */
export default function AboutSettings() {
  const [st, setSt] = useState<UpdateStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [restarting, setRestarting] = useState<string | null>(null); // installing: the version we wait for

  const load = useCallback(async (refresh = false) => {
    try {
      setSt(await api.get<UpdateStatus>(`/api/update${refresh ? "?refresh=true" : ""}`));
      setErr(null);
    } catch (e) {
      setErr((e as Error).message);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  // While downloading: follow its progress
  const job = st?.job.state;
  useEffect(() => {
    if (job !== "downloading") return;
    const t = setInterval(() => load(), 1000);
    return () => clearInterval(t);
  }, [job, load]);

  // While installing: the server goes away and comes back as the new version, then the page reloads
  useEffect(() => {
    if (!restarting) return;
    const t = setInterval(async () => {
      try {
        const s = await api.get<ServerStatus>("/api/status");
        if (s.version === restarting) window.location.reload();
      } catch { /* still restarting */ }
    }, 3000);
    return () => clearInterval(t);
  }, [restarting]);

  const act = async (path: string) => {
    setBusy(true);
    setErr(null);
    try {
      const s = await api.post<UpdateStatus>(path, {});
      setSt(s);
      if (s.job.state === "installing") setRestarting(s.job.version ?? s.latest?.version ?? null);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const install = () => {
    if (window.confirm(`Install BAMS ${st?.latest?.version} now? The server stops for a minute or two while it updates: `
      + "anyone watching is interrupted. Your libraries, accounts and settings are kept.")) act("/api/update/install");
  };

  if (!st) {
    return <section className="lib-card settings-card"><div className="lib-head"><h3>BAMS</h3></div>
      {err ? <p className="key-msg bad">{err}</p> : <p className="muted">Checking for updates…</p>}</section>;
  }
  const l = st.latest;
  const asset = st.install !== "source" ? l?.assets[st.install] : undefined;
  const pct = st.job.size ? Math.min(100, Math.round(((st.job.got ?? 0) / st.job.size) * 100)) : null;
  const debPath = st.job.file;
  return (
    <section className="lib-card settings-card">
      <div className="lib-head">
        <h3>BAMS {st.current}</h3>
        {st.newer
          ? <span className="status-pill warn">Update available: {l!.version}</span>
          : l && <span className="status-pill ok"><Icon name="check" size={14} /> Up to date</span>}
      </div>
      <p className="muted">
        You're running BAMS {st.current}
        {st.install === "windows" ? " (Windows installer)" : st.install === "deb" ? " (Linux package)" : " (from source)"}.
        {l && <> The newest release is <a href={l.url} target="_blank" rel="noreferrer">{l.name ?? l.version}</a>
          {l.published && `, published ${day(l.published)}`}.</>}
        {!l && !st.error && " No release has been published yet."}
      </p>
      {st.error && <p className="key-msg warn">{st.error}</p>}

      {st.newer && l?.notes && (
        <details className="release-notes">
          <summary>What's new in {l.version}</summary>
          <pre>{l.notes.trim()}</pre>
        </details>
      )}

      {st.newer && st.install === "source" && (
        <p className="fine-print">This copy runs from a source checkout: update it with <code>git pull</code> (then rebuild
          the web UI and restart), or install the release.</p>
      )}

      {st.newer && asset && (
        <div className="key-row">
          {(job === "idle" || job === "error" || (st.job.version && st.job.version !== l!.version)) && (
            <button className="btn primary small" disabled={busy} onClick={() => act("/api/update/download")}>
              <Icon name="download" size={16} /> Download {l!.version}{asset.size ? ` (${fmtSize(asset.size)})` : ""}
            </button>
          )}
          {job === "downloading" && <span className="muted">Downloading… {pct !== null ? `${pct}%` : ""}</span>}
          {job === "ready" && st.install === "windows" && !restarting && (
            <button className="btn primary small" disabled={busy} onClick={install}>Install and restart</button>
          )}
          {(job === "installing" || restarting) && (
            <span className="muted">Installing {st.job.version}: BAMS restarts by itself and this page reloads when it's
              back (a minute or two).</span>
          )}
        </div>
      )}
      {st.job.state === "error" && <p className="key-msg bad">{st.job.error}</p>}
      {job === "ready" && st.install === "deb" && debPath && (
        <>
          <p className="muted">Downloaded and checked. The service can't install packages itself (it runs without root):
            run this on the server, and BAMS restarts on the new version.</p>
          <pre className="command">sudo apt install {debPath}</pre>
        </>
      )}
      {err && <p className="key-msg bad">{err}</p>}

      <div className="key-row">
        <button className="btn ghost small" disabled={busy || job === "downloading"} onClick={() => load(true)}>
          Check again</button>
        {st.checked_at && <span className="fine-print tight">Checked {new Date(st.checked_at * 1000).toLocaleString()}</span>}
      </div>
      <p className="fine-print">Releases come from <a href="https://github.com/TomSomerville/bams/releases" target="_blank"
        rel="noreferrer">github.com/TomSomerville/bams</a>. A download is checked against the release's SHA-256 before
        it's installed. Updates keep your libraries, accounts, watch history and settings.</p>
    </section>
  );
}
