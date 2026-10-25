import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import type { QueueTrack } from "./api";
import { useMusic } from "./music";
import Icon from "./components/Icon";
import { callFor, scopeLink, useScope } from "./servers";

// Play Random: a random selection of a library, show or artist, from the server (GET .../random).
// Music goes to the music player's queue. Movies and episodes go to the video queue here: the player follows it
// (its "next" is the queue's next, not the episode after) and lists it under "Up next", reorderable like the music
// queue. The queue lives above the routes (the player is re-created per video) and in sessionStorage (a reload).

export type VideoEntry = {
  id: number; kind: "movie" | "episode"; title: string; show: string | null;
  season_number: number | null; episode_number: number | null; runtime: number | null; year: number | null;
  art: string | null;
};
type Random = { type: "music"; tracks: QueueTrack[] } | { type: "video"; items: VideoEntry[] };

type VideoQueue = {
  /** the queue's server (null: this one) */
  rid: number | null;
  items: VideoEntry[];
  /** a holiday's Shuffle: what's watched from it is kept nowhere (no progress, not in Continue Watching) */
  untracked: boolean;
  /** where `id` is in the queue (-1: not in it, so the player plays on as usual) */
  indexOf: (id: number, rid: number | null) => number;
  move: (from: number, to: number) => void;
  /** Take a video out of the queue (the player never offers the one playing). */
  remove: (i: number) => void;
  clear: () => void;
  /** Play a random selection: `path` is "/api/libraries/3/random" or "/api/items/7/random". */
  playRandom: (path: string, rid: number | null, opts?: { untracked?: boolean }) => Promise<void>;
};

const Ctx = createContext<VideoQueue | null>(null);

export function useVideoQueue(): VideoQueue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useVideoQueue outside VideoQueueProvider");
  return v;
}

const KEY = "bams.videoQueue";
type Stored = { rid: number | null; items: VideoEntry[]; untracked?: boolean };

function load(): Stored {
  try {
    const s = JSON.parse(sessionStorage.getItem(KEY) ?? "null");
    if (s && Array.isArray(s.items)) return s;
  } catch {
    /* nothing kept */
  }
  return { rid: null, items: [] };
}

function save(s: Stored) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* private mode: it lasts until a reload */
  }
}

export function VideoQueueProvider({ children }: { children: ReactNode }) {
  const [q, setQ] = useState<Stored>(load);
  const music = useMusic();
  const nav = useNavigate();
  const set = (s: Stored) => { save(s); setQ(s); };

  const indexOf = useCallback((id: number, rid: number | null) =>
    rid === q.rid ? q.items.findIndex((x) => x.id === id) : -1, [q]);

  const move = useCallback((from: number, to: number) => {
    const list = [...q.items];
    if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return;
    const [x] = list.splice(from, 1);
    list.splice(to, 0, x);
    set({ ...q, items: list });
  }, [q]);

  const remove = useCallback((i: number) => set({ ...q, items: q.items.filter((_, k) => k !== i) }), [q]);

  const clear = useCallback(() => set({ rid: null, items: [] }), []);

  const { playTracks } = music;
  const playRandom = useCallback(async (path: string, rid: number | null, opts: { untracked?: boolean } = {}) => {
    const r = await callFor(rid).get<Random>(path);
    if (r.type === "music") {
      playTracks(r.tracks);  // already in random order
      return;
    }
    if (!r.items.length) return;
    set({ rid, items: r.items, untracked: !!opts.untracked });
    nav(scopeLink(rid, `/play/${r.items[0].id}`), { state: opts.untracked ? { shuffle: true } : undefined });
  }, [playTracks, nav]);

  const value = useMemo(() => ({ rid: q.rid, items: q.items, untracked: !!q.untracked, indexOf, move, remove, clear, playRandom }),
    [q, indexOf, move, remove, clear, playRandom]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** "Show · S01E02 · Title" or "Film (2001)", for the Up next list. */
export function entryLabel(e: VideoEntry): { title: string; sub: string } {
  if (e.kind === "movie") return { title: e.title, sub: [e.year, e.runtime ? `${e.runtime}m` : null].filter(Boolean).join(" · ") };
  const sxe = e.season_number != null && e.episode_number != null
    ? `S${String(e.season_number).padStart(2, "0")}E${String(e.episode_number).padStart(2, "0")}` : null;
  return { title: e.title, sub: [e.show, sxe].filter(Boolean).join(" · ") };
}

/** The "Play Random" button of a library, show or artist page (`path`: its /random endpoint on this page's server). */
export function PlayRandomButton({ path, className = "btn ghost" }: { path: string; className?: string }) {
  const { playRandom } = useVideoQueue();
  const { rid } = useScope();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const go = () => {
    setBusy(true);
    setFailed(false);
    playRandom(path, rid).catch(() => setFailed(true)).finally(() => setBusy(false));
  };
  return (
    <button className={className} onClick={go} disabled={busy} title={failed ? "Couldn't load a random selection" : "Play a random selection"}>
      <Icon name="shuffle" /> {failed ? "Try again" : "Play Random"}
    </button>
  );
}
