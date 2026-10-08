// Prototype data layer. Phase 1 replaces this module with calls to the FastAPI backend;
// the shapes here are the ones the API should return.
import catalog from "./mock/catalog.json";

export type MediaInfo = {
  container: string;
  video: string;
  resolution: string;
  hdr?: string;
  audio: string;
  size?: string;
};

export type Item = {
  id: string;
  type: "movie" | "show";
  title: string;
  year: number;
  rating: string;
  runtime?: number;
  genres: string[];
  score: number;
  addedDaysAgo: number;
  featured?: boolean;
  overview: string;
  seasons?: number[];
  media: MediaInfo;
  art: { poster: string; backdrop?: string };
};

export type Episode = {
  season: number;
  episode: number;
  title: string;
  runtime: number;
  overview: string;
};

export type Library = {
  id: string;
  name: string;
  type: "movie" | "show" | "music";
  paths: string[];
  scanEveryHours: number;
  lastScan: string;
  items: number;
  comingSoon?: boolean;
};

export type ContinueEntry = { item: Item; progress: number; season?: number; episode?: number };

export const items = catalog.items as Item[];
export const libraries = catalog.libraries as Library[];

export const byId = (id: string) => items.find((i) => i.id === id);
export const movies = items.filter((i) => i.type === "movie");
export const shows = items.filter((i) => i.type === "show");
export const featured = items.filter((i) => i.featured);
export const recentlyAdded = [...items].sort((a, b) => a.addedDaysAgo - b.addedDaysAgo);

export const continueWatching: ContinueEntry[] = catalog.continueWatching.map((c) => ({
  ...c,
  item: byId(c.id)!,
}));

export const posterUrl = (i: Item) => `/mock/posters/${i.id}.webp`;
export const backdropUrl = (i: Item) => (i.art.backdrop ? `/mock/backdrops/${i.id}.webp` : undefined);

export const allGenres = (list: Item[]) => [...new Set(list.flatMap((i) => i.genres))].sort();

/** What the server would do to play this in a typical Chromium browser. Mirrors PLAN.md §6. */
export type PlayMethod = "Direct Play" | "Direct Stream" | "Transcode";
export function playMethod(m: MediaInfo): PlayMethod {
  const browserVideo = m.video === "H.264";
  const browserAudio = /^(AAC|MP3)/.test(m.audio);
  if (!browserVideo) return "Transcode";
  if (m.container === "MP4" && browserAudio) return "Direct Play";
  return "Direct Stream";
}

// Deterministic fake episode titles so the season view has something to show.
const WORDS = ["Pilot", "Undertow", "Glass", "Static", "Homecoming", "The Long Night", "Fault Lines",
  "Second Wind", "Blackout", "Old Friends", "Signal", "Crossroads", "Embers", "The Visitor", "Low Tide",
  "Breaking Point", "Ghosts", "Paper Trail", "Aftershock", "Reunion", "Northbound", "Ashes", "Daybreak", "Finale"];

function hash(s: string) {
  let h = 2166136261;
  for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return h >>> 0;
}

export function episodes(show: Item, season: number): Episode[] {
  const count = show.seasons?.[season - 1] ?? 0;
  const base = show.genres.includes("Comedy") || show.genres.includes("Animation") ? 23 : 48;
  return Array.from({ length: count }, (_, k) => {
    const e = k + 1;
    const h = hash(`${show.id}-${season}-${e}`);
    const title = season === 1 && e === 1 ? "Pilot" : WORDS[h % WORDS.length];
    return {
      season,
      episode: e,
      title,
      runtime: base + (h % 9),
      overview: `${show.title} — season ${season}, episode ${e}. Placeholder synopsis until TMDB matching lands in phase 1.`,
    };
  });
}

export const sxe = (s: number, e: number) => `S${String(s).padStart(2, "0")}E${String(e).padStart(2, "0")}`;
export const fmtRuntime = (min?: number) => (min ? `${Math.floor(min / 60)}h ${min % 60}m` : "");
export const seasonsLabel = (i: Item) => {
  const n = i.seasons?.length ?? 0;
  return `${n} season${n === 1 ? "" : "s"}`;
};
