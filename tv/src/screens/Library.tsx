import { useEffect, useMemo, useState } from "react";
import { api, type ItemSummary } from "../api";
import { useFocusOnReady, useNav } from "../App";
import { Poster } from "../Cards";

const SORTS = [
  { id: "title", label: "A–Z" },
  { id: "added", label: "Recently added" },
  { id: "year", label: "Year" },
  { id: "rating", label: "Rating" },
] as const;

const PAGE = 140;  // posters on the page at once; more are added as the focus gets near the end

/** One library: a grid of posters, sortable. */
export default function Library({ id }: { id: number }) {
  const nav = useNav();
  const lib = nav.libraries.find((l) => l.id === id);
  const [sort, setSort] = useState<string>(() => sessionStorage.getItem(`bams.sort.${id}`) || "title");
  const [items, setItems] = useState<ItemSummary[] | null>(null);
  const [shown, setShown] = useState(PAGE);
  const [err, setErr] = useState<string | null>(null);
  const [genre, setGenre] = useState<string | null>(() => sessionStorage.getItem(`bams.genre.${id}`));

  useEffect(() => {
    setItems(null);
    api.get<ItemSummary[]>(`/api/libraries/${id}/items?sort=${sort}&limit=5000`)
      .then(setItems).catch((e) => setErr((e as Error).message));
  }, [id, sort]);

  useFocusOnReady(items !== null);

  // the web Library page's genre filter: the genres of this library's titles
  const genres = useMemo(() => [...new Set((items ?? []).flatMap((i) => i.genres))].sort(), [items]);
  const list = (items ?? []).filter((i) => !genre || i.genres.includes(genre));
  const pickGenre = (g: string | null) => {
    if (g) sessionStorage.setItem(`bams.genre.${id}`, g); else sessionStorage.removeItem(`bams.genre.${id}`);
    setShown(PAGE);
    setGenre(g);
  };

  const pick = (s: string) => {
    sessionStorage.setItem(`bams.sort.${id}`, s);
    setShown(PAGE);
    setSort(s);
  };

  return (
    <div className="page">
      <div className="page-head">
        <h1>{lib?.name ?? "Library"}</h1>
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
          <Poster key={it.id} item={it} fid={`item-${it.id}`} autoFocus={i === 0}
            onFocus={() => { if (i > shown - 30 && shown < list.length) setShown((n) => n + PAGE); }}
            onPress={() => nav.push({ name: "detail", id: it.id })} />
        ))}
      </div>
    </div>
  );
}
