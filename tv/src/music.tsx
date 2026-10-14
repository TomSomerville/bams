// Music on the TV: one <audio> for the whole app (it keeps playing while you browse), a queue, play/pause/next/
// previous from the on-screen bar (NowPlaying) and the remote's media keys (App.tsx). Tracks can come from any of
// the TV's servers (`rid`). Like the web player (web/src/music.tsx) without the gapless hand-over: a track the
// server plays as-is ("file") seeks with Range; a converted one ("transcode", /audio?t=) restarts at t. CUE tracks
// are stretches of one file (start/end). If the TV can't decode a file after all, it asks for the conversion.

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { apiFor, mediaFor, type QueueTrack } from "./api";

export type Track = QueueTrack & { rid: number | undefined };

type Music = {
  queue: Track[];
  index: number;
  current: Track | null;
  playing: boolean;
  /** seconds into the track, and its length */
  time: number;
  duration: number;
  error: string | null;
  /** the TV couldn't decode the file as it is: it's playing the server's conversion (the quality line says so) */
  converted: boolean;
  playTracks: (tracks: QueueTrack[], rid: number | undefined, start?: number, shuffle?: boolean) => void;
  /** an artist, album or track by id: its play queue from the server */
  playItem: (id: number, rid: number | undefined, opts?: { shuffle?: boolean; startTrackId?: number }) => Promise<void>;
  toggle: () => void;
  pause: () => void;
  next: () => void;
  prev: () => void;
  stop: () => void;
  /** Up next (Queue.tsx): play queue place `i`, move a track, take one out (not the one playing) */
  jump: (i: number) => void;
  move: (from: number, to: number) => void;
  remove: (i: number) => void;
};

const Ctx = createContext<Music | null>(null);
export const useMusic = () => useContext(Ctx)!;

const startOf = (t: Track) => t.start ?? 0;

function shuffled<T>(a: T[]): T[] {
  const b = [...a];
  for (let i = b.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [b[i], b[j]] = [b[j], b[i]];
  }
  return b;
}

