import { useEffect, useState } from "react";
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

  useEffect(() => {
    setItems(null);
    api.get<ItemSummary[]>(`/api/libraries/${id}/items?sort=${sort}&limit=5000`)
      .then(setItems).catch((e) => setErr((e as Error).message));
  }, [id, sort]);

  useFocusOnReady(items !== null);

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
      {items && !items.length && <p className="muted big">This library is empty.</p>}
      <div className="grid">
        {items?.slice(0, shown).map((it, i) => (
          <Poster key={it.id} item={it} fid={`item-${it.id}`} autoFocus={i === 0}
            onFocus={() => { if (i > shown - 30 && shown < items.length) setShown((n) => n + PAGE); }}
            onPress={() => nav.push({ name: "detail", id: it.id })} />
        ))}
      </div>
    </div>
  );
}
