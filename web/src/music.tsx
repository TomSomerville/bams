import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, type QueueTrack } from "./api";
import { app, appPlaysMusic } from "./android";
import { callFor } from "./servers";

// The music player lives above the routes, so a song keeps playing while you browse.
// "file" tracks play the original bytes (the browser seeks with Range). "transcode" tracks are converted
// by the server; seeking restarts the stream at ?t=, so the clock is offset + currentTime.
//
// CUE-sheet tracks are stretches of one file (start/end, in seconds): the player seeks to the start and moves
// on at the end. Consecutive CUE tracks of one file play as one continuous stream (gapless, as recorded).
//
// Gapless between files: there are two <audio> elements. While one plays, the next track is loaded into the
// other a little before the end, and started the moment the current track ends (a timer armed from the
// element's own clock, with `ended` as the fallback), instead of only beginning to load then.
//
// In the Android app the page doesn't play music itself: AppMusicProvider hands the queue to the app's player
// (android/…/Music.kt), which plays on with the screen locked and shows on the lock screen and headphones.

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
  /** Play an artist, album or track by item id (rid: of another BAMS server, servers.tsx). */
  playItem: (itemId: number, opts?: { startTrackId?: number; shuffle?: boolean; rid?: number | null }) => Promise<void>;
  toggle: () => void;
  pause: () => void;
  next: () => void;
  prev: () => void;
  jump: (index: number) => void;
  /** Move a queued track to another place (drag to reorder). The current track keeps playing. */
  move: (from: number, to: number) => void;
  /** Take a queued track out (not the one playing). */
  remove: (i: number) => void;
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

const PRELOAD_BEFORE = 20; // seconds before the end of a track to start loading the next one
const ARM_BEFORE = 1.5; // seconds before the end to arm the exact hand-over timer

const startOf = (t: QueueTrack) => t.start ?? 0;
/** The next track carries straight on from this one in the same stream (consecutive CUE tracks). */
const continuous = (a: QueueTrack, b: QueueTrack | undefined) =>
  !!b && a.end != null && b.start != null && a.file_id === b.file_id && a.playback.mode === b.playback.mode &&
  Math.abs(b.start - a.end) < 0.05;

/** What each <audio> element holds: which track, and (converted streams) where in the file its stream starts. */
type Slot = { track: QueueTrack | null; offset: number };

export function MusicProvider({ children }: { children: ReactNode }) {
  return appPlaysMusic ? <AppMusicProvider>{children}</AppMusicProvider> : <BrowserMusicProvider>{children}</BrowserMusicProvider>;
}

