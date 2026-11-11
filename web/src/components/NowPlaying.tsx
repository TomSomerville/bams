import { useState } from "react";
import { Link } from "react-router-dom";
import { fmtClock } from "../format";
import { useMusic } from "../music";
import { ridOf, scopeLink, ScopeFor } from "../servers";
import { Poster } from "./Art";
import FullPlayer, { useFullPlayer, useNarrow } from "./FullPlayer";
import Icon from "./Icon";
import { AddToPlaylist } from "./Playlists";
import { useReorder } from "./useReorder";
import { qualityLine } from "../quality";
import type { QueueTrack } from "../api";

/** The queue, reorderable: drag a row by its handle (mouse or touch), or focus the handle and use the arrow keys. */
function QueueList({ scroller = ".np-queue" }: { scroller?: string }) {
  const m = useMusic();
  const { listRef, dragging, handle, rowClass } = useReorder<HTMLOListElement>(m.queue.length, m.move, scroller);

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
          {i !== m.index && (
            <button type="button" className="icon-btn subtle np-q-remove" onClick={() => m.remove(i)}
              aria-label={`Remove ${q.title}`} title="Remove from the queue"><Icon name="close" size={14} /></button>
          )}
        </li>
      ))}
    </ol>
  );
}

/** The playing song's format and quality, under its title and artist (quality.ts). */
function Quality({ t }: { t: QueueTrack }) {
  const line = qualityLine(t.playback);
  return line ? <span className="np-quality" title={line}>{line}</span> : null;
}

/** The bar at the bottom of every page while music is queued. */
export default function NowPlaying() {
  const m = useMusic();
  const [showQueue, setShowQueue] = useState(false);
  const full = useFullPlayer();
  const narrow = useNarrow();
  const t = m.current;
  if (!t) return null;
  const pct = m.duration ? Math.min(100, (m.time / m.duration) * 100) : 0;
  const rid = ridOf(t.playback.url);
  const to = (p: string) => scopeLink(rid, p);  // the track may be from another BAMS server

  if (full.open) {
    return (
      <FullPlayer
        poster={t.poster} title={t.title} artist={t.artist} album={t.album}
        albumTo={to(`/title/${t.album_id}`)} artistTo={to(`/title/${t.artist_id}`)} quality={qualityLine(t.playback)}
        playing={m.playing} time={m.time} duration={m.duration} canNext={m.index + 1 < m.queue.length} error={m.error}
        onToggle={m.toggle} onPrev={m.prev} onNext={m.next} onSeek={m.seek} onClose={full.hide}
        addToPlaylist={<ScopeFor rid={rid}><AddToPlaylist small items={[t.id]} title={t.title} /></ScopeFor>}
        queue={<QueueList scroller=".fp-queue-list" />}
      />
    );
  }

  return (
    // phones: the bar (but its buttons) opens the full-screen player
    <div className={`now-playing ${narrow ? "np-tap" : ""}`} role="region" aria-label="Now playing"
      onClick={narrow ? (e) => { if (!(e.target as HTMLElement).closest("button, a, input")) full.show(); } : undefined}>
      {showQueue && (
        <div className="np-queue">
          <div className="np-queue-head">
            <h3>Up next</h3>
            <button className="icon-btn subtle" onClick={() => setShowQueue(false)} aria-label="Close queue"><Icon name="close" size={18} /></button>
          </div>
          <QueueList />
        </div>
      )}

      {narrow ? (
        <div className="np-track">
          <span className="np-cover"><Poster src={t.poster} title={t.album} /></span>
          <div className="np-text">
            <span className="np-title">{t.title}</span>
            <span className="np-artist muted">{t.artist}</span>
            <Quality t={t} />
          </div>
        </div>
      ) : (
        <div className="np-track">
          <Link to={to(`/title/${t.album_id}`)} className="np-cover"><Poster src={t.poster} title={t.album} /></Link>
          <div className="np-text">
            <Link to={to(`/title/${t.album_id}`)} className="np-title">{t.title}</Link>
            <Link to={to(`/title/${t.artist_id}`)} className="np-artist muted">{t.artist}</Link>
            <Quality t={t} />
          </div>
        </div>
      )}

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
