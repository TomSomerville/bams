import { useMemo, useState } from "react";
import { allGenres, movies, shows } from "../data";
import { PosterCard } from "../components/Cards";

const SORTS = {
  added: { label: "Recently added", fn: (a: { addedDaysAgo: number }, b: { addedDaysAgo: number }) => a.addedDaysAgo - b.addedDaysAgo },
  title: { label: "Title", fn: (a: { title: string }, b: { title: string }) => a.title.localeCompare(b.title) },
  year: { label: "Year", fn: (a: { year: number }, b: { year: number }) => b.year - a.year },
  score: { label: "Rating", fn: (a: { score: number }, b: { score: number }) => b.score - a.score },
} as const;

export default function Library({ type }: { type: "movie" | "show" }) {
  const source = type === "movie" ? movies : shows;
  const [genre, setGenre] = useState<string | null>(null);
  const [sort, setSort] = useState<keyof typeof SORTS>("added");
  const list = useMemo(
    () => source.filter((i) => !genre || i.genres.includes(genre)).sort(SORTS[sort].fn),
    [source, genre, sort],
  );

  return (
    <div className="page">
      <div className="page-head">
        <h1>{type === "movie" ? "Movies" : "TV Shows"}</h1>
        <span className="count">{list.length} {type === "movie" ? "movies" : "shows"}</span>
        <label className="sort">
          Sort
          <select value={sort} onChange={(e) => setSort(e.target.value as keyof typeof SORTS)}>
            {Object.entries(SORTS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
        </label>
      </div>
      <div className="chips">
        <button className={`chip ${!genre ? "on" : ""}`} onClick={() => setGenre(null)}>All</button>
        {allGenres(source).map((g) => (
          <button key={g} className={`chip ${genre === g ? "on" : ""}`} onClick={() => setGenre(g)}>{g}</button>
        ))}
      </div>
      <div className="grid">
        {list.map((i) => <PosterCard key={i.id} item={i} />)}
      </div>
    </div>
  );
}
