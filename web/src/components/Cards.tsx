import { Link } from "react-router-dom";
import type { ContinueItem, ItemSummary, PlayMethod } from "../api";
import { fmtRuntime, PLAY_LABEL, plural, subLabel, sxe } from "../format";
import { useMusic } from "../music";
import { useItemServer } from "../servers";
import { Poster } from "./Art";
import Icon from "./Icon";

/** How far through something the user is: 0..1, or null when there's nothing to show. */
export function progressOf(item: ItemSummary): number | null {
  const p = item.progress;
  if (!p || p.watched || !p.position || !p.duration) return null;
  return Math.min(1, p.position / p.duration);
}

/** Watched / unwatched markers on a poster: a tick when it's all watched, the number of unwatched episodes of a
 *  show that's been started, and a progress bar for a movie stopped part-way. */
export function WatchMarks({ item }: { item: ItemSummary }) {
  const all = item.kind === "movie" ? item.progress?.watched : !!item.episodes && item.unwatched === 0;
  const left = item.kind === "show" && item.episodes && item.unwatched && item.unwatched < item.episodes ? item.unwatched : 0;
  const pct = progressOf(item);
  return (
    <>
      {all && <span className="corner-badge watched" title="Watched"><Icon name="check" size={12} /></span>}
      {left > 0 && <span className="corner-badge count" title={`${left} unwatched episode${left === 1 ? "" : "s"}`}>{left}</span>}
      {pct !== null && <div className="progress"><div style={{ width: `${pct * 100}%` }} /></div>}
    </>
  );
}

export function PosterCard({ item }: { item: ItemSummary }) {
  const { to } = useItemServer(item);
  return (
    <Link to={to(`/title/${item.id}`)} className="poster-card">
      <div className="poster-frame">
        <Poster src={item.poster} title={item.title} />
        {item.match_status === "unmatched" && <span className="corner-badge warn" title="Not matched on TMDB">?</span>}
        <WatchMarks item={item} />
        <div className="poster-hover">
          <span className="round-btn"><Icon name="info" size={18} /></span>
        </div>
      </div>
      <div className="poster-title">{item.title}</div>
      <div className="poster-sub">{subLabel(item)}</div>
    </Link>
  );
}

/** Continue Watching: a wide still with the progress bar. The picture plays straight away; the show's name opens
 *  the show, the episode line opens its season (the show page on that season's tab). */
export function ContinueCard({ item }: { item: ContinueItem }) {
  const { to } = useItemServer(item);
  const pct = progressOf(item);
  const img = item.still || item.show?.backdrop || item.backdrop || item.show?.poster || item.poster;
  const title = item.show?.title ?? item.title;
  const left = item.progress?.duration && item.progress.position
    ? Math.max(1, Math.round((item.progress.duration - item.progress.position) / 60)) : null;
  const sub = [
    item.kind === "episode" ? `${sxe(item.season_number!, item.episode_number)} · ${item.title}` : null,
    item.reason === "next" ? "Next episode" : left ? `${fmtRuntime(left)} left` : null,
  ].filter(Boolean).join(" · ");
  const page = to(item.show ? `/title/${item.show.id}` : `/title/${item.id}`);
  const seasonPage = item.season_id ? `${page}?season=${item.season_id}` : page;
  return (
    <div className="continue-card">
      <Link to={to(`/play/${item.id}`)} className="continue-frame" aria-label={`Play ${title}${item.show ? ` ${item.title}` : ""}`}>
        {img ? <img className="continue-img" src={img} alt="" loading="lazy" /> : <Poster src={null} title={title} />}
        <div className="continue-play"><span className="round-btn"><Icon name="play" size={18} /></span></div>
        {pct !== null && <div className="progress"><div style={{ width: `${pct * 100}%` }} /></div>}
      </Link>
      <Link to={page} className="poster-title">{title}</Link>
      <Link to={seasonPage} className="poster-sub">{sub}</Link>
    </div>
  );
}

/** Square album cover; the play button on hover starts the album without opening it. */
export function AlbumCard({ item, showArtist = true }: { item: ItemSummary; showArtist?: boolean }) {
  const music = useMusic();
  const { to, rid } = useItemServer(item);
  return (
    <Link to={to(`/title/${item.id}`)} className="poster-card album-card">
      <div className="poster-frame square">
        <Poster src={item.poster} title={item.title} />
        <div className="poster-hover">
          <button className="round-btn" aria-label={`Play ${item.title}`}
            onClick={(e) => { e.preventDefault(); music.playItem(item.id, { rid }); }}>
            <Icon name="play" size={18} />
          </button>
        </div>
      </div>
      <div className="poster-title">{item.title}</div>
      <div className="poster-sub">{[showArtist ? item.parent_title : null, item.year].filter(Boolean).join(" · ")}</div>
    </Link>
  );
}

export function ArtistCard({ item }: { item: ItemSummary }) {
  const { to } = useItemServer(item);
  return (
    <Link to={to(`/title/${item.id}`)} className="poster-card artist-card">
      <div className="poster-frame round"><Poster src={item.poster} title={item.title} /></div>
      <div className="poster-title">{item.title}</div>
      <div className="poster-sub">{plural(item.child_count ?? 0, "album")}</div>
    </Link>
  );
}

/** Any item in a grid or row: the right card for its kind. */
export function ItemCard({ item }: { item: ItemSummary }) {
  if (item.kind === "album") return <AlbumCard item={item} />;
  if (item.kind === "artist") return <ArtistCard item={item} />;
  return <PosterCard item={item} />;
}

export function PlayBadge({ method }: { method: PlayMethod }) {
  const cls = method === "direct_play" ? "ok" : method === "direct_stream" ? "mid" : "hot";
  return <span className={`play-badge ${cls}`} title="How BAMS would play this in a browser">{PLAY_LABEL[method]}</span>;
}
