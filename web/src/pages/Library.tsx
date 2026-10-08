import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import type { ItemSummary, ServerLibrary } from "../api";
import { PosterCard } from "../components/Cards";
import { useApi } from "../useApi";
import { MusicLibrary } from "./Music";

const SORTS = { added: "Recently added", title: "Title", year: "Year", rating: "Rating" } as const;

export default function Library() {
  const { id } = useParams();
  const [sort, setSort] = useState<keyof typeof SORTS>("title");
  const [genre, setGenre] = useState<string | null>(null);
  const { data: lib, error } = useApi<ServerLibrary>(`/api/libraries/${id}`);
  const isMusic = lib?.type === "music";
  const { data: items } = useApi<ItemSummary[]>(lib && !isMusic ? `/api/libraries/${id}/items?sort=${sort}` : null);

  const genres = useMemo(() => [...new Set((items ?? []).flatMap((i) => i.genres))].sort(), [items]);
  const list = (items ?? []).filter((i) => !genre || i.genres.includes(genre));
  const noun = lib?.type === "movie" ? "movies" : "shows";

  if (error) return <div className="page"><p className="key-msg bad">{error}</p></div>;
  if (lib && isMusic) return <MusicLibrary key={lib.id} lib={lib} />;
  return (
    <div className="page">
      <div className="page-head">
        <h1>{lib?.name ?? ""}</h1>
        {items && <span className="count">{list.length} {noun}</span>}
        <label className="sort">
          Sort
          <select value={sort} onChange={(e) => setSort(e.target.value as keyof typeof SORTS)}>
            {Object.entries(SORTS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
      </div>
      {genres.length > 1 && (
        <div className="chips">
          <button className={`chip ${!genre ? "on" : ""}`} onClick={() => setGenre(null)}>All</button>
          {genres.map((g) => (
            <button key={g} className={`chip ${genre === g ? "on" : ""}`} onClick={() => setGenre(g)}>{g}</button>
          ))}
        </div>
      )}
      {items && !items.length && <p className="muted">No {noun} found in this library yet.</p>}
      <div className="grid">
        {list.map((i) => <PosterCard key={i.id} item={i} />)}
      </div>
    </div>
  );
}
