import { useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import type { ItemSummary, ServerLibrary } from "../api";
import { useAuth } from "../auth";
import { PosterCard } from "../components/Cards";
import { UnrecognizedFiles } from "../components/Identify";
import { useScope } from "../servers";
import { useApi } from "../useApi";
import { MusicLibrary } from "./Music";

const SORTS = { added: "Recently added", title: "Title", year: "Year", rating: "Rating" } as const;

export default function Library() {
  const { id } = useParams();
  const [sort, setSort] = useState<keyof typeof SORTS>("title");
  const [genre, setGenre] = useState<string | null>(null);
  const { data: lib, error, reload } = useApi<ServerLibrary>(`/api/libraries/${id}`);
  const { user } = useAuth();
  const { rid, libName } = useScope();
  // identifying files (Unrecognized tab) is done on the server they are on, not through another one
  const admin = rid === null && user.is_admin;
  const [params, setParams] = useSearchParams();
  const tab = admin && params.get("tab") === "unrecognized" ? "unrecognized" : "titles";
  const unrecognized = (lib?.files.unrecognized ?? 0) + (lib?.files.guessed ?? 0);  // incl. auto fill guesses to review
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
        <h1>{lib ? libName(lib.id, lib.name) : ""}</h1>
        {items && <span className="count">{list.length} {noun}</span>}
        {admin && (unrecognized > 0 || tab === "unrecognized") && (
          <div className="segmented lib-tabs">
            <button className={tab === "titles" ? "on" : ""} onClick={() => setParams({})}>{noun[0].toUpperCase() + noun.slice(1)}</button>
            <button className={tab === "unrecognized" ? "on" : ""} onClick={() => setParams({ tab: "unrecognized" })}>
              Unrecognized{unrecognized ? <span className="tab-count">{unrecognized}</span> : null}</button>
          </div>
        )}
        {tab === "titles" && <label className="sort">
          Sort
          <select value={sort} onChange={(e) => setSort(e.target.value as keyof typeof SORTS)}>
            {Object.entries(SORTS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>}
      </div>
      {tab === "unrecognized" && lib && (
        <>
          <p className="muted">Files in this library the scan couldn't place from their names, and files Auto fill placed
            by a best guess (check those, then keep, edit or leave them out). Paste a TMDB or IMDb link, or say what each one
            is (the fields suggest what's already in the library). Kept across rescans.</p>
          <UnrecognizedFiles libraryId={lib.id} onChange={reload} />
        </>
      )}
      {tab === "titles" && genres.length > 1 && (
        <div className="chips">
          <button className={`chip ${!genre ? "on" : ""}`} onClick={() => setGenre(null)}>All</button>
          {genres.map((g) => (
            <button key={g} className={`chip ${genre === g ? "on" : ""}`} onClick={() => setGenre(g)}>{g}</button>
          ))}
        </div>
      )}
      {tab === "titles" && <>
        {items && !items.length && <p className="muted">No {noun} found in this library yet.</p>}
        <div className="grid">
          {list.map((i) => <PosterCard key={i.id} item={i} />)}
        </div>
      </>}
    </div>
  );
}