function BrowserMusicProvider({ children }: { children: ReactNode }) {
  const els = [useRef<HTMLAudioElement>(null), useRef<HTMLAudioElement>(null)];
  const slots = useRef<Slot[]>([{ track: null, offset: 0 }, { track: null, offset: 0 }]);
  const active = useRef(0);
  const timer = useRef<number | null>(null);
  const [queue, setQueueState] = useState<QueueTrack[]>([]);
  const [index, setIndexState] = useState(-1);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [volume, setVolumeState] = useState(loadVolume);
  const [error, setError] = useState<string | null>(null);
  // Event handlers and timers read these, so they never see a stale queue.
  const q = useRef<QueueTrack[]>([]);
  const idx = useRef(-1);
  const current = index >= 0 ? queue[index] ?? null : null;

  const setQueue = (list: QueueTrack[]) => { q.current = list; setQueueState(list); };
  const setIndex = (i: number) => { idx.current = i; setIndexState(i); };
  const el = (n = active.current) => els[n].current;
  const disarm = () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
  };

  /** Seconds into the file the active element is at. */
  const absTime = () => slots.current[active.current].offset + (el()?.currentTime ?? 0);

  /** Put `t` in element `n`, `at` seconds into the track. */
  const fill = (n: number, t: QueueTrack, at: number) => {
    const e = el(n);
    if (!e) return;
    const from = startOf(t) + at;
    if (t.playback.mode === "transcode") {
      slots.current[n] = { track: t, offset: from };
      e.src = `${t.playback.url}?t=${from.toFixed(2)}`;
    } else {
      slots.current[n] = { track: t, offset: 0 };
      if (e.getAttribute("src") !== t.playback.url) e.src = t.playback.url;
      e.currentTime = from;
    }
  };

  /** Start queue position `i` from scratch in the active element (a jump, or no preloaded hand-over). */
  const startAt = useCallback((i: number, at = 0) => {
    const t = q.current[i];
    if (!t) return;
    disarm();
    const other = el(1 - active.current);
    if (other) {
      other.pause();
      other.removeAttribute("src");
      other.load();
    }
    slots.current[1 - active.current] = { track: null, offset: 0 };
    setError(null);
    setIndex(i);
    fill(active.current, t, at);
    setTime(at);
    el()?.play().catch(() => setPlaying(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** The current track has reached its end: carry on with the next one, as seamlessly as we can. */
  const advance = useCallback(() => {
    disarm();
    const i = idx.current;
    const cur = q.current[i];
    const nxt = q.current[i + 1];
    if (!cur) return;
    if (!nxt) {
      el()?.pause();
      setPlaying(false);
      return;
    }
    if (continuous(cur, nxt)) {
      slots.current[active.current] = { ...slots.current[active.current], track: nxt };
      setIndex(i + 1); // same stream, already playing it
      return;
    }
    const n = 1 - active.current;
    const other = el(n);
    if (other && slots.current[n].track === nxt) {
      const prev = el();
      other.play().then(() => {
        prev?.pause();
      }).catch(() => startAt(i + 1)); // e.g. a phone that only lets the element the user started play
      active.current = n;
      setIndex(i + 1);
      setTime(0);
      return;
    }
    startAt(i + 1);
  }, [startAt]);

  /** On every clock tick of the playing element: preload the next track, and arm the hand-over at the end. */
  const tick = useCallback(() => {
    const e = el();
    const t = slots.current[active.current].track;
    if (!e || !t || t !== q.current[idx.current]) return;
    const abs = absTime();
    setTime(Math.max(0, abs - startOf(t)));
    const fileEnd = t.playback.mode === "file" && isFinite(e.duration) ? e.duration : null;
    const end = t.end ?? fileEnd; // a converted whole file: we don't know its exact end; `ended` says
    const estEnd = end ?? (t.duration != null ? startOf(t) + t.duration : null);
    const nxt = q.current[idx.current + 1];
    if (estEnd !== null && estEnd - abs < PRELOAD_BEFORE && nxt && !continuous(t, nxt)) {
      const n = 1 - active.current;
      if (slots.current[n].track !== nxt) fill(n, nxt, 0); // setting src starts loading (preload="auto")
    }
    if (end !== null && !e.paused && timer.current === null) {
      const left = end - abs;
      if (left <= 0) advance();
      else if (left < ARM_BEFORE) timer.current = window.setTimeout(advance, (left / (e.playbackRate || 1)) * 1000);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [advance]);

  const playTracks = useCallback((tracks: QueueTrack[], start = 0, shuffle = false) => {
    let list = tracks.filter((t) => t.available);
    if (!list.length) return;
    let at = Math.max(0, list.findIndex((t) => t.id === tracks[start]?.id));
    if (shuffle) {
      list = shuffled(list);
      at = 0;
    }
    setQueue(list);
    startAt(at);
  }, [startAt]);

  const playItem = useCallback(async (itemId: number, opts: { startTrackId?: number; shuffle?: boolean; rid?: number | null } = {}) => {
    const tracks = await callFor(opts.rid ?? null).get<QueueTrack[]>(`/api/items/${itemId}/tracks`);
    const start = opts.startTrackId ? Math.max(0, tracks.findIndex((t) => t.id === opts.startTrackId)) : 0;
    playTracks(tracks, start, opts.shuffle);
  }, [playTracks]);

  const jump = useCallback((i: number) => {
    if (i >= 0 && i < q.current.length) startAt(i);
  }, [startAt]);

  const move = useCallback((from: number, to: number) => {
    const list = q.current;
    if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return;
    const nq = [...list];
    const [t] = nq.splice(from, 1);
    nq.splice(to, 0, t);
    let i = idx.current;
    if (from === i) i = to;
    else if (from < i && to >= i) i--;
    else if (from > i && to <= i) i++;
    setQueue(nq); // same track, new place: it keeps playing (a preloaded next track no longer next is ignored)
    setIndex(i);
  }, []);

  const remove = useCallback((i: number) => {
    const list = q.current;
    if (i < 0 || i >= list.length || i === idx.current) return;
    setQueue(list.filter((_, k) => k !== i));
    if (i < idx.current) setIndex(idx.current - 1);
  }, []);

  const next = useCallback(() => {
    if (idx.current + 1 < q.current.length) startAt(idx.current + 1);
    else {
      el()?.pause();
      setPlaying(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startAt]);

  const seek = useCallback((t: number) => {
    const e = el();
    const cur = q.current[idx.current];
    if (!e || !cur) return;
    disarm();
    if (cur.playback.mode === "transcode") {
      fill(active.current, cur, t);
      e.play().catch(() => setPlaying(false));
    } else e.currentTime = startOf(cur) + t;
    setTime(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const prev = useCallback(() => {
    if (time > 3 || idx.current <= 0) seek(0);
    else startAt(idx.current - 1);
  }, [time, seek, startAt]);

  const toggle = useCallback(() => {
    const e = el();
    if (!e || !q.current[idx.current]) return;
    if (e.paused) e.play().catch(() => undefined);
    else e.pause();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pause = useCallback(() => el()?.pause(), []); // eslint-disable-line react-hooks/exhaustive-deps

  const stop = useCallback(() => {
    disarm();
    for (const r of els) {
      const e = r.current;
      if (e) {
        e.pause();
        e.removeAttribute("src");
        e.load();
      }
    }
    slots.current = [{ track: null, offset: 0 }, { track: null, offset: 0 }];
    setQueue([]);
    setIndex(-1);
    setTime(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
    for (const r of els) if (r.current) r.current.volume = volume;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [volume]);

  useEffect(() => disarm, []);

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
    playTracks, playItem, toggle, pause, next, prev, jump, move, remove, seek, setVolume, stop,
  }), [queue, index, current, playing, time, duration, volume, error,
      playTracks, playItem, toggle, pause, next, prev, jump, move, remove, seek, setVolume, stop]);

  // Only the active element's events count; the other one is just loading the next track.
  const mine = (n: number) => n === active.current;
  return (
    <Ctx.Provider value={value}>
      {children}
      {[0, 1].map((n) => (
        <audio
          key={n}
          ref={els[n]}
          preload="auto"
          onPlay={() => mine(n) && setPlaying(true)}
          onPause={() => {
            if (!mine(n)) return;
            disarm();
            setPlaying(false);
          }}
          onSeeking={() => mine(n) && disarm()}
          onTimeUpdate={() => mine(n) && tick()}
          onEnded={() => mine(n) && advance()}
          onError={() => {
            if (!els[n].current?.getAttribute("src")) return; // emptied on purpose
            if (!mine(n)) {
              slots.current[n] = { track: null, offset: 0 }; // preload failed: the hand-over will load it normally
              return;
            }
            setPlaying(false);
            setError("This track couldn't be played.");
          }}
        />
      ))}
    </Ctx.Provider>
  );
}

// ---- in the Android app: the app's player plays, this page shows it

/** The app's player as the page sees it (Music.kt `state`, sent as `bams:music` events). */
type AppState = {
  ready: boolean; playing?: boolean; index?: number; position?: number; duration?: number | null;
  queue?: string[]; volume?: number; error?: string | null;
};

const SAVED = "bams.appMusic";  // this page's queue, kept while the app shows other pages (the player plays on)
const TICKET_REFRESH = 6 * 3600 * 1000;
let ticket: { prefix: string; at: number } | null = null;

/** A media link the app's player can open without this page's sign-in cookie: this server's through a media ticket
 *  (as the TV app does); another server's links are ticket URLs already (servers.tsx `rewrite`). */
async function playable(p: string | null): Promise<string | null> {
  if (!p) return null;
  if (/^https?:\/\//.test(p)) return p;
  if (!ticket || Date.now() - ticket.at > TICKET_REFRESH) {
    ticket = { prefix: (await api.get<{ prefix: string }>("/api/media-ticket")).prefix, at: Date.now() };
  }
  return p.startsWith("/api/files/") || p.startsWith("/api/images/") ? location.origin + ticket.prefix + p.slice(4) : null;
}

let keyCounter = 0;

function AppMusicProvider({ children }: { children: ReactNode }) {
  const saved = (() => {
    try {
      return JSON.parse(sessionStorage.getItem(SAVED) || "null") as { queue: QueueTrack[]; keys: string[] } | null;
    } catch {
      return null;
    }
  })();
  const [queue, setQueueState] = useState<QueueTrack[]>(saved?.queue ?? []);
  const [keys, setKeys] = useState<string[]>(saved?.keys ?? []);
  const [st, setSt] = useState<AppState>({ ready: false });
  const [volume, setVolumeState] = useState(1);
  const [error, setError] = useState<string | null>(null);

  const keep = (q: QueueTrack[], k: string[]) => {
    setQueueState(q);
    setKeys(k);
    try {
      sessionStorage.setItem(SAVED, JSON.stringify({ queue: q, keys: k }));
    } catch { /* not kept */ }
  };

  useEffect(() => {
    const on = (e: Event) => setSt((e as CustomEvent<AppState>).detail);
    window.addEventListener("bams:music", on);
    app<AppState>("musicState").then(setSt).catch(() => {});
    return () => window.removeEventListener("bams:music", on);
  }, []);

  // the app's queue is still ours (not stopped, not replaced by the Downloads pages' music)
  const ours = !!st.queue && st.queue.length === keys.length && st.queue.every((k, i) => k === keys[i]);
  const index = ours ? st.index ?? -1 : -1;
  const current = index >= 0 ? queue[index] ?? null : null;
  useEffect(() => { if (st.volume !== undefined) setVolumeState(st.volume); }, [st.volume]);

  const cmd = (c: string, value?: number, to?: number) =>
    app("musicCmd", { cmd: c, ...(value === undefined ? {} : { value }), ...(to === undefined ? {} : { to }) }).catch(() => {});

  const playTracks = useCallback((tracks: QueueTrack[], start = 0, shuffle = false) => {
    let list = tracks.filter((t) => t.available);
    if (!list.length) return;
    let at = Math.max(0, list.findIndex((t) => t.id === tracks[start]?.id));
    if (shuffle) {
      list = shuffled(list);
      at = 0;
    }
    const k = list.map((t) => `s${++keyCounter}:${t.id}`);
    setError(null);
    void (async () => {
      try {
        const items = await Promise.all(list.map(async (t, i) => {
          const url = await playable(t.playback.url);
          return {
            key: k[i], url, transcode: t.playback.mode === "transcode",
            // the phone can't decode it after all: the server's conversion
            fallback: t.playback.mode === "file" ? url?.replace(/\/stream$/, "/audio") ?? null : null,
            title: t.title, artist: t.artist, album: t.album, art: await playable(t.poster), start: t.start, end: t.end,
            duration: t.duration,
          };
        }));
        keep(list, k);
        await app("musicStream", { items, index: at });
      } catch (e) {
        setError((e as Error).message);
      }
    })();
  }, []);

  const playItem = useCallback(async (itemId: number, opts: { startTrackId?: number; shuffle?: boolean; rid?: number | null } = {}) => {
    const tracks = await callFor(opts.rid ?? null).get<QueueTrack[]>(`/api/items/${itemId}/tracks`);
    const start = opts.startTrackId ? Math.max(0, tracks.findIndex((t) => t.id === opts.startTrackId)) : 0;
    playTracks(tracks, start, opts.shuffle);
  }, [playTracks]);

  const move = useCallback((from: number, to: number) => {
    if (from === to || from < 0 || to < 0 || from >= queue.length || to >= queue.length) return;
    const q = [...queue], k = [...keys];
    q.splice(to, 0, ...q.splice(from, 1));
    k.splice(to, 0, ...k.splice(from, 1));
    keep(q, k);
    void cmd("move", from, to);
  }, [queue, keys]); // eslint-disable-line react-hooks/exhaustive-deps

  const remove = useCallback((i: number) => {
    if (i < 0 || i >= queue.length || i === index) return;
    keep(queue.filter((_, n) => n !== i), keys.filter((_, n) => n !== i));
    void cmd("remove", i);
  }, [queue, keys, index]); // eslint-disable-line react-hooks/exhaustive-deps

  const stop = useCallback(() => {
    keep([], []);
    void cmd("stop");
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const setVolume = useCallback((v: number) => {
    setVolumeState(v);
    void cmd("volume", v);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const duration = current?.duration ?? st.duration ?? 0;
  const value = useMemo<Music>(() => ({
    queue: current ? queue : [], index, current, playing: ours && !!st.playing, time: ours ? st.position ?? 0 : 0,
    duration, volume, error: error ?? (ours ? st.error ?? null : null),
    playTracks, playItem, move, remove, stop, setVolume,
    toggle: () => void cmd("toggle"),
    pause: () => void cmd("pause"),
    next: () => void cmd("next"),
    prev: () => void cmd("prev"),
    jump: (i: number) => void cmd("jump", i),
    seek: (t: number) => void cmd("seek", t),
  }), [queue, index, current, ours, st, duration, volume, error, playTracks, playItem, move, remove, stop, setVolume]); // eslint-disable-line react-hooks/exhaustive-deps
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
