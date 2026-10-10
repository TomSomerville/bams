// Home and Search across every server a client shows (its own and the others it's connected to), the same on the
// web (pages/Home.tsx, pages/Search.tsx) and on the TV (tv/src/screens/Home.tsx, Search.tsx): which rows Home has,
// what each row asks each server, and how the answers are merged into one row. Each item is tagged with the
// server it came from (`rid`: null = the client's first server) so its card opens it there.
//
// Shared with the TV app (like homeRows.ts): keep it free of React, the router and browser-only APIs.

import type { ContinueItem, Genre, HomeRowPref, ItemSummary, ServerLibrary } from "./api";
import { homeRows, rowGenre } from "./homeRows";

/** One server to ask: `get` is that server's API (the client adds its token, and makes media links usable). */
export type Source = { rid: number | null; get: <T>(path: string) => Promise<T> };

export const ROW_SIZE = 30;
export const TOP_RATING = 7;   // "Top Rated" picks at random from titles rated at least this (TMDB, out of 10)
const ASK_TIMEOUT = 8000;      // a server that hasn't answered by then is left out of this row

/** A row's items: each one carries `rid`. */
export type Tagged<T> = T & { rid: number | null };

/** A key unique across servers (ids are per server). */
export const keyOf = (i: { id: number; rid?: number | null }) => `${i.rid ?? "h"}:${i.id}`;

function timeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise((res, rej) => {
    const t = setTimeout(() => rej(new Error("timeout")), ms);
    p.then((v) => { clearTimeout(t); res(v); }, (e) => { clearTimeout(t); rej(e); });
  });
}

/** Ask every source for `path`; `onList` is called as each one answers (a slow or offline server doesn't hold the
 *  others up; it's left out). Resolves once all have answered or given up. */
export async function askAll<T>(sources: Source[], path: string,
                                onList: (rid: number | null, list: Tagged<T>[]) => void): Promise<void> {
  await Promise.all(sources.map(async (s) => {
    try {
      const list = await timeout(s.get<T[]>(path), ASK_TIMEOUT);
      onList(s.rid, (list ?? []).map((x) => ({ ...x, rid: s.rid })));
    } catch {
      onList(s.rid, []);
    }
  }));
}

// ---- merging one row from several servers' answers (each list in that server's order)

/** Newest first, by when each server added it (Recently Added). */
export function newestFirst(lists: Tagged<ItemSummary>[][], n = ROW_SIZE): Tagged<ItemSummary>[] {
  return lists.flat().sort((a, b) => b.added_at - a.added_at).slice(0, n);
}

/** One from each server in turn (rows each server picks at random: Top Rated, the genres). */
export function interleave<T>(lists: T[][], n = ROW_SIZE): T[] {
  const out: T[] = [];
  for (let i = 0; out.length < n && lists.some((l) => i < l.length); i++) {
    for (const l of lists) if (i < l.length && out.length < n) out.push(l[i]);
  }
  return out;
}

/** Continue Watching: most recent activity first. Servers older than this field (no `last_watched_at`) are
 *  interleaved in their own order instead. */
export function continueOrder(lists: Tagged<ContinueItem>[][], n = ROW_SIZE): Tagged<ContinueItem>[] {
  const all = lists.flat();
  if (all.every((c) => typeof c.last_watched_at === "number")) {
    return all.sort((a, b) => (b.last_watched_at ?? 0) - (a.last_watched_at ?? 0)).slice(0, n);
  }
  return interleave(lists, n);
}

/** By title (Search). */
export function byTitle<T extends { title: string }>(lists: T[][], n = Infinity): T[] {
  return lists.flat().sort((a, b) => a.title.localeCompare(b.title, undefined, { sensitivity: "base" })).slice(0, n);
}

/** Every genre any server has, most titles first (counts added up). */
export function mergeGenres(lists: Genre[][]): Genre[] {
  const m = new Map<string, number>();
  for (const g of lists.flat()) m.set(g.name, (m.get(g.name) ?? 0) + g.count);
  return [...m].map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
}

// ---- Home

