import { Link } from "react-router-dom";
import type { ContinueEntry, Item } from "../data";
import { playMethod, seasonsLabel, sxe } from "../data";
import { Backdrop, Poster } from "./Art";
import Icon from "./Icon";

export function PosterCard({ item }: { item: Item }) {
  return (
    <Link to={`/title/${item.id}`} className="poster-card">
      <div className="poster-frame">
        <Poster item={item} />
        {item.media.resolution === "4K" && <span className="corner-badge">4K</span>}
        <div className="poster-hover">
          <span className="round-btn"><Icon name="play" size={18} /></span>
        </div>
      </div>
      <div className="poster-title">{item.title}</div>
      <div className="poster-sub">
        {item.year} · {item.type === "show" ? seasonsLabel(item) : item.rating}
      </div>
    </Link>
  );
}

export function ContinueCard({ entry }: { entry: ContinueEntry }) {
  const { item, progress, season, episode } = entry;
  return (
    <Link to={`/play/${item.id}`} className="continue-card">
      <div className="continue-frame">
        <Backdrop item={item} className="continue-img" />
        <div className="continue-play"><span className="round-btn"><Icon name="play" size={18} /></span></div>
        <div className="progress"><div style={{ width: `${progress * 100}%` }} /></div>
      </div>
      <div className="poster-title">{item.title}</div>
      <div className="poster-sub">
        {season ? `${sxe(season, episode!)} · ` : ""}{Math.round((1 - progress) * (item.runtime ?? 50))} min left
      </div>
    </Link>
  );
}

export function PlayBadge({ item }: { item: Item }) {
  const m = playMethod(item.media);
  const cls = m === "Direct Play" ? "ok" : m === "Direct Stream" ? "mid" : "hot";
  return <span className={`play-badge ${cls}`} title="How BAMS would play this in a browser">{m}</span>;
}
