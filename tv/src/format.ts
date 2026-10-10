import type { ItemSummary } from "./api";

export function clock(s: number | null | undefined): string {
  if (s === null || s === undefined || !Number.isFinite(s)) return "--:--";
  s = Math.max(0, Math.floor(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  const mm = h ? String(m).padStart(2, "0") : String(m);
  return `${h ? `${h}:` : ""}${mm}:${String(sec).padStart(2, "0")}`;
}

export function runtime(min: number | null | undefined): string | null {
  if (!min) return null;
  const h = Math.floor(min / 60), m = Math.round(min % 60);
  return h ? `${h} h ${m} min` : `${m} min`;
}

export const sxe = (i: Pick<ItemSummary, "season_number" | "episode_number">) =>
  i.season_number !== undefined && i.season_number !== null
    ? `S${String(i.season_number).padStart(2, "0")}${i.episode_number !== undefined && i.episode_number !== null ? `E${String(i.episode_number).padStart(2, "0")}` : ""}`
    : "";

/** "2021 · 1 h 52 min · Drama, Thriller · ★ 7.4" */
export function metaLine(i: ItemSummary): string {
  return [i.year, runtime(i.runtime), i.genres?.slice(0, 3).join(", "), i.rating ? `★ ${i.rating.toFixed(1)}` : null]
    .filter(Boolean).join("  ·  ");
}

/** Share watched of a movie/episode (0-1), for the bar under a poster; null when not started. */
export function progressOf(i: ItemSummary): number | null {
  const p = i.progress;
  if (!p || !p.position || !p.duration) return null;
  return Math.min(1, p.position / p.duration);
}
