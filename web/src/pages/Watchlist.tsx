import { useMemo, useState, type FormEvent } from "react";
import type { WatchlistItem } from "../api";
import { useAuth } from "../auth";
import { ListedCard } from "../components/Cards";
import Icon from "../components/Icon";
import { keyOf, listedLook, listedOrder, WATCHLIST_PATH, type Tagged } from "../everywhere";
import { listName, WATCHLIST_NAME } from "../homeRows";
import { useEverywhere, useSources } from "../servers";

// The watch list (sidebar, under Home): one list of every server this browser shows. Each server keeps the part of
// it that's its own (per account), so every app signed in there shows the same list; this page puts them together.

const SORTS = { listed: "Recently added", title: "Title" } as const;
const KINDS = { all: "All", movie: "Movies", show: "Shows", episode: "Episodes" } as const;  // seasons count as shows
type Kind = keyof typeof KINDS;
const kindOf = (i: WatchlistItem): Kind => (i.kind === "season" ? "show" : i.kind as Kind);

const byTitle = (a: Tagged<WatchlistItem>, b: Tagged<WatchlistItem>) => {
  const x = listedLook(a), y = listedLook(b);
  return x.title.localeCompare(y.title, undefined, { sensitivity: "base" })
    || (x.sub ?? "").localeCompare(y.sub ?? "", undefined, { numeric: true });
};

export default function Watchlist() {
  const { prefs, setPrefs } = useAuth();
  const name = listName(prefs.watchlist_name);
  const sources = useSources();
  const { lists, done } = useEverywhere<WatchlistItem>(sources, WATCHLIST_PATH);
  const [removed, setRemoved] = useState<Set<string>>(new Set());  // taken off here (the bookmark on a card)
  const [sort, setSort] = useState<keyof typeof SORTS>("listed");
  const [kind, setKind] = useState<Kind>("all");
  const [naming, setNaming] = useState<string | null>(null);  // the name being typed
  const [err, setErr] = useState<string | null>(null);

  const all = useMemo(() => listedOrder(lists).filter((i) => !removed.has(keyOf(i))), [lists, removed]);
  const kinds = useMemo(() => (Object.keys(KINDS) as Kind[]).filter((k) => k === "all" || all.some((i) => kindOf(i) === k)), [all]);
  const shown = useMemo(() => {
    const l = all.filter((i) => kind === "all" || kindOf(i) === kind);
    return sort === "title" ? [...l].sort(byTitle) : l;
  }, [all, kind, sort]);

  const rename = (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    setPrefs({ watchlist_name: (naming ?? "").trim() }).then(() => setNaming(null)).catch((x: Error) => setErr(x.message));
  };

  return (
    <div className="page">
      <div className="page-head">
        {naming === null ? (
          <>
            <h1>{name}</h1>
            <button className="icon-btn subtle" onClick={() => setNaming(prefs.watchlist_name)} title="Rename" aria-label={`Rename ${name}`}>
              <Icon name="edit" size={18} />
            </button>
          </>
        ) : (
          <form className="list-rename" onSubmit={rename}>
            <input autoFocus value={naming} maxLength={60} placeholder={WATCHLIST_NAME} aria-label="Watch list name"
              onChange={(e) => setNaming(e.target.value)} onKeyDown={(e) => { if (e.key === "Escape") setNaming(null); }} />
            <button className="btn small primary">Save</button>
            <button type="button" className="btn small ghost" onClick={() => { setNaming(null); setErr(null); }}>Cancel</button>
          </form>
        )}
        {all.length > 0 && <span className="count">{shown.length} {shown.length === 1 ? "title" : "titles"}</span>}
        {all.length > 1 && (
          <label className="sort">
            Sort
            <select value={sort} onChange={(e) => setSort(e.target.value as keyof typeof SORTS)}>
              {Object.entries(SORTS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
        )}
      </div>
      {err && <p className="key-msg bad">{err}</p>}
      {kinds.length > 2 && (
        <div className="chips">
          {kinds.map((k) => (
            <button key={k} className={`chip ${kind === k ? "on" : ""}`} onClick={() => setKind(k)}>{KINDS[k]}</button>
          ))}
        </div>
      )}
      {!all.length && (done
        ? <div className="empty-state list-empty">
            <Icon name="bookmark" size={40} />
            <h2>Nothing on {name} yet</h2>
            <p className="muted">Add movies, shows, seasons and episodes with the {name} button on their page, the bookmark
              beside an episode, or the bookmark on a poster. Titles from every server you're connected to go on this one list,
              and it's the same on every device you sign in on.</p>
          </div>
        : <p className="muted">Loading…</p>)}
      <div className="grid">
        {shown.map((i) => (
          <ListedCard key={keyOf(i)} item={i} onRemoved={() => setRemoved((s) => new Set(s).add(keyOf(i)))} />
        ))}
      </div>
    </div>
  );
}
