import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { byId, playMethod, sxe } from "../data";
import { Backdrop } from "../components/Art";
import Icon from "../components/Icon";

// Mock player: no media is served yet, so this simulates the timeline over the backdrop.
// Phase 1 swaps the backdrop for <video> fed by hls.js.
export default function Player() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const item = byId(id ?? "");
  const total = (item?.runtime ?? 48) * 60;
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [idle, setIdle] = useState(false);
  const idleTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!playing) return;
    const tick = setInterval(() => setT((x) => Math.min(total, x + 1)), 1000);
    return () => clearInterval(tick);
  }, [playing, total]);

  useEffect(() => {
    const wake = () => {
      setIdle(false);
      clearTimeout(idleTimer.current);
      idleTimer.current = window.setTimeout(() => setIdle(true), 3000);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === " ") { e.preventDefault(); setPlaying((p) => !p); }
      if (e.key === "Escape") nav(-1);
      if (e.key === "ArrowRight") setT((x) => Math.min(total, x + 10));
      if (e.key === "ArrowLeft") setT((x) => Math.max(0, x - 10));
      wake();
    };
    wake();
    window.addEventListener("mousemove", wake);
    window.addEventListener("keydown", key);
    return () => { window.removeEventListener("mousemove", wake); window.removeEventListener("keydown", key); };
  }, [nav, total]);

  if (!item) return null;
  const s = Number(params.get("s") ?? 0), e = Number(params.get("e") ?? 0);
  const fmt = (sec: number) => {
    const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), ss = Math.floor(sec % 60);
    return `${h ? `${h}:` : ""}${String(m).padStart(h ? 2 : 1, "0")}:${String(ss).padStart(2, "0")}`;
  };
  const method = playMethod(item.media);

  return (
    <div className={`player ${idle && playing ? "idle" : ""}`} onClick={() => setPlaying((p) => !p)}>
      <Backdrop item={item} className="player-img" />
      {!playing && <div className="player-center"><span className="round-btn big"><Icon name="play" size={40} /></span></div>}

      <div className="player-top" onClick={(ev) => ev.stopPropagation()}>
        <button className="icon-btn" onClick={() => nav(-1)} aria-label="Back"><Icon name="back" size={28} /></button>
        <div>
          <div className="player-title">{item.title}</div>
          {s > 0 && <div className="muted">{sxe(s, e)}</div>}
        </div>
        <div className="player-stream">
          {method === "Transcode" ? `Transcoding ${item.media.video} → H.264 (NVENC)` : method} · {item.media.resolution}
        </div>
      </div>

      <div className="player-bottom" onClick={(ev) => ev.stopPropagation()}>
        <input
          className="timeline"
          type="range" min={0} max={total} value={t}
          onChange={(ev) => setT(Number(ev.target.value))}
          style={{ ["--pct" as string]: `${(t / total) * 100}%` }}
          aria-label="Seek"
        />
        <div className="player-controls">
          <button className="icon-btn" onClick={() => setPlaying(!playing)} aria-label={playing ? "Pause" : "Play"}>
            <Icon name={playing ? "pause" : "play"} size={28} />
          </button>
          <button className="icon-btn" aria-label="Volume"><Icon name="volume" size={24} /></button>
          <span className="time">{fmt(t)} / {fmt(total)}</span>
          <span className="spacer" />
          <button className="icon-btn" title="Subtitles"><Icon name="subtitles" size={24} /></button>
          <button className="icon-btn" title="Settings: quality, audio track"><Icon name="settings" size={24} /></button>
          <button className="icon-btn" title="Fullscreen" onClick={() => document.documentElement.requestFullscreen?.()}>
            <Icon name="fullscreen" size={24} />
          </button>
        </div>
      </div>
    </div>
  );
}
