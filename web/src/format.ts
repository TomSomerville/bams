import type { ItemSummary, PlayMethod, QueueTrack } from "./api";

/** S01E02; an unnumbered episode (an extra in a season folder) is just S00. */
export const sxe = (s: number, e?: number | null) =>
  `S${String(s).padStart(2, "0")}${e == null ? "" : `E${String(e).padStart(2, "0")}`}`;

export const fmtRuntime = (min?: number | null) =>
  min ? (min >= 60 ? `${Math.floor(min / 60)}h ${min % 60}m` : `${min}m`) : "";

export const fmtSize = (b: number) => (b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.round(b / 1e6)} MB`);

export const seasonsLabel = (i: ItemSummary) => {
  const n = i.child_count ?? 0;
  return `${n} season${n === 1 ? "" : "s"}`;
};

/** An artist's records: "2 albums, 3 singles", "1 album", "3 singles" (singles only when there are some). */
export const recordsLabel = (i: ItemSummary) => {
  const singles = i.single_count ?? 0, albums = (i.child_count ?? 0) - singles;
  return albums || !singles
    ? [plural(albums, "album"), singles ? plural(singles, "single") : null].filter(Boolean).join(", ")
    : plural(singles, "single");
};

/** A song of an artist's singles (GET /api/items/:id/singles), with its single's year. Shared with the TV app. */
export type SingleTrack = QueueTrack & { year: number | null };
export type SingleSort = "year" | "title";
export const sortSingles = (list: SingleTrack[], by: SingleSort) => (by === "title"
  ? [...list].sort((a, b) => a.title.localeCompare(b.title, undefined, { sensitivity: "base", numeric: true }))
  : [...list].sort((a, b) => (a.year ?? 9999) - (b.year ?? 9999)));  // stable: a single's songs stay in order
/** A singles row's second line: the single's name when it isn't the song's, and its year. */
export const singleNote = (t: SingleTrack) =>
  [t.album.localeCompare(t.title, undefined, { sensitivity: "base" }) ? t.album : null, t.year].filter(Boolean).join(" · ") || null;

/** What Top Played Songs says when it has no songs to show (shared with the TV app). */
export const noTopSongs = (t: { token?: "missing" | "refused" | null }) =>
  t.token === "missing"
    ? "ListenBrainz now asks for a token before it shares listening stats. An admin can add one in Settings, under Music identification."
    : t.token === "refused"
      ? "ListenBrainz refused this server's token. An admin can replace it in Settings, under Music identification."
      : "ListenBrainz has no listening stats for this artist's songs here.";

export const subLabel = (i: ItemSummary) =>
  [i.year, i.kind === "show" ? seasonsLabel(i) : fmtRuntime(i.runtime)].filter(Boolean).join(" · ");

/** 194.1 -> "3:14", 4000 -> "1:06:40" */
export const fmtClock = (sec?: number | null) => {
  if (sec == null || !isFinite(sec)) return "";
  const s = Math.max(0, Math.floor(sec));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${r}` : `${m}:${r}`;
};

/** Album length: "34 min", "1 h 12 min" */
export const fmtLength = (sec?: number | null) => {
  if (!sec) return "";
  const m = Math.round(sec / 60);
  return m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m} min`;
};

export const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** Library types: what the UI calls them and their icon. */
export const LIB_TYPES = {
  show: { label: "TV Shows", icon: "tv" },
  movie: { label: "Movies", icon: "film" },
  music: { label: "Music", icon: "music" },
} as const;
export type LibType = keyof typeof LIB_TYPES;

export const PLAY_LABEL: Record<PlayMethod, string> = {
  direct_play: "Direct Play",
  direct_stream: "Direct Stream",
  transcode: "Transcode",
};

// ---- Music Home dates (shared with the TV app and the phone's offline pages: no React or storage here)

/** "YYYY-MM-DD" as a local date (new Date("YYYY-MM-DD") would be UTC midnight: the day before, west of Greenwich). */
export const localDate = (iso: string) => { const [y, m, d] = iso.split("-").map(Number); return new Date(y, m - 1, d); };
export const isoDate = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const md = (d: Date, opts: Intl.DateTimeFormatOptions = {}) => d.toLocaleDateString(undefined, { month: "short", day: "numeric", ...opts });
/** "Nov 15 – 21", "Dec 28 – Jan 3": a Music Home week. */
export const weekLabel = (start: string, end: string) => {
  const a = localDate(start), b = localDate(end);
  return `${md(a)} – ${a.getMonth() === b.getMonth() ? b.getDate() : md(b)}`;
};
/** "Nov 15, 1984": an album's release day. */
export const releasedLabel = (iso: string) => md(localDate(iso), { year: "numeric" });
/** "Thu, Dec 25" (or "Today"): a holiday's day. */
export const holidayDayLabel = (iso: string, today = new Date()) =>
  iso === isoDate(today) ? "Today" : md(localDate(iso), { weekday: "short" });
/** This calendar week, Sunday to Saturday, and its days as "MM-DD" (29 Feb counts in other years' week of 28 Feb), as
 *  the server's Music Home works it out (app.py `_this_week`): the phone's offline pages use it. */
export const thisWeek = (today = new Date()) => {
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate() - today.getDay());
  const days = Array.from({ length: 7 }, (_, i) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + i));
  const mds = days.map((d) => isoDate(d).slice(5));
  if (mds.includes("02-28") && !mds.includes("02-29")) mds.push("02-29");
  return { start: isoDate(days[0]), end: isoDate(days[6]), days: mds };
};