export function MusicProvider({ children }: { children: ReactNode }) {
  const audio = useRef<HTMLAudioElement | null>(null);
  if (!audio.current && typeof Audio !== "undefined") audio.current = new Audio();
  const [queue, setQueue] = useState<Track[]>([]);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [convertedNow, setConverted] = useState(false);
  const q = useRef<Track[]>([]);
  const idx = useRef(0);
  const offset = useRef(0);          // a converted stream starts at ?t=: its clock starts there
  const converted = useRef(false);   // this track is playing the server's conversion (a fallback after an error)

  const current = queue[index] ?? null;
  const duration = current ? (current.end ?? (current.duration != null ? startOf(current) + current.duration : 0)) - startOf(current) : 0;

  const load = useCallback((t: Track, from: number, convert = false) => {
    const e = audio.current;
    if (!e) return;
    const m = mediaFor(t.rid);
    converted.current = convert;
    setConverted(convert);
    setError(null);
    if (convert || t.playback.mode === "transcode") {
      const url = convert ? `/api/files/${t.file_id}/audio` : t.playback.url;
      offset.current = from;
      e.src = `${m(url)}?t=${from.toFixed(2)}`;
    } else {
      offset.current = 0;
      e.src = m(t.playback.url) ?? "";
      e.currentTime = from;
    }
    void e.play().catch(() => undefined);
  }, []);

  const startAt = useCallback((i: number) => {
    const t = q.current[i];
    if (!t) return;
    idx.current = i;
    setIndex(i);
    setTime(0);
    load(t, startOf(t));
  }, [load]);

  const next = useCallback(() => {
    if (idx.current + 1 < q.current.length) startAt(idx.current + 1);
    else {
      audio.current?.pause();
      setPlaying(false);
    }
  }, [startAt]);

  const prev = useCallback(() => {
    // a few seconds in: back to the start of this track; else the one before
    if (time > 4 || idx.current === 0) startAt(idx.current);
    else startAt(idx.current - 1);
  }, [startAt, time]);

  useEffect(() => {
    const e = audio.current;
    if (!e) return;
    const onTime = () => {
      const t = q.current[idx.current];
      if (!t) return;
      const abs = offset.current + e.currentTime;
      setTime(Math.max(0, abs - startOf(t)));
      if (t.end != null && abs >= t.end) next();  // a CUE track ends inside its file
    };
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onEnded = () => next();
    const onError = () => {
      const t = q.current[idx.current];
      if (!t) return;
      // the TV couldn't decode it as-is: the server's conversion, from where it was
      if (!converted.current && t.playback.mode === "file") load(t, offset.current + (e.currentTime || startOf(t)), true);
      else setError(`Couldn't play ${t.title}.`);
    };
    e.addEventListener("timeupdate", onTime);
    e.addEventListener("play", onPlay);
    e.addEventListener("pause", onPause);
    e.addEventListener("ended", onEnded);
    e.addEventListener("error", onError);
    return () => {
      e.removeEventListener("timeupdate", onTime);
      e.removeEventListener("play", onPlay);
      e.removeEventListener("pause", onPause);
      e.removeEventListener("ended", onEnded);
      e.removeEventListener("error", onError);
    };
  }, [next, load]);

  const playTracks = useCallback((tracks: QueueTrack[], rid: number | undefined, start = 0, shuffle = false) => {
    let list: Track[] = tracks.filter((t) => t.available).map((t) => ({ ...t, rid }));
    if (!list.length) return;
    let at = Math.max(0, list.findIndex((t) => t.id === tracks[start]?.id));
    if (shuffle) {
      list = shuffled(list);
      at = 0;
    }
    q.current = list;
    setQueue(list);
    startAt(at);
  }, [startAt]);

  const playItem = useCallback(async (id: number, rid: number | undefined, opts: { shuffle?: boolean; startTrackId?: number } = {}) => {
    const tracks = await apiFor(rid).get<QueueTrack[]>(`/api/items/${id}/tracks`);
    const start = opts.startTrackId ? Math.max(0, tracks.findIndex((t) => t.id === opts.startTrackId)) : 0;
    playTracks(tracks, rid, start, opts.shuffle);
  }, [playTracks]);

  const toggle = useCallback(() => {
    const e = audio.current;
    if (!e || !q.current.length) return;
    if (e.paused) void e.play().catch(() => undefined);
    else e.pause();
  }, []);
  const pause = useCallback(() => audio.current?.pause(), []);
  const stop = useCallback(() => {
    const e = audio.current;
    if (e) {
      e.pause();
      e.removeAttribute("src");
      e.load();
    }
    q.current = [];
    setQueue([]);
    setIndex(0);
    setPlaying(false);
  }, []);

  const jump = useCallback((i: number) => {
    if (i >= 0 && i < q.current.length) startAt(i);
  }, [startAt]);

  const move = useCallback((from: number, to: number) => {
    const list = [...q.current];
    if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return;
    const [t] = list.splice(from, 1);
    list.splice(to, 0, t);
    let i = idx.current;
    if (from === i) i = to;
    else if (from < i && to >= i) i--;
    else if (from > i && to <= i) i++;
    q.current = list;
    setQueue(list);  // same track, new place: it keeps playing
    idx.current = i;
    setIndex(i);
  }, []);

  const remove = useCallback((i: number) => {
    if (i < 0 || i >= q.current.length || i === idx.current) return;
    q.current = q.current.filter((_, k) => k !== i);
    setQueue(q.current);
    if (i < idx.current) {
      idx.current--;
      setIndex(idx.current);
    }
  }, []);

  const value = useMemo<Music>(() => ({
    queue, index, current, playing, time, duration, error, converted: convertedNow, playTracks, playItem, toggle, pause, next,
    prev, stop, jump, move, remove,
  }), [queue, index, current, playing, time, duration, error, convertedNow, playTracks, playItem, toggle, pause, next, prev, stop, jump, move, remove]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
