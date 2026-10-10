import type { Genre, HomeRowPref, ServerLibrary } from "./api";

/** One row of Home, in the user's order (Settings → Home page). */
export type HomeRow = { id: string; label: string; show: boolean };

/** The genre a "genre:<name>" row shows, or null for other rows. */
export const rowGenre = (id: string) => (id.startsWith("genre:") ? id.slice(6) : null);

/** Home's rows in their default order: Continue Watching, Recently Added, each TV/movie library's newest titles,
 *  each music library's new albums, Top Rated, then one row per genre (most titles first). */
export function defaultRows(libs: ServerLibrary[], genres: Genre[]): Omit<HomeRow, "show">[] {
  return [
    { id: "continue", label: "Continue Watching" },
    { id: "recent", label: "Recently Added" },
    ...libs.filter((l) => l.type !== "music").map((l) => ({ id: `lib:${l.id}`, label: `Recently Added ${l.name}` })),
    ...libs.filter((l) => l.type === "music").map((l) => ({ id: `lib:${l.id}`, label: `Recently Added ${l.name}` })),
    { id: "top_rated", label: "Top Rated" },  // a random pick of the well rated, not best first
    ...genres.map((g) => ({ id: `genre:${g.name}`, label: `Genre: ${g.name}` })),  // a random pick of each
  ];
}

/** The user's saved order applied to the rows that exist now. Saved rows that no longer exist (a removed library)
 *  are dropped; rows the user hasn't placed yet (a new library or genre) are shown, after the row they follow by
 *  default. An older save's single "genres" entry stands for every genre row it doesn't place itself. */
export function homeRows(saved: HomeRowPref[], libs: ServerLibrary[], genres: Genre[]): HomeRow[] {
  const all = defaultRows(libs, genres);
  const byId = new Map(all.map((r) => [r.id, r]));
  const placed = new Set(saved.map((s) => s.id));
  const expanded = saved.flatMap((s) => s.id !== "genres" ? [s]
    : genres.map((g) => ({ id: `genre:${g.name}`, show: s.show })).filter((g) => !placed.has(g.id)));
  const out: HomeRow[] = expanded.filter((s) => byId.has(s.id)).map((s) => ({ ...byId.get(s.id)!, show: s.show }));
  all.forEach((r, i) => {
    if (out.some((o) => o.id === r.id)) return;
    const prev = i > 0 ? out.findIndex((o) => o.id === all[i - 1].id) : -1;
    out.splice(prev + 1, 0, { ...r, show: true });
  });
  return out;
}
