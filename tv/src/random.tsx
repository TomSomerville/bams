// Play Random on the TV, as on the web (web/src/random.tsx): a random selection of a library, show or artist from the
// server (GET .../random). Music goes to the music player's queue; movies and episodes to the video queue here, which
// the player follows (its "next" is the queue's next) and lists under "Up next" (Queue.tsx). The queue is kept in
// sessionStorage, so it outlives the player, which is re-created for every video.

import { useState, useSyncExternalStore } from "react";
import { apiFor, type QueueTrack } from "./api";
import { useNav } from "./App";
import Icon from "./Icon";
import { useMusic } from "./music";
import { session } from "./platform";

export type VideoEntry = {
  id: number; kind: "movie" | "episode"; title: string; show: string | null;
  season_number: number | null; episode_number: number | null; runtime: number | null; year: number | null;
  art: string | null;
};
type Random = { type: "music"; tracks: QueueTrack[] } | { type: "video"; items: VideoEntry[] };
type Stored = { rid: number | null; items: VideoEntry[] };

const KEY = "bams.videoQueue";
const EMPTY: Stored = { rid: null, items: [] };

function load(): Stored {
  try {
    const s = JSON.parse(session.get(KEY) ?? "null");
    if (s && Array.isArray(s.items)) return s;
  } catch {
    /* nothing kept */
  }
  return EMPTY;
}

let state: Stored = load();
const listeners = new Set<() => void>();

function set(s: Stored) {
  state = s;
  try {
    session.set(KEY, JSON.stringify(s));
  } catch {
    /* lasts until the app restarts */
  }
  listeners.forEach((f) => f());
}

/** The video queue, re-rendering when it changes. */
export function useVideoQueue(): Stored {
  return useSyncExternalStore((f) => { listeners.add(f); return () => listeners.delete(f); }, () => state);
}

/** Where video `id` of server `rid` is in the queue (-1: not in it, so the player goes on as usual). */
export function queueIndex(id: number, rid: number | undefined): number {
  return (rid ?? null) === state.rid ? state.items.findIndex((x) => x.id === id) : -1;
}

/** The video after `id` in the queue, or undefined when it's not in the queue (null: it's the last one). */
export function queueNext(id: number, rid: number | undefined): number | null | undefined {
  const i = queueIndex(id, rid);
  return i < 0 ? undefined : state.items[i + 1]?.id ?? null;
}

export function moveVideo(from: number, to: number) {
  const list = [...state.items];
  if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return;
  const [x] = list.splice(from, 1);
  list.splice(to, 0, x);
  set({ ...state, items: list });
}

export function removeVideo(i: number) {
  set({ ...state, items: state.items.filter((_, k) => k !== i) });
}

/** "Show · S01E02" or "2001 · 104m", under a queue entry's title. */
export function entrySub(e: VideoEntry): string {
  if (e.kind === "movie") return [e.year, e.runtime ? `${e.runtime}m` : null].filter(Boolean).join("  ·  ");
  const sxe = e.season_number != null && e.episode_number != null
    ? `S${String(e.season_number).padStart(2, "0")}E${String(e.episode_number).padStart(2, "0")}` : null;
  return [e.show, sxe].filter(Boolean).join("  ·  ");
}

/** The "Play Random" button of a library, show or artist (`path`: its /random endpoint on server `rid`). */
export function PlayRandomButton({ path, rid, fid = "random", chip = false }: {
  path: string; rid?: number; fid?: string; chip?: boolean;
}) {
  const nav = useNav();
  const music = useMusic();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const go = async () => {
    if (busy) return;
    setBusy(true);
    setFailed(false);
    try {
      const r = await apiFor(rid).get<Random>(path);
      if (r.type === "music") music.playTracks(r.tracks, rid);  // already in random order
      else if (r.items.length) {
        set({ rid: rid ?? null, items: r.items });
        nav.push({ name: "player", id: r.items[0].id, rid, resume: false });
      }
    } catch {
      setFailed(true);
    }
    setBusy(false);
  };
  return (
    <button className={chip ? "chip" : "btn"} data-fid={fid} onClick={() => void go()}>
      <Icon name="shuffle" size={chip ? 26 : 30} /> {failed ? "Try again" : busy ? "Loading…" : "Play Random"}
    </button>
  );
}
