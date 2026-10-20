import { useEffect, useMemo, useState } from "react";
import { apiFor, type Holidays, type ItemSummary, type ShownItem } from "../api";
import { holidayLabel, holidayPath, listedLook } from "../../../web/src/everywhere";
import { useFocusOnReady, useNav } from "../App";
import { Poster } from "../Cards";
import { PlayRandomButton } from "../random";
import { MusicLibrary } from "./Music";
import { session } from "../platform";

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
  const [sort, setSort] = useState<string>(() => session.get(`bams.sort.${key}`) || "title");
  const [items, setItems] = useState<ItemSummary[] | null>(null);
  const [shown, setShown] = useState(PAGE);
  const [err, setErr] = useState<string | null>(null);
  const [genre, setGenre] = useState<string | null>(() => session.get(`bams.genre.${key}`));
  // the web's holiday filters: this library's movies (or episodes) about the upcoming / recent holiday
  const [holidays, setHolidays] = useState<Holidays | null>(null);
  const [hol, setHol] = useState<"next" | "recent" | null>(null);
  const [holItems, setHolItems] = useState<ShownItem[] | null>(null);
  useEffect(() => {
    apiFor(rid).get<Holidays>("/api/holidays").then(setHolidays).catch(() => setHolidays(null));
  }, [rid]);
  useEffect(() => {
    setHolItems(null);
    if (hol) apiFor(rid).get<ShownItem[]>(holidayPath(hol, { library: id })).then(setHolItems).catch((e) => setErr((e as Error).message));
  }, [hol, id, rid]);

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
    if (g) session.set(`bams.genre.${key}`, g); else session.remove(`bams.genre.${key}`);
    setShown(PAGE);
    setHol(null);
    setGenre(g);
  };

  const pick = (s: string) => {
    session.set(`bams.sort.${key}`, s);
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
        {items !== null && items.length > 0 && <PlayRandomButton chip path={`/api/libraries/${id}/random`} rid={rid} />}
      </div>
      {err && <p className="error big">{err}</p>}
      {items === null && !err && <div className="spinner" />}
      {(genres.length > 1 || holidays) && (
        <div className="chips genres" data-row>
          <button className={`chip ${!genre && !hol ? "on" : ""}`} data-fid="genre-all" onClick={() => pickGenre(null)}>All</button>
          {holidays && (["next", "recent"] as const).map((w) => (
            <button key={w} className={`chip ${hol === w ? "on" : ""}`} data-fid={`holiday-${w}`} onClick={() => setHol(w)}>
              {w === "next" ? "Upcoming" : "Recent"}: {holidayLabel(holidays[w])}</button>
          ))}
          {genres.map((g) => (
            <button key={g} className={`chip ${genre === g && !hol ? "on" : ""}`} data-fid={`genre-${g}`} onClick={() => pickGenre(g)}>{g}</button>
          ))}
        </div>
      )}
      {items && !items.length && <p className="muted big">This library is empty.</p>}
      {hol && holItems === null && <div className="spinner" />}
      {hol && holItems && !holItems.length && holidays && (
        <p className="muted big">Nothing in this library is about {holidays[hol].name}.</p>
      )}
      {hol ? <div className="grid">
        {(holItems ?? []).map((it) => (
          <Poster key={it.id} item={it} rid={rid} fid={`hol-${it.id}`} look={listedLook(it)}
            onPress={() => nav.push({ name: "detail", id: it.id, rid })} />
        ))}
      </div> : <div className="grid">
        {list.slice(0, shown).map((it, i) => (
          <Poster key={it.id} item={it} rid={rid} fid={`item-${it.id}`} autoFocus={i === 0}
            onFocus={() => { if (i > shown - 30 && shown < list.length) setShown((n) => n + PAGE); }}
            onPress={() => nav.push({ name: "detail", id: it.id, rid })} />
        ))}
      </div>}
    </div>
  );
}
