import { useEffect, useState } from "react";
import type { Genre, HomeRowPref, ServerLibrary } from "../api";
import { useAuth } from "../auth";
import { homeRows, type HomeRow } from "../homeRows";
import { useApi } from "../useApi";
import Icon from "./Icon";
import { useReorder } from "./useReorder";

/** Your own Home page: the banner, and which rows show in what order (each account has its own). */
export function HomeSettings() {
  const { prefs, setPrefs } = useAuth();
  const { data: libs } = useApi<ServerLibrary[]>("/api/libraries");
  const { data: genres } = useApi<Genre[]>("/api/genres");
  const [rows, setRows] = useState<HomeRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (libs && genres) setRows(homeRows(prefs.home_rows, libs, genres)); }, [libs, genres, prefs.home_rows]);

  const save = (next: HomeRow[] | null) => {
    if (next) setRows(next);
    setErr(null);
    const home_rows: HomeRowPref[] = next ? next.map(({ id, show }) => ({ id, show })) : [];
    setPrefs({ home_rows }).catch((e) => setErr(e.message));
  };
  const move = (from: number, to: number) => {
    if (!rows) return;
    const next = [...rows];
    next.splice(to, 0, ...next.splice(from, 1));
    save(next);
  };
  const { listRef, dragging, handle, rowClass } = useReorder<HTMLOListElement>(rows?.length ?? 0, move);

  return (
    <section className="lib-card settings-card">
      <div className="lib-head"><h3>Home page</h3></div>
      <p className="muted">Choose which rows Home shows and in what order. These settings are yours; other accounts
        keep their own.</p>
      <label className="check">
        <input type="checkbox" checked={prefs.home_hero}
          onChange={(e) => setPrefs({ home_hero: e.target.checked }).catch((er) => setErr(er.message))} />
        Show the rotating "Recently added" banner at the top
      </label>
      {rows && (
        <ol ref={listRef} className={`home-rows ${dragging ? "dragging" : ""}`}>
          {rows.map((r, i) => (
            <li key={r.id} className={`home-row ${r.show ? "" : "off"} ${rowClass(i)}`}>
              <button type="button" className="reorder-handle" aria-label={`Move ${r.label}`} {...handle(i)}>
                <Icon name="grip" size={16} />
              </button>
              <label className="check">
                <input type="checkbox" checked={r.show}
                  onChange={(e) => save(rows.map((x) => (x.id === r.id ? { ...x, show: e.target.checked } : x)))} />
                {r.label}
              </label>
              <span className="spacer" />
              <span className="lib-order">
                <button className="icon-btn subtle" disabled={i === 0} onClick={() => move(i, i - 1)} title="Move up"
                  aria-label={`Move ${r.label} up`}><Icon name="chevronUp" size={16} /></button>
                <button className="icon-btn subtle" disabled={i === rows.length - 1} onClick={() => move(i, i + 1)}
                  title="Move down" aria-label={`Move ${r.label} down`}><Icon name="chevronDown" size={16} /></button>
              </span>
            </li>
          ))}
        </ol>
      )}
      <div className="key-row">
        <span className="muted">Rows with nothing in them yet stay hidden. New libraries and genres appear switched on.</span>
        <span className="spacer" />
        <button className="btn small ghost" disabled={!prefs.home_rows.length} onClick={() => save(null)}>
          Reset to default
        </button>
      </div>
      {err && <p className="key-msg bad">{err}</p>}
    </section>
  );
}
