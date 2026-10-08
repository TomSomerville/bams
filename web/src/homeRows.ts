import type { HomeRowPref, ServerLibrary } from "./api";

/** One row of Home, in the user's order (Settings → Home page). */
export type HomeRow = { id: string; label: string; show: boolean };

/** Home's rows in their default order: Continue Watching, Recently Added, each music library's new albums, each
 *  TV/movie library, Top Rated, then the most common genres. */
export function defaultRows(libs: ServerLibrary[]): Omit<HomeRow, "show">[] {
  return [
    { id: "continue", label: "Continue Watching" },
    { id: "recent", label: "Recently Added" },
    ...libs.filter((l) => l.type === "music").map((l) => ({ id: `lib:${l.id}`, label: `${l.name}: recently added` })),
    ...libs.filter((l) => l.type !== "music").map((l) => ({ id: `lib:${l.id}`, label: l.name })),
    { id: "top_rated", label: "Top Rated" },
    { id: "genres", label: "Genres (your most common ones)" },
  ];
}

/** The user's saved order applied to the rows that exist now. Saved rows that no longer exist (a removed library)
 *  are dropped; rows the user hasn't placed yet (a new library) are shown, after the row they follow by default. */
export function homeRows(saved: HomeRowPref[], libs: ServerLibrary[]): HomeRow[] {
  const all = defaultRows(libs);
  const byId = new Map(all.map((r) => [r.id, r]));
  const out: HomeRow[] = saved.filter((s) => byId.has(s.id)).map((s) => ({ ...byId.get(s.id)!, show: s.show }));
  all.forEach((r, i) => {
    if (out.some((o) => o.id === r.id)) return;
    const prev = i > 0 ? out.findIndex((o) => o.id === all[i - 1].id) : -1;
    out.splice(prev + 1, 0, { ...r, show: true });
  });
  return out;
}
