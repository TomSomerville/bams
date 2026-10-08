import { useState } from "react";
import { Link } from "react-router-dom";
import { fmtClock } from "../format";
import { useMusic } from "../music";
import { Poster } from "./Art";
import Icon from "./Icon";

/** The bar at the bottom of every page while music is queued. */
export default function NowPlaying() {
  const m = useMusic();
  const [showQueue, setShowQueue] = useState(false);
  const t = m.current;
  if (!t) return null;
  const pct = m.duration ? Math.min(100, (m.time / m.duration) * 100) : 0;

  return (
    <div className="now-playing" role="region" aria-label="Now playing">
      {showQueue && (
        <div className="np-queue">
          <div className="np-queue-head">
            <h3>Up next</h3>
            <button className="icon-btn subtle" onClick={() => setShowQueue(false)} aria-label="Close queue"><Icon name="close" size={18} /></button>
          </div>
          <ol>
            {m.queue.map((q, i) => (
              <li key={`${i}-${q.id}`}>
                <button className={i === m.index ? "on" : ""} onClick={() => m.jump(i)}>
                  <span className="np-q-title">{q.title}</span>
                  <span className="muted">{q.artist}</span>
                  <span className="muted np-q-time">{fmtClock(q.duration)}</span>
                </button>
              </li>
            ))}
          </ol>
        </div>
      )}

      <div className="np-track">
        <Link to={`/title/${t.album_id}`} className="np-cover"><Poster src={t.poster} title={t.album} /></Link>
        <div className="np-text">
          <Link to={`/title/${t.album_id}`} className="np-title">{t.title}</Link>
          <Link to={`/title/${t.artist_id}`} className="np-artist muted">{t.artist}</Link>
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
          <span className="np-badge" title={`${t.playback.audio_codec ?? "This format"} doesn't play in browsers; the server converts it to AAC while streaming.`}>
            Converted
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
