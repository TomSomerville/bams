import { useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import type { Holidays, ItemDetail, ItemSummary, ServerLibrary, ShownItem } from "../api";
import { useAuth } from "../auth";
import { ListedCard, PosterCard } from "../components/Cards";
import FixMatch from "../components/FixMatch";
import { holidayLabel, holidayPath } from "../everywhere";
import { UnrecognizedFiles } from "../components/Identify";
import { useScope } from "../servers";
import { useApi } from "../useApi";
import { MusicLibrary } from "./Music";
import { PlayRandomButton } from "../random";

const SORTS = { added: "Recently added", title: "Title", year: "Year", rating: "Rating" } as const;

/** The filter chips above the titles: a genre, the upcoming / recent holiday (its movies, or a show library's
 *  episodes), or (admins) titles not identified on TMDB yet. */
type Filter = { genre: string } | "next" | "recent" | "unidentified" | null;
const UNIDENTIFIED = "pending,unmatched";

export default function Library() {
  const { id } = useParams();
  const [sort, setSort] = useState<keyof typeof SORTS>("title");
  const [filter, setFilter] = useState<Filter>(null);
  const genre = filter && typeof filter === "object" ? filter.genre : null;
  const which = filter === "next" || filter === "recent" ? filter : null;
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
  // the holidays (an older server has none: no holiday chips), and what a holiday or Unidentified filter shows
  const { data: holidays } = useApi<Holidays>(lib && !isMusic ? "/api/holidays" : null);
  const { data: holidayItems } = useApi<ShownItem[]>(lib && which ? holidayPath(which, { library: lib.id }) : null);
  const { data: unidentified, reload: reloadUnidentified } = useApi<ItemSummary[]>(
    lib && !isMusic && admin ? `/api/libraries/${id}/items?sort=${sort}&match_status=${UNIDENTIFIED}` : null);
  const [fixing, setFixing] = useState<ItemDetail | null>(null);
  const { call } = useScope();
  const fix = async (i: ItemSummary) => setFixing(await call.get<ItemDetail>(`/api/items/${i.id}`));

  const genres = useMemo(() => [...new Set((items ?? []).flatMap((i) => i.genres))].sort(), [items]);
  const list = filter === "unidentified" ? unidentified ?? [] : (items ?? []).filter((i) => !genre || i.genres.includes(genre));
  const noun = lib?.type === "movie" ? "movies" : "shows";

  if (error) return <div className="page"><p className="key-msg bad">{error}</p></div>;
  if (lib && isMusic) return <MusicLibrary key={lib.id} lib={lib} />;
  return (
    <div className="page">
      <div className="page-head">
        <h1>{lib ? libName(lib.id, lib.name) : ""}</h1>
        {items && <span className="count">{which ? `${holidayItems?.length ?? "…"} ${lib?.type === "movie" ? "movies" : "episodes"}`
          : `${list.length} ${noun}`}</span>}
        {lib && tab === "titles" && <PlayRandomButton className="btn ghost small page-random" path={`/api/libraries/${lib.id}/random`} />}
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
      {tab === "titles" && (genres.length > 1 || holidays || (unidentified?.length ?? 0) > 0) && (
        <div className="chips">
          <button className={`chip ${!filter ? "on" : ""}`} onClick={() => setFilter(null)}>All</button>
          {holidays && (["next", "recent"] as const).map((w) => (
            <button key={w} className={`chip holiday ${filter === w ? "on" : ""}`} onClick={() => setFilter(w)}
              title={w === "next" ? "The next holiday" : "The holiday just past"}>
              {w === "next" ? "Upcoming" : "Recent"}: {holidayLabel(holidays[w])}</button>
          ))}
          {admin && ((unidentified?.length ?? 0) > 0 || filter === "unidentified") && (
            <button className={`chip ${filter === "unidentified" ? "on" : ""}`} onClick={() => setFilter("unidentified")}
              title="Not identified on TMDB yet: pick one to fix its match">
              Unidentified<span className="tab-count">{unidentified?.length ?? 0}</span></button>
          )}
          {genres.length > 1 && genres.map((g) => (
            <button key={g} className={`chip ${genre === g ? "on" : ""}`} onClick={() => setFilter({ genre: g })}>{g}</button>
          ))}
        </div>
      )}
      {tab === "titles" && which && <>
        {holidayItems && !holidayItems.length && holidays && (
          <p className="muted">Nothing in this library is about {holidays[which].name}.</p>
        )}
        <div className="grid">
          {(holidayItems ?? []).map((i) => <ListedCard key={i.id} item={i} />)}
        </div>
      </>}
      {tab === "titles" && filter === "unidentified" && (
        <p className="muted">Not identified on TMDB yet: pick one to search TMDB and fix its match.</p>
      )}
      {tab === "titles" && !which && <>
        {items && !items.length && <p className="muted">No {noun} found in this library yet.</p>}
        <div className="grid">
          {list.map((i) => filter === "unidentified"
            ? <div key={i.id} className="fix-card" onClickCapture={(e) => { e.preventDefault(); e.stopPropagation(); void fix(i); }}>
                <PosterCard item={i} /></div>
            : <PosterCard key={i.id} item={i} />)}
        </div>
      </>}
      {fixing && <FixMatch item={fixing} onClose={() => { setFixing(null); reloadUnidentified(); }} />}
    </div>
  );
}
