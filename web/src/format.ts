import type { ItemSummary, PlayMethod } from "./api";

export const sxe = (s: number, e: number) => `S${String(s).padStart(2, "0")}E${String(e).padStart(2, "0")}`;

export const fmtRuntime = (min?: number | null) =>
  min ? (min >= 60 ? `${Math.floor(min / 60)}h ${min % 60}m` : `${min}m`) : "";

export const fmtSize = (b: number) => (b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.round(b / 1e6)} MB`);

export const seasonsLabel = (i: ItemSummary) => {
  const n = i.child_count ?? 0;
  return `${n} season${n === 1 ? "" : "s"}`;
};

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
