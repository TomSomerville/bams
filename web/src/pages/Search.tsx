import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import type { ItemSummary } from "../api";
import { ItemCard } from "../components/Cards";
import Icon from "../components/Icon";
import { byTitle, keyOf, searchPaths, type Tagged } from "../everywhere";
import { fmtClock } from "../format";
import { useMusic } from "../music";
import { useEverywhere, useSources } from "../servers";

function TrackHits({ tracks }: { tracks: Tagged<ItemSummary>[] }) {
  const music = useMusic();
  return (
    <ol className="tracklist">
      {tracks.map((t) => (
        <li key={keyOf(t)}>
          <button className="track" onClick={() => music.playItem(t.id, { rid: t.rid })}>
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

/** Search every server this browser shows (everywhere.ts; the TV's Search asks the same). */
export default function Search() {
  const [params] = useSearchParams();
  const q = params.get("q") ?? "";
  const sources = useSources();
  const p = q.trim() ? searchPaths(q) : null;
  const v = useEverywhere<ItemSummary>(sources, p?.video ?? null);
  const m = useEverywhere<ItemSummary>(sources, p?.music ?? null);
  const t = useEverywhere<ItemSummary>(sources, p?.tracks ?? null);
  const video = useMemo(() => byTitle(v.lists), [v.lists]);
  const music = useMemo(() => byTitle(m.lists), [m.lists]);
  const tracks = useMemo(() => byTitle(t.lists, 50), [t.lists]);
  const done = v.done && m.done && t.done;
  const total = video.length + music.length + tracks.length;
  const artists = music.filter((i) => i.kind === "artist");
  const albums = music.filter((i) => i.kind === "album");

  return (
    <div className="page">
      <div className="page-head">
        <h1>Results for “{q}”</h1>
        {done && <span className="count">{total}</span>}
      </div>
      {done && !total && <p className="muted">Nothing in your libraries matches that.</p>}
      {video.length > 0 && (
        <section className="search-section">
          {(artists.length > 0 || albums.length > 0 || tracks.length > 0) && <h2>Shows &amp; movies</h2>}
          <div className="grid">{video.map((i) => <ItemCard key={keyOf(i)} item={i} />)}</div>
        </section>
      )}
      {artists.length > 0 && (
        <section className="search-section">
          <h2>Artists</h2>
          <div className="grid">{artists.map((i) => <ItemCard key={keyOf(i)} item={i} />)}</div>
        </section>
      )}
      {albums.length > 0 && (
        <section className="search-section">
          <h2>Albums</h2>
          <div className="grid">{albums.map((i) => <ItemCard key={keyOf(i)} item={i} />)}</div>
        </section>
      )}
      {tracks.length > 0 && (
        <section className="search-section">
          <h2>Tracks</h2>
          <TrackHits tracks={tracks} />
        </section>
      )}
    </div>
  );
}
