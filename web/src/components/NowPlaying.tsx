import { useState } from "react";
import { Link } from "react-router-dom";
import { fmtClock } from "../format";
import { useMusic } from "../music";
import { ridOf, scopeLink } from "../servers";
import { Poster } from "./Art";
import Icon from "./Icon";
import { useReorder } from "./useReorder";

/** The queue, reorderable: drag a row by its handle (mouse or touch), or focus the handle and use the arrow keys. */
function QueueList() {
  const m = useMusic();
  const { listRef, dragging, handle, rowClass } = useReorder<HTMLOListElement>(m.queue.length, m.move, ".np-queue");

  // rows keyed by track (not place), so a handle keeps focus while the arrow keys move it
  const seen = new Map<number, number>();
  const keys = m.queue.map((q) => { const n = seen.get(q.id) ?? 0; seen.set(q.id, n + 1); return `${q.id}-${n}`; });

  return (
    <ol ref={listRef} className={dragging ? "dragging" : ""}>
      {m.queue.map((q, i) => (
        <li key={keys[i]} className={rowClass(i)}>
          <button type="button" className="reorder-handle np-q-handle" aria-label={`Move ${q.title}`} {...handle(i)}>
            <Icon name="grip" size={16} />
          </button>
          <button className={`np-q-row ${i === m.index ? "on" : ""}`} onClick={() => m.jump(i)}>
            <span className="np-q-title">{q.title}</span>
            <span className="muted">{q.artist}</span>
            <span className="muted np-q-time">{fmtClock(q.duration)}</span>
          </button>
        </li>
      ))}
    </ol>
  );
}

/** The bar at the bottom of every page while music is queued. */
export default function NowPlaying() {
  const m = useMusic();
  const [showQueue, setShowQueue] = useState(false);
  const t = m.current;
  if (!t) return null;
  const pct = m.duration ? Math.min(100, (m.time / m.duration) * 100) : 0;
  const to = (p: string) => scopeLink(ridOf(t.playback.url), p);  // the track may be from another BAMS server

  return (
    <div className="now-playing" role="region" aria-label="Now playing">
      {showQueue && (
        <div className="np-queue">
          <div className="np-queue-head">
            <h3>Up next</h3>
            <button className="icon-btn subtle" onClick={() => setShowQueue(false)} aria-label="Close queue"><Icon name="close" size={18} /></button>
          </div>
          <QueueList />
        </div>
      )}

      <div className="np-track">
        <Link to={to(`/title/${t.album_id}`)} className="np-cover"><Poster src={t.poster} title={t.album} /></Link>
        <div className="np-text">
          <Link to={to(`/title/${t.album_id}`)} className="np-title">{t.title}</Link>
          <Link to={to(`/title/${t.artist_id}`)} className="np-artist muted">{t.artist}</Link>
        </div>
      </div>

      <div className="np-center">
        <div className="np-buttons">
          <button className="icon-btn" onClick={m.prev} aria-label="Previous"><Icon name="skipBack" size={20} /></button>
          <button className="icon-btn np-play" onClick={m.toggle} aria-label={m.playing ? "Pause" : "Play"}>
            <Icon name={m.playing ? "pause" : "play"} size={22} />
          </button>
          <button className="icon-btn" onClick={m.next} disabled={m.index + 1 >= m.queue.length} aria-label="Next">
            <Icon name="skipForward" size={20} />
          </button>
        </div>
        <div className="np-seek">
          <span className="time">{fmtClock(m.time)}</span>
          <input
            type="range" className="timeline" min={0} max={m.duration || 1} step={0.5} value={Math.min(m.time, m.duration || 1)}
            style={{ ["--pct" as string]: `${pct}%` }}
            onChange={(e) => m.seek(Number(e.target.value))} aria-label="Seek"
          />
          <span className="time">{fmtClock(m.duration)}</span>
        </div>
        {m.error && <span className="np-error">{m.error}</span>}
      </div>

      <div className="np-right">
        {t.playback.mode === "transcode" && (
          <span className="np-badge" title={`${t.playback.audio_codec ?? "This format"} doesn't play in browsers; the server converts it to ${t.playback.output === "flac" ? "FLAC (lossless)" : "AAC"} while streaming.`}>
            {t.playback.output === "flac" ? "FLAC" : "Converted"}
          </span>
        )}
        <Icon name="volume" size={18} />
        <input
          type="range" className="timeline np-volume" min={0} max={1} step={0.02} value={m.volume}
          style={{ ["--pct" as string]: `${m.volume * 100}%` }}
          onChange={(e) => m.setVolume(Number(e.target.value))} aria-label="Volume"
        />
        <button className={`icon-btn ${showQueue ? "active" : ""}`} onClick={() => setShowQueue(!showQueue)} aria-label="Queue">
          <Icon name="list" size={20} />
        </button>
        <button className="icon-btn" onClick={m.stop} aria-label="Stop and clear the queue"><Icon name="close" size={18} /></button>
      </div>
    </div>
  );
}
