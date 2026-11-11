import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { fmtClock } from "../format";
import { Poster } from "./Art";
import Icon from "./Icon";

// The full-screen player of phones: tapping the now-playing bar opens it. Shared by the web UI's player (also what the
// Android app shows online) and the Android app's offline pages, which hand it their own player's state.
//
// Open = `player` in the navigation state, so the phone's Back closes it (and going back to a page reopens it as it
// was left). The album and artist links leave it for their pages.

/** Whether the full-screen player is open, and how to open/close it (through the history, so Back closes it). */
export function useFullPlayer(): { open: boolean; show: () => void; hide: () => void } {
  const location = useLocation();
  const navigate = useNavigate();
  const state = (location.state ?? {}) as Record<string, unknown>;
  const open = !!state.player;
  return {
    open,
    show: () => { if (!open) navigate(location, { state: { ...state, player: true } }); },
    hide: () => { if (open) navigate(-1); },
  };
}

/** Phones: the bar opens the full-screen player instead of linking to the album. */
export function useNarrow(width = 720): boolean {
  const q = `(max-width: ${width}px)`;
  const [narrow, setNarrow] = useState(() => typeof window !== "undefined" && window.matchMedia(q).matches);
  useEffect(() => {
    const mq = window.matchMedia(q);
    const on = () => setNarrow(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [q]);
  return narrow;
}

export type FullPlayerProps = {
  poster: string | null;
  title: string;
  artist: string | null;
  album: string | null;
  albumTo: string;
  artistTo: string;
  /** "FLAC · 24-bit · 96 kHz" and the like (quality.ts) */
  quality: string | null;
  playing: boolean;
  time: number;
  duration: number;
  canNext: boolean;
  error?: string | null;
  onToggle: () => void;
  onPrev: () => void;
  onNext: () => void;
  onSeek: (t: number) => void;
  shuffle?: { on: boolean; toggle: () => void };
  /** the "add to playlist" button; none where playlists can't be reached (offline) */
  addToPlaylist?: ReactNode;
  /** the play queue, shown over the player by the queue button */
  queue: ReactNode;
  onClose: () => void;
};

export default function FullPlayer(p: FullPlayerProps) {
  const [showQueue, setShowQueue] = useState(false);
  const pct = p.duration ? Math.min(100, (p.time / p.duration) * 100) : 0;
  const left = p.duration ? Math.max(0, p.duration - p.time) : 0;

  const { onClose } = p;
  useEffect(() => {
    document.documentElement.classList.add("fp-open");  // the page under it doesn't scroll
    return () => document.documentElement.classList.remove("fp-open");
  }, []);
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") (showQueue ? setShowQueue(false) : onClose()); };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [showQueue, onClose]);
  // the queue opens at the song playing
  useEffect(() => {
    if (showQueue) document.querySelector(".fp-queue .on")?.scrollIntoView({ block: "center" });
  }, [showQueue]);

  return (
    <div className="fp" role="dialog" aria-modal="true" aria-label="Now playing">
      {p.poster && <div className="fp-glow" aria-hidden="true"><img src={p.poster} alt="" /></div>}
      <div className="fp-head">
        <button className="icon-btn" onClick={p.onClose} aria-label="Close the player"><Icon name="chevronDown" size={26} /></button>
        <span className="fp-head-label">Now playing</span>
        <span className="fp-head-pad" />
      </div>

      <div className="fp-art"><div className="fp-art-box"><Poster src={p.poster} title={p.album ?? p.title} /></div></div>

      <div className="fp-meta">
        <Link to={p.albumTo} className="fp-title">{p.title}</Link>
        {p.artist && <Link to={p.artistTo} className="fp-artist">{p.artist}</Link>}
        {p.album && <Link to={p.albumTo} className="fp-album muted">{p.album}</Link>}
        {p.quality && <span className="np-quality fp-quality">{p.quality}</span>}
      </div>

      <div className="fp-actions">
        {p.addToPlaylist}
        <button className={`icon-btn ${showQueue ? "active" : ""}`} onClick={() => setShowQueue(true)} aria-label="Play queue" title="Play queue">
          <Icon name="list" size={22} />
        </button>
      </div>

      <div className="fp-seek">
        <input type="range" className="timeline" min={0} max={p.duration || 1} step={0.5} value={Math.min(p.time, p.duration || 1)}
          style={{ ["--pct" as string]: `${pct}%` }} onChange={(e) => p.onSeek(Number(e.target.value))} aria-label="Seek" />
        <div className="fp-times"><span>{fmtClock(p.time)}</span><span>-{fmtClock(left)}</span></div>
      </div>
      {p.error && <p className="np-error fp-error">{p.error}</p>}

      <div className="fp-controls">
        {p.shuffle
          ? <button className={`icon-btn fp-side ${p.shuffle.on ? "active" : ""}`} onClick={p.shuffle.toggle} aria-label="Shuffle"><Icon name="shuffle" size={22} /></button>
          : <span className="fp-side" />}
        <button className="icon-btn fp-skip" onClick={p.onPrev} aria-label="Previous"><Icon name="skipBack" size={30} /></button>
        <button className="icon-btn fp-play" onClick={p.onToggle} aria-label={p.playing ? "Pause" : "Play"}>
          <Icon name={p.playing ? "pause" : "play"} size={34} />
        </button>
        <button className="icon-btn fp-skip" onClick={p.onNext} disabled={!p.canNext} aria-label="Next"><Icon name="skipForward" size={30} /></button>
        <span className="fp-side" />
      </div>

      {showQueue && (
        <div className="fp-queue">
          <div className="np-queue-head">
            <h3>Play queue</h3>
            <button className="icon-btn subtle" onClick={() => setShowQueue(false)} aria-label="Close the queue"><Icon name="close" size={20} /></button>
          </div>
          <div className="fp-queue-list">{p.queue}</div>
        </div>
      )}
    </div>
  );
}
