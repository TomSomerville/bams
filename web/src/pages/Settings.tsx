import { useState } from "react";
import { libraries, type Library } from "../data";
import Icon from "../components/Icon";

const INTERVALS = [1, 2, 6, 12, 24];

function LibraryCard({ lib }: { lib: Library }) {
  const [every, setEvery] = useState(lib.scanEveryHours);
  const [scan, setScan] = useState<number | null>(null);
  const [last, setLast] = useState(lib.lastScan);

  // Simulated scan so the flow can be clicked through; phase 1 calls POST /api/libraries/{id}/scan.
  const start = () => {
    setScan(0);
    const t = setInterval(() => {
      setScan((p) => {
        const n = (p ?? 0) + 7 + Math.random() * 12;
        if (n >= 100) { clearInterval(t); setLast("just now"); return null; }
        return n;
      });
    }, 220);
  };

  return (
    <div className={`lib-card ${lib.comingSoon ? "coming" : ""}`}>
      <div className="lib-head">
        <Icon name={lib.type === "movie" ? "film" : lib.type === "show" ? "tv" : "music"} size={22} />
        <h3>{lib.name}</h3>
        {lib.comingSoon ? <span className="tag">Phase 3</span> : <span className="muted">{lib.items} items</span>}
      </div>
      <div className="lib-paths">
        {lib.paths.length ? lib.paths.map((p) => (
          <div key={p} className="path"><Icon name="folder" size={16} /> <code>{p}</code></div>
        )) : <div className="muted">No folders yet</div>}
      </div>
      <div className="lib-foot">
        <label className="sort">
          Scan every
          <select value={every} onChange={(e) => setEvery(Number(e.target.value))} disabled={lib.comingSoon}>
            {INTERVALS.map((h) => <option key={h} value={h}>{h} hour{h > 1 ? "s" : ""}</option>)}
          </select>
        </label>
        <span className="muted">Last scan: {last}</span>
        <button className="btn ghost small" onClick={start} disabled={lib.comingSoon || scan !== null}>
          <Icon name="refresh" size={16} /> {scan !== null ? "Scanning…" : "Scan now"}
        </button>
      </div>
      {scan !== null && <div className="progress inline"><div style={{ width: `${scan}%` }} /></div>}
    </div>
  );
}

export default function Settings() {
  return (
    <div className="page narrow">
      <div className="page-head">
        <h1>Libraries</h1>
        <button className="btn primary small" disabled title="Phase 1"><Icon name="plus" size={16} /> Add library</button>
      </div>
      <p className="muted">
        Folders can be local drives or mounted network shares. On Windows, use UNC paths (<code>\\nas\media</code>) because
        a service can't see mapped drive letters. On Linux, use the mount point (<code>/mnt/media</code>).
      </p>
      <div className="lib-list">{libraries.map((l) => <LibraryCard key={l.id} lib={l} />)}</div>

      <h2 className="section-title">Metadata</h2>
      <div className="lib-card">
        <div className="lib-head"><h3>TMDB</h3><span className="tag">primary</span></div>
        <p className="muted">Posters, descriptions, cast and IMDb IDs. This product uses the TMDB API but is not endorsed or certified by TMDB.</p>
      </div>
    </div>
  );
}
