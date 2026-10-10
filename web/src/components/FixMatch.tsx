import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { type ItemDetail, type TmdbResult } from "../api";
import { useScope } from "../servers";
import Icon from "./Icon";

/** Search TMDB and pin a show/movie to the right title. */
export default function FixMatch({ item, onClose }: { item: ItemDetail; onClose: () => void }) {
  const nav = useNavigate();
  const { call, to } = useScope();  // this server, or another one's title (servers.tsx)
  const kind = item.kind === "show" ? "show" : "movie";
  const [q, setQ] = useState(item.parsed_title || item.title);
  const [results, setResults] = useState<TmdbResult[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | "search" | null>(null);

  const search = async () => {
    setBusy("search");
    setErr(null);
    try {
      setResults(await call.get<TmdbResult[]>(`/api/tmdb/search?kind=${kind}&q=${encodeURIComponent(q)}`));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const pick = async (r: TmdbResult) => {
    setBusy(r.tmdb_id);
    setErr(null);
    try {
      const d = await call.post<ItemDetail>(`/api/items/${item.id}/match`, { tmdb_id: r.tmdb_id });
      onClose();
      nav(to(`/title/${d.id}`), { replace: true });
      if (d.id === item.id) window.location.reload();
    } catch (e) {
      setErr((e as Error).message);
      setBusy(null);
    }
  };

  useEffect(() => {
    search();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Fix match">
        <div className="modal-head">
          <h3>Fix match</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="close" size={20} /></button>
        </div>
        <form className="picker-path" onSubmit={(e) => { e.preventDefault(); search(); }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search TMDB" />
          <button className="btn ghost small" disabled={!q.trim() || busy !== null}>Search</button>
        </form>
        {err && <p className="key-msg bad">{err}</p>}
        <ul className="picker-list match-list">
          {busy === "search" && <li className="muted picker-empty">Searching TMDB…</li>}
          {results?.map((r) => (
            <li key={r.tmdb_id}>
              <button onClick={() => pick(r)} disabled={busy !== null}>
                {r.poster_path
                  ? <img src={`https://image.tmdb.org/t/p/w92${r.poster_path}`} alt="" />
                  : <span className="match-noposter" />}
                <span className="match-text">
                  <strong>{r.title}</strong> {r.year && <span className="muted">({r.year})</span>}
                  {item.ids.tmdb === r.tmdb_id && <span className="tag">current</span>}
                  <span className="muted match-overview">{r.overview}</span>
                </span>
                {busy === r.tmdb_id && <span className="muted">Matching…</span>}
              </button>
            </li>
          ))}
          {results && !results.length && <li className="muted picker-empty">No TMDB results. Try another spelling.</li>}
        </ul>
      </div>
    </div>
  );
}
