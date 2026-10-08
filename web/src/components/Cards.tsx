import { Link } from "react-router-dom";
import type { ItemSummary, PlayMethod } from "../api";
import { PLAY_LABEL, plural, subLabel } from "../format";
import { useMusic } from "../music";
import { Poster } from "./Art";
import Icon from "./Icon";

export function PosterCard({ item }: { item: ItemSummary }) {
  return (
    <Link to={`/title/${item.id}`} className="poster-card">
      <div className="poster-frame">
        <Poster src={item.poster} title={item.title} />
        {item.match_status === "unmatched" && <span className="corner-badge warn" title="Not matched on TMDB">?</span>}
        <div className="poster-hover">
          <span className="round-btn"><Icon name="info" size={18} /></span>
        </div>
      </div>
      <div className="poster-title">{item.title}</div>
      <div className="poster-sub">{subLabel(item)}</div>
    </Link>
  );
}

/** Square album cover; the play button on hover starts the album without opening it. */
export function AlbumCard({ item, showArtist = true }: { item: ItemSummary; showArtist?: boolean }) {
  const music = useMusic();
  return (
    <Link to={`/title/${item.id}`} className="poster-card album-card">
      <div className="poster-frame square">
        <Poster src={item.poster} title={item.title} />
        <div className="poster-hover">
          <button className="round-btn" aria-label={`Play ${item.title}`}
            onClick={(e) => { e.preventDefault(); music.playItem(item.id); }}>
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
  return (
    <Link to={`/title/${item.id}`} className="poster-card artist-card">
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
