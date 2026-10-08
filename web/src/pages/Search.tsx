import { useSearchParams } from "react-router-dom";
import type { ItemSummary } from "../api";
import { ItemCard } from "../components/Cards";
import Icon from "../components/Icon";
import { fmtClock } from "../format";
import { useMusic } from "../music";
import { useApi } from "../useApi";

function TrackHits({ tracks }: { tracks: ItemSummary[] }) {
  const music = useMusic();
  return (
    <ol className="tracklist">
      {tracks.map((t) => (
        <li key={t.id}>
          <button className={`track ${music.current?.id === t.id ? "on" : ""}`} onClick={() => music.playItem(t.id)}>
            <span className="track-num"><Icon name="play" size={14} /></span>
            <span className="track-text">
              <span className="track-title">{t.title}</span>
              <span className="muted track-sub">{[t.artist, t.parent_title].filter(Boolean).join(" · ")}</span>
            </span>
            <span className="track-time">{fmtClock(t.duration)}</span>
          </button>
        </li>
      ))}
    </ol>
  );
}

export default function Search() {
  const [params] = useSearchParams();
  const q = params.get("q") ?? "";
  const enc = encodeURIComponent(q);
  const { data: video } = useApi<ItemSummary[]>(q ? `/api/items?sort=title&q=${enc}` : null);
  const { data: music } = useApi<ItemSummary[]>(q ? `/api/items?kind=artist,album&sort=title&q=${enc}` : null);
  const { data: tracks } = useApi<ItemSummary[]>(q ? `/api/items?kind=track&sort=title&q=${enc}&limit=50` : null);
  const done = video && music && tracks;
  const total = (video?.length ?? 0) + (music?.length ?? 0) + (tracks?.length ?? 0);
  const artists = music?.filter((i) => i.kind === "artist") ?? [];
  const albums = music?.filter((i) => i.kind === "album") ?? [];

  return (
    <div className="page">
      <div className="page-head">
        <h1>Results for “{q}”</h1>
        {done && <span className="count">{total}</span>}
      </div>
      {done && !total && <p className="muted">Nothing in your libraries matches that.</p>}
      {!!video?.length && (
        <section className="search-section">
          {(artists.length > 0 || albums.length > 0 || !!tracks?.length) && <h2>Shows &amp; movies</h2>}
          <div className="grid">{video.map((i) => <ItemCard key={i.id} item={i} />)}</div>
        </section>
      )}
      {artists.length > 0 && (
        <section className="search-section">
          <h2>Artists</h2>
          <div className="grid">{artists.map((i) => <ItemCard key={i.id} item={i} />)}</div>
        </section>
      )}
      {albums.length > 0 && (
        <section className="search-section">
          <h2>Albums</h2>
          <div className="grid">{albums.map((i) => <ItemCard key={i.id} item={i} />)}</div>
        </section>
      )}
      {!!tracks?.length && (
        <section className="search-section">
          <h2>Tracks</h2>
          <TrackHits tracks={tracks} />
        </section>
      )}
    </div>
  );
}