/** What a Home row shows and where its items come from. */
export type HomeRowSpec = {
  id: string;
  title: string;
  /** continue: wide cards that play; titles: posters; albums: square covers */
  kind: "continue" | "titles" | "albums";
  /** asked of every source, or only the first server (its own library rows) */
  path: string;
  everywhere: boolean;
  merge: "newest" | "mix" | "continue";
  /** hidden below this many items */
  min: number;
  /** the library the row is from ("See all") */
  library?: number;
};

/** Home's rows in the user's order (Settings → Home page, saved on their first server), the same on web and TV:
 *  Continue Watching, Recently Added, Top Rated and each genre combine every server; each library's row is
 *  that library's. `libs` are the first server's libraries, `genres` every server's (mergeGenres). */
export function homeSpecs(saved: HomeRowPref[], libs: ServerLibrary[], genres: Genre[]): HomeRowSpec[] {
  const out: HomeRowSpec[] = [];
  for (const r of homeRows(saved, libs, genres).filter((x) => x.show)) {
    const g = rowGenre(r.id);
    if (r.id === "continue") {
      out.push({ id: r.id, title: r.label, kind: "continue", path: "/api/continue", everywhere: true, merge: "continue", min: 1 });
    } else if (r.id === "recent") {
      out.push({ id: r.id, title: r.label, kind: "titles", path: `/api/items?kind=show,movie&sort=added&limit=${ROW_SIZE}`,
        everywhere: true, merge: "newest", min: 1 });
    } else if (r.id === "top_rated") {
      out.push({ id: r.id, title: r.label, kind: "titles", path: `/api/items?sort=random&min_rating=${TOP_RATING}&limit=${ROW_SIZE}`,
        everywhere: true, merge: "mix", min: 4 });
    } else if (g !== null) {
      out.push({ id: r.id, title: g, kind: "titles", path: `/api/items?sort=random&genre=${encodeURIComponent(g)}&limit=${ROW_SIZE}`,
        everywhere: true, merge: "mix", min: 1 });
    } else {
      const l = libs.find((x) => `lib:${x.id}` === r.id);
      if (!l) continue;
      // newest first; a show with new episodes counts as new again
      out.push(l.type === "music"
        ? { id: r.id, title: r.label, kind: "albums", path: `/api/libraries/${l.id}/items?kind=album&sort=added&limit=${ROW_SIZE}`,
            everywhere: false, merge: "newest", min: 1, library: l.id }
        : { id: r.id, title: r.label, kind: "titles", path: `/api/libraries/${l.id}/items?sort=recent&limit=${ROW_SIZE}`,
            everywhere: false, merge: "newest", min: 1, library: l.id });
    }
  }
  return out;
}

/** A row's items from the answers so far (one list per server that answered). */
export function mergeRow(spec: HomeRowSpec, lists: Tagged<ItemSummary>[][]): Tagged<ItemSummary>[] {
  if (spec.merge === "continue") return continueOrder(lists as Tagged<ContinueItem>[][]);
  if (spec.merge === "mix") return interleave(lists);
  // a library's own row keeps that library's order ("recent": a show with new episodes comes back up)
  return spec.everywhere ? newestFirst(lists) : lists.flat().slice(0, ROW_SIZE);
}

/** The banner: the newest titles (with art) of every server. */
export const HERO_SIZE = 6;
export const heroPath = "/api/items?kind=show,movie&sort=added&limit=40";
export function heroItems(lists: Tagged<ItemSummary>[][]): Tagged<ItemSummary>[] {
  return newestFirst(lists, 200).filter((i) => i.backdrop || i.poster).slice(0, HERO_SIZE);
}

// ---- Search: the same three asks on every server, merged by title

export const searchPaths = (q: string) => {
  const enc = encodeURIComponent(q.trim());
  return {
    video: `/api/items?sort=title&q=${enc}`,
    music: `/api/items?kind=artist,album&sort=title&q=${enc}`,
    tracks: `/api/items?kind=track&sort=title&q=${enc}&limit=50`,
  };
};
