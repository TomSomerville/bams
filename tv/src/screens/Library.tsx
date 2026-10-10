import { useEffect, useMemo, useState } from "react";
import { apiFor, type ItemSummary } from "../api";
import { useFocusOnReady, useNav } from "../App";
import { Poster } from "../Cards";
import { MusicLibrary } from "./Music";

const SORTS = [
  { id: "title", label: "A–Z" },
  { id: "added", label: "Recently added" },
  { id: "year", label: "Year" },
  { id: "rating", label: "Rating" },
] as const;

const PAGE = 140;  // posters on the page at once; more are added as the focus gets near the end

/** One library: music (MusicLibrary), or a grid of posters, sortable. `rid`: of another of this TV's servers. */
export default function Library({ id, rid }: { id: number; rid?: number }) {
  const nav = useNav();
  const lib = rid === undefined ? nav.libraries.find((l) => l.id === id)
    : nav.servers.find((s) => s.id === rid)?.libraries.find((l) => l.id === id);
  if (lib?.type === "music") return <MusicLibrary id={id} rid={rid} name={lib.name} />;
  return <VideoLibrary id={id} rid={rid} name={lib?.name} />;
}

function VideoLibrary({ id, rid, name }: { id: number; rid?: number; name?: string }) {
  const nav = useNav();
  const key = rid === undefined ? `${id}` : `r${rid}.${id}`;  // remembered sort/genre, per server and library
  const [sort, setSort] = useState<string>(() => sessionStorage.getItem(`bams.sort.${key}`) || "title");
  const [items, setItems] = useState<ItemSummary[] | null>(null);
  const [shown, setShown] = useState(PAGE);
  const [err, setErr] = useState<string | null>(null);
  const [genre, setGenre] = useState<string | null>(() => sessionStorage.getItem(`bams.genre.${key}`));

  useEffect(() => {
    setItems(null);
    apiFor(rid).get<ItemSummary[]>(`/api/libraries/${id}/items?sort=${sort}&limit=5000`)
      .then(setItems).catch((e) => setErr((e as Error).message));
  }, [id, rid, sort]);

  useFocusOnReady(items !== null);

  // the web Library page's genre filter: the genres of this library's titles
  const genres = useMemo(() => [...new Set((items ?? []).flatMap((i) => i.genres))].sort(), [items]);
  const list = (items ?? []).filter((i) => !genre || i.genres.includes(genre));
  const pickGenre = (g: string | null) => {
    if (g) sessionStorage.setItem(`bams.genre.${key}`, g); else sessionStorage.removeItem(`bams.genre.${key}`);
    setShown(PAGE);
    setGenre(g);
  };

  const pick = (s: string) => {
    sessionStorage.setItem(`bams.sort.${key}`, s);
    setShown(PAGE);
    setSort(s);
  };

  return (
    <div className="page">
      <div className="page-head">
        <h1>{name ?? "Library"}</h1>
        <div className="chips">
          {SORTS.map((s) => (
            <button key={s.id} data-fid={`sort-${s.id}`} className={`chip ${sort === s.id ? "on" : ""}`} onClick={() => pick(s.id)}>
              {s.label}
            </button>
          ))}
        </div>
      </div>
      {err && <p className="error big">{err}</p>}
      {items === null && !err && <div className="spinner" />}
      {genres.length > 1 && (
        <div className="chips genres" data-row>
          <button className={`chip ${!genre ? "on" : ""}`} data-fid="genre-all" onClick={() => pickGenre(null)}>All</button>
          {genres.map((g) => (
            <button key={g} className={`chip ${genre === g ? "on" : ""}`} data-fid={`genre-${g}`} onClick={() => pickGenre(g)}>{g}</button>
          ))}
        </div>
      )}
      {items && !items.length && <p className="muted big">This library is empty.</p>}
      <div className="grid">
        {list.slice(0, shown).map((it, i) => (
          <Poster key={it.id} item={it} rid={rid} fid={`item-${it.id}`} autoFocus={i === 0}
            onFocus={() => { if (i > shown - 30 && shown < list.length) setShown((n) => n + PAGE); }}
            onPress={() => nav.push({ name: "detail", id: it.id, rid })} />
        ))}
      </div>
    </div>
  );
}
