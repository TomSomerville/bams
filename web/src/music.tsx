import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, type QueueTrack } from "./api";

// The music player lives above the routes, so a song keeps playing while you browse.
// "file" tracks play the original bytes (the browser seeks with Range). "transcode" tracks are converted
// to AAC by the server; seeking restarts the stream at ?t=, so the clock is offset + currentTime.

type Music = {
  queue: QueueTrack[];
  index: number;
  current: QueueTrack | null;
  playing: boolean;
  time: number;
  duration: number;
  volume: number;
  error: string | null;
  /** Play `tracks` from `start` (optionally shuffled). */
  playTracks: (tracks: QueueTrack[], start?: number, shuffle?: boolean) => void;
  /** Play an artist, album or track by item id. */
  playItem: (itemId: number, opts?: { startTrackId?: number; shuffle?: boolean }) => Promise<void>;
  toggle: () => void;
  pause: () => void;
  next: () => void;
  prev: () => void;
  jump: (index: number) => void;
  /** Move a queued track to another place (drag to reorder). The current track keeps playing. */
  move: (from: number, to: number) => void;
  seek: (t: number) => void;
  setVolume: (v: number) => void;
  stop: () => void;
};

const Ctx = createContext<Music | null>(null);

export function useMusic(): Music {
  const m = useContext(Ctx);
  if (!m) throw new Error("useMusic outside MusicProvider");
  return m;
}

const loadVolume = () => {
  try {
    const v = parseFloat(localStorage.getItem("bams.volume") ?? "");
    return isFinite(v) ? Math.min(1, Math.max(0, v)) : 0.9;
  } catch {
    return 0.9;
  }
};

