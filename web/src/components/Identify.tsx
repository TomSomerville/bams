import { useCallback, useEffect, useMemo, useState, type ClipboardEvent, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, type Identification, type LibraryNames, type UnrecognizedFile } from "../api";
import { sxe } from "../format";
import Combo, { type ComboOption } from "./Combo";
import Icon from "./Icon";

// What's already in each library, for the suggestions. Dropped after a save (a new name may exist then).
const namesCache = new Map<number, Promise<LibraryNames>>();
const loadNames = (libId: number) => {
  if (!namesCache.has(libId)) namesCache.set(libId, api.get<LibraryNames>(`/api/libraries/${libId}/names`).catch(() => []));
  return namesCache.get(libId)!;
};

const size = (b: number) => (b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.max(1, Math.round(b / 1e6))} MB`);
const seasonLabel = (n: number) => (n === 0 ? "Specials" : `Season ${n}`);

/** "2" · "2-3" · "2, 3" -> episode numbers; "" -> [] (an extra); anything else -> null (invalid). */
function parseEpisodes(s: string): number[] | null {
  const t = s.trim();
  if (!t) return [];
  const range = t.match(/^(\d+)\s*-\s*(\d+)$/);
  if (range) {
    const [a, b] = [Number(range[1]), Number(range[2])];
    return b >= a && b - a < 50 ? Array.from({ length: b - a + 1 }, (_, i) => a + i) : null;
  }
  const parts = t.split(/[\s,]+/);
  return parts.every((p) => /^\d+$/.test(p)) ? parts.map(Number) : null;
}

function describe(m: Identification, type: string) {
  if (type === "movie") return [m.title, m.year && `(${m.year})`, m.edition && `· ${m.edition}`].filter(Boolean).join(" ");
  const eps = m.episodes?.length ? m.episodes : null;
  const where = eps ? eps.map((e) => sxe(m.season ?? 0, e)).join(", ") : `${seasonLabel(m.season ?? 0)}, extra`;
  return [m.title, m.year && `(${m.year})`, "·", where, m.episode_title && `· ${m.episode_title}`].filter(Boolean).join(" ");
}

/** Say what one file is: paste a TMDB / IMDb link, or fill the fields in (with suggestions from the library). */
function IdentifyForm({ file, onDone, onCancel }: { file: UnrecognizedFile; onDone: (msg: string, itemId: number) => void; onCancel: () => void }) {
  const isShow = file.library_type === "show";
  const start: Identification = file.manual ?? {
    title: file.guess.title ?? "", year: file.guess.year, season: file.guess.season,
    episodes: file.guess.episodes ?? [], episode_title: file.guess.episode_title,
  };
  const [names, setNames] = useState<LibraryNames>([]);
  const [link, setLink] = useState("");
  const [title, setTitle] = useState(start.title);
  const [year, setYear] = useState(start.year ? String(start.year) : "");
  const [season, setSeason] = useState(start.season != null ? String(start.season) : "");
  const [episodes, setEpisodes] = useState((start.episodes ?? []).join(", "));
  const [epTitle, setEpTitle] = useState(start.episode_title ?? "");
  const [edition, setEdition] = useState(start.edition ?? "");
  const [tmdbId, setTmdbId] = useState<number | null>(start.tmdb_id ?? null);
  const [busy, setBusy] = useState<"link" | "save" | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { loadNames(file.library_id).then(setNames); }, [file.library_id]);

  // the show/movie the fields point at, if it's already in the library
  const known = useMemo(() => {
    const t = title.trim().toLowerCase();
    return names.find((n) => n.title.toLowerCase() === t && (!year || String(n.year ?? "") === year))
      ?? names.find((n) => n.title.toLowerCase() === t);
  }, [names, title, year]);
  const knownSeason = known?.seasons?.find((s) => String(s.season) === season.trim());

  const titleOptions: ComboOption[] = names.map((n) => ({ value: n.title, note: n.year ? String(n.year) : undefined }));
  const yearOptions: ComboOption[] = [...new Set(names.filter((n) => !title.trim() || n.title.toLowerCase().includes(title.trim().toLowerCase()))
    .map((n) => n.year).filter((y): y is number => !!y))].sort((a, b) => b - a).map((y) => ({ value: String(y) }));
  const seasonOptions: ComboOption[] = (known?.seasons ?? []).map((s) => ({
    value: String(s.season), label: seasonLabel(s.season), note: `${s.episodes.length} in library` }));
  const numbered = (knownSeason?.episodes ?? []).filter((e) => e.n !== null);
  const episodeOptions: ComboOption[] = numbered.map((e) => ({ value: String(e.n), label: `${e.n} · ${e.title}`, note: "in library" }));
  const epTitleOptions: ComboOption[] = (knownSeason?.episodes ?? []).map((e) => ({
    value: e.title, note: e.n !== null ? `E${String(e.n).padStart(2, "0")}` : "extra" }));

  const fill = async (text: string) => {
    if (!text.trim()) return;
    setBusy("link");
    setErr(null);
    try {
      const r = await api.post<Identification>("/api/identify/lookup", { link: text.trim(), library_id: file.library_id });
      setTitle(r.title ?? "");
      setYear(r.year ? String(r.year) : "");
      setTmdbId(r.tmdb_id ?? null);
      if (isShow) {
        if (r.season != null) setSeason(String(r.season));
        if (r.episodes?.length) setEpisodes(r.episodes.join(", "));
        if (r.episode_title) setEpTitle(r.episode_title);
      }
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const eps = parseEpisodes(episodes);
  const seasonN = /^\d+$/.test(season.trim()) ? Number(season.trim()) : null;
  const yearN = /^\d{4}$/.test(year.trim()) ? Number(year.trim()) : null;
  const problem = !title.trim() ? "A title is needed."
    : year.trim() && yearN === null ? "The year should be four digits."
    : isShow && seasonN === null ? "Which season? (0 = Specials)"
    : isShow && eps === null ? "Episodes: a number, a range like 2-3, or a list like 2, 3."
    : isShow && !eps?.length && !epTitle.trim() ? "An extra (no episode number) needs a title."
    : null;

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (problem) return setErr(problem);
    setBusy("save");
    setErr(null);
    const body: Identification = isShow
      ? { title: title.trim(), year: yearN, season: seasonN, episodes: eps!, episode_title: epTitle.trim() || null, tmdb_id: tmdbId }
      : { title: title.trim(), year: yearN, edition: edition.trim() || null, tmdb_id: tmdbId };
    try {
      const r = await api.put<{ item_id: number; note: string | null }>(`/api/files/${file.id}/identify`, body);
      namesCache.delete(file.library_id);
      onDone(r.note ?? "Saved", r.item_id);
    } catch (e) {
      setErr((e as Error).message);
      setBusy(null);
    }
  };

  return (
    <form className="identify-form" onSubmit={save}>
      <label htmlFor={`link-${file.id}`}>Link</label>
      <span className="identify-link">
        <input id={`link-${file.id}`} className="text-input" value={link} placeholder="Paste a TMDB or IMDb link to fill this in"
          onChange={(e) => setLink(e.target.value)}
          onPaste={(e: ClipboardEvent<HTMLInputElement>) => { const t = e.clipboardData.getData("text"); setTimeout(() => fill(t)); }} />
        <button type="button" className="btn ghost small" disabled={!link.trim() || busy !== null} onClick={() => fill(link)}>
          {busy === "link" ? "Looking up…" : "Fill in"}
        </button>
      </span>

      <label htmlFor={`title-${file.id}`}>{isShow ? "Show" : "Movie"}</label>
      <span className="identify-pair">
        <Combo id={`title-${file.id}`} value={title} options={titleOptions} placeholder={isShow ? "Show name" : "Movie title"}
          onChange={(v) => { setTitle(v); setErr(null); }}
          onPick={(o) => { setTitle(o.value); if (o.note) setYear(o.note); }} />
        <Combo aria-label="Year" className="combo-year" value={year} options={yearOptions} placeholder="Year" inputMode="numeric"
          onChange={(v) => { setYear(v); setErr(null); }} />
      </span>
      {tmdbId && (
        <><span /><span className="identify-tmdb">
          <span className="tag">TMDB {tmdbId}</span>
          <button type="button" className="link-btn" onClick={() => setTmdbId(null)}>don't use</button>
        </span></>
      )}

      {isShow ? (
        <>
          <label htmlFor={`season-${file.id}`}>Season</label>
          <span className="identify-pair">
            <Combo id={`season-${file.id}`} className="combo-num" value={season} options={seasonOptions} placeholder="0 = Specials"
              inputMode="numeric" onChange={(v) => { setSeason(v); setErr(null); }} />
            <Combo aria-label="Episode number(s)" className="combo-num" value={episodes} options={episodeOptions}
              placeholder="Episode(s)" onChange={(v) => { setEpisodes(v); setErr(null); }}
              onPick={(o) => { setEpisodes(o.value); setEpTitle(numbered.find((e) => String(e.n) === o.value)?.title ?? epTitle); }} />
          </span>
          <label htmlFor={`eptitle-${file.id}`}>Episode title</label>
          <Combo id={`eptitle-${file.id}`} value={epTitle} options={epTitleOptions} placeholder="Optional (needed for an extra)"
            onChange={(v) => { setEpTitle(v); setErr(null); }}
            onPick={(o) => {
              setEpTitle(o.value);
              const ep = knownSeason?.episodes.find((e) => e.title === o.value);
              if (ep) setEpisodes(ep.n !== null ? String(ep.n) : "");
            }} />
          <span />
          <p className="fine-print">Leave the episode number empty for an extra (a featurette, a blooper reel): it's listed
            after that season's episodes. A file with several episodes: 2-3.</p>
        </>
      ) : (
        <>
          <label htmlFor={`edition-${file.id}`}>Edition</label>
          <input id={`edition-${file.id}`} className="text-input" value={edition} placeholder="Optional (Director's Cut…)"
            onChange={(e) => setEdition(e.target.value)} />
        </>
      )}

      <span />
      <span className="identify-actions">
        <button className="btn small primary" disabled={busy !== null}>{busy === "save" ? "Saving…" : "Save"}</button>
        <button type="button" className="btn small ghost" onClick={onCancel}>Cancel</button>
        {err && <span className="key-msg bad">{err}</span>}
      </span>
    </form>
  );
}

function FileRow({ f, onChange }: { f: UnrecognizedFile; onChange: () => void }) {
  const [editing, setEditing] = useState(false);
  const [msg, setMsg] = useState<{ text: string; itemId?: number } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const canEdit = f.library_type !== "music";

  const undo = async () => {
    setErr(null);
    try {
      await api.del(`/api/files/${f.id}/identify`);
      namesCache.delete(f.library_id);
      onChange();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <li className={f.manual ? "identified" : ""}>
      <div className="file-line">
        <code>{f.path}</code>
        <span className="muted">{size(f.size)}</span>
        <span className="spacer" />
        {canEdit && !editing && <button className="btn ghost small" onClick={() => { setEditing(true); setMsg(null); }}>
          <Icon name="edit" size={14} /> {f.manual ? "Edit" : "Identify"}</button>}
        {f.manual && !editing && <button className="btn ghost small" onClick={undo}
          title="Forget this and place the file by its name again">Undo</button>}
      </div>
      {f.manual ? <span className="ok-text"><Icon name="check" size={14} /> Identified by hand: {describe(f.manual, f.library_type)}</span>
        : <span className="muted">{f.hint}</span>}
      {msg && <span className="ok-text">{msg.text}{msg.itemId && <> · <Link to={`/title/${msg.itemId}`}>open</Link></>}</span>}
      {err && <span className="key-msg bad">{err}</span>}
      {editing && <IdentifyForm file={f} onCancel={() => setEditing(false)}
        onDone={(text, itemId) => { setEditing(false); setMsg({ text, itemId }); onChange(); }} />}
    </li>
  );
}

/** Files the scanner couldn't identify (and ones identified by hand), for one library or all of them. */
export function UnrecognizedFiles({ libraryId, reloadKey, onChange }: { libraryId?: number; reloadKey?: unknown; onChange?: () => void }) {
  const [files, setFiles] = useState<UnrecognizedFile[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    api.get<UnrecognizedFile[]>(libraryId ? `/api/libraries/${libraryId}/unrecognized` : "/api/unrecognized")
      .then((f) => { setFiles(f); setErr(null); }).catch((e) => setErr(e.message));
  }, [libraryId]);
  useEffect(load, [load, reloadKey]);

  const changed = () => { load(); onChange?.(); };
  if (err) return <p className="key-msg bad">{err}</p>;
  if (!files) return <p className="muted">Loading…</p>;
  if (!files.length) return <p className="muted">Every file {libraryId ? "in this library" : ""} has been identified.</p>;

  const groups = new Map<number, UnrecognizedFile[]>();
  for (const f of files) groups.set(f.library_id, [...(groups.get(f.library_id) ?? []), f]);
  return (
    <div className="unrecognized-list">
      {[...groups.values()].map((g) => {
        const open = g.filter((f) => !f.manual).length;
        return (
          <section key={g[0].library_id} className="lib-card settings-card">
            {!libraryId && (
              <div className="lib-head">
                <h3><Link to={`/library/${g[0].library_id}?tab=unrecognized`}>{g[0].library_name}</Link></h3>
                <span className={`status-pill ${open ? "warn" : "ok"}`}>{open ? `${open} to identify` : "All identified"}</span>
              </div>
            )}
            <ul className="unrecognized-files">
              {g.map((f) => <FileRow key={f.id} f={f} onChange={changed} />)}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