function shuffled<T>(xs: T[]): T[] {
  const a = [...xs];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

const srcFor = (t: QueueTrack, at: number) =>
  t.playback.mode === "transcode" ? `${t.playback.url}?t=${at.toFixed(2)}` : t.playback.url;

export function MusicProvider({ children }: { children: ReactNode }) {
  const audio = useRef<HTMLAudioElement>(null);
  const offset = useRef(0); // transcode streams: where the current stream started
  const [queue, setQueue] = useState<QueueTrack[]>([]);
  const [index, setIndex] = useState(-1);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [volume, setVolumeState] = useState(loadVolume);
  const [error, setError] = useState<string | null>(null);
  const current = index >= 0 ? queue[index] ?? null : null;

  const load = useCallback((t: QueueTrack, at = 0) => {
    const el = audio.current;
    if (!el) return;
    setError(null);
    offset.current = t.playback.mode === "transcode" ? at : 0;
    el.src = srcFor(t, at);
    if (t.playback.mode !== "transcode" && at) el.currentTime = at;
    setTime(at);
    el.play().catch(() => setPlaying(false));
  }, []);

  // Start the track whenever the current position in the queue changes.
  const loadedId = useRef<string | null>(null);
  useEffect(() => {
    const key = current ? `${index}:${current.id}` : null;
    if (!current || key === loadedId.current) return;
    loadedId.current = key;
    load(current);
  }, [current, index, load]);

  const playTracks = useCallback((tracks: QueueTrack[], start = 0, shuffle = false) => {
    let list = tracks.filter((t) => t.available);
    if (!list.length) return;
    let at = Math.max(0, list.findIndex((t) => t.id === tracks[start]?.id));
    if (shuffle) {
      list = shuffled(list);
      at = 0;
    }
    loadedId.current = null;
    setQueue(list);
    setIndex(at);
  }, []);

  const playItem = useCallback(async (itemId: number, opts: { startTrackId?: number; shuffle?: boolean } = {}) => {
    const tracks = await api.get<QueueTrack[]>(`/api/items/${itemId}/tracks`);
    const start = opts.startTrackId ? Math.max(0, tracks.findIndex((t) => t.id === opts.startTrackId)) : 0;
    playTracks(tracks, start, opts.shuffle);
  }, [playTracks]);

  const jump = useCallback((i: number) => {
    if (i < 0 || i >= queue.length) return;
    loadedId.current = null;
    setIndex(i);
  }, [queue.length]);

  const move = useCallback((from: number, to: number) => {
    if (from === to || from < 0 || to < 0 || from >= queue.length || to >= queue.length) return;
    const q = [...queue];
    const [t] = q.splice(from, 1);
    q.splice(to, 0, t);
    let i = index;
    if (from === index) i = to;
    else if (from < index && to >= index) i--;
    else if (from > index && to <= index) i++;
    if (current) loadedId.current = `${i}:${current.id}`; // same track, new place: don't restart it
    setQueue(q);
    setIndex(i);
  }, [queue, index, current]);

  const next = useCallback(() => {
    if (index + 1 < queue.length) jump(index + 1);
    else {
      audio.current?.pause();
      setPlaying(false);
    }
  }, [index, queue.length, jump]);

  const seek = useCallback((t: number) => {
    const el = audio.current;
    if (!el || !current) return;
    if (current.playback.mode === "transcode") load(current, t);
    else el.currentTime = t;
    setTime(t);
  }, [current, load]);

  const prev = useCallback(() => {
    if (time > 3 || index <= 0) seek(0);
    else jump(index - 1);
  }, [time, index, seek, jump]);

  const toggle = useCallback(() => {
    const el = audio.current;
    if (!el || !current) return;
    if (el.paused) el.play().catch(() => undefined);
    else el.pause();
  }, [current]);

  const pause = useCallback(() => audio.current?.pause(), []);

  const stop = useCallback(() => {
    const el = audio.current;
    if (el) {
      el.pause();
      el.removeAttribute("src");
      el.load();
    }
    loadedId.current = null;
    setQueue([]);
    setIndex(-1);
    setTime(0);
  }, []);

  const setVolume = useCallback((v: number) => {
    setVolumeState(v);
    try {
      localStorage.setItem("bams.volume", String(v));
    } catch {
      /* private mode: just don't remember it */
    }
  }, []);

  useEffect(() => {
    if (audio.current) audio.current.volume = volume;
  }, [volume]);

  // Media keys / lock screen / OS media flyout.
  useEffect(() => {
    if (!("mediaSession" in navigator)) return;
    const ms = navigator.mediaSession;
    ms.metadata = current
      ? new MediaMetadata({
          title: current.title, artist: current.artist, album: current.album,
          artwork: current.poster ? [{ src: new URL(current.poster, location.href).href }] : [],
        })
      : null;
    const handlers: [MediaSessionAction, MediaSessionActionHandler | null][] = [
      ["play", current ? () => toggle() : null],
      ["pause", current ? () => pause() : null],
      ["nexttrack", index + 1 < queue.length ? () => next() : null],
      ["previoustrack", current ? () => prev() : null],
      ["seekto", current ? (d) => d.seekTime != null && seek(d.seekTime) : null],
    ];
    for (const [action, h] of handlers) {
      try {
        ms.setActionHandler(action, h);
      } catch {
        /* action not supported by this browser */
      }
    }
  }, [current, index, queue.length, toggle, pause, next, prev, seek]);

  const duration = current?.duration ?? 0;
  const value = useMemo<Music>(() => ({
    queue, index, current, playing, time, duration, volume, error,
    playTracks, playItem, toggle, pause, next, prev, jump, move, seek, setVolume, stop,
  }), [queue, index, current, playing, time, duration, volume, error,
      playTracks, playItem, toggle, pause, next, prev, jump, move, seek, setVolume, stop]);

  return (
    <Ctx.Provider value={value}>
      {children}
      <audio
        ref={audio}
        preload="auto"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onTimeUpdate={(e) => setTime(offset.current + e.currentTarget.currentTime)}
        onEnded={next}
        onError={() => {
          if (!audio.current?.getAttribute("src")) return; // stopped on purpose
          setPlaying(false);
          setError("This track couldn't be played.");
        }}
      />
    </Ctx.Provider>
  );
}
