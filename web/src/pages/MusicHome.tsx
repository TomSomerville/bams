import { useState } from "react";
import type { MusicHome as Home, QueueTrack } from "../api";
import { Poster } from "../components/Art";
import { AlbumCard } from "../components/Cards";
import Icon from "../components/Icon";
import Row from "../components/Row";
import { holidayDayLabel, releasedLabel, weekLabel } from "../format";
import { useMusic } from "../music";
import { useVideoQueue } from "../random";
import { useScope } from "../servers";
import { useApi } from "../useApi";

// A music library's Home tab (owner 2026-11-18), its first: Recently Added (the latest 20 albums), Released This Week
// (albums first out this Sunday-to-Saturday week, any year), and each holiday of the coming weeks with its songs. Every
// section has a Shuffle of all its songs (GET …/music-home/<section>/random). The phone's offline Downloads build the
// same sections from their manifests (phone/pages.tsx `OfflineMusicHome`); the TV has its own (tv Music screen).

/** A section's Shuffle: every song in it, in random order, from the server. */
function Shuffle({ path, label }: { path: string; label: string }) {
  const { playRandom } = useVideoQueue();
  const { rid } = useScope();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  return (
    <button className="btn ghost small row-shuffle" disabled={busy} aria-label={`Shuffle ${label}`}
      title={failed ? "Couldn't load the songs. Try again" : `Shuffle every song in ${label}`}
      onClick={() => {
        setBusy(true);
        setFailed(false);
        playRandom(path, rid).catch(() => setFailed(true)).finally(() => setBusy(false));
      }}>
      <Icon name="shuffle" size={16} /> {failed ? "Try again" : "Shuffle"}
    </button>
  );
}

/** A song in a holiday section: its album's picture; pressing it plays the section from there. */
function SongCard({ tracks, i }: { tracks: QueueTrack[]; i: number }) {
  const music = useMusic();
  const t = tracks[i];
  const on = music.current?.id === t.id && music.current?.playback.url === t.playback.url;
  return (
    <button className={`poster-card album-card song-card ${on ? "on" : ""}`} onClick={() => (on ? music.toggle() : music.playTracks(tracks, i))}
      aria-label={`Play ${t.title}`}>
      <div className="poster-frame square">
        <Poster src={t.poster} title={t.album} />
        <div className="poster-hover"><span className="round-btn"><Icon name={on && music.playing ? "pause" : "play"} size={18} /></span></div>
      </div>
      <div className="poster-title">{t.title}</div>
      <div className="poster-sub">{t.artist}</div>
    </button>
  );
}

export default function MusicHome({ libId }: { libId: number }) {
  const { data, error } = useApi<Home>(`/api/libraries/${libId}/music-home`);
  const base = `/api/libraries/${libId}/music-home`;
  if (error) return <p className="key-msg bad">{error}</p>;
  if (!data) return null;
  if (!data.recent.length) {
    return <p className="muted">No music found in this library yet. Scans run in the background; check their status in Settings.</p>;
  }
  return (
    <div className="rows music-home">
      <Row title="Recently Added" actions={<Shuffle path={`${base}/recent/random`} label="Recently Added" />}>
        {data.recent.map((a) => <AlbumCard key={a.id} item={a} />)}
      </Row>

      <Row title="Released This Week" sub={weekLabel(data.week.start, data.week.end)}
        actions={data.week.albums.length > 0 && <Shuffle path={`${base}/week/random`} label="Released This Week" />}
        empty={!data.week.albums.length && (
          <p className="muted music-home-empty">
            No album here first came out this week, in any year. Release days come from MusicBrainz, or from the files'
            tags when an album isn't identified.
          </p>
        ) || undefined}>
        {data.week.albums.map((a) => (
          <AlbumCard key={a.id} item={a} sub={[a.parent_title, a.released && releasedLabel(a.released)].filter(Boolean).join(" · ")} />
        ))}
      </Row>

      {data.holidays.map((h) => (
        <Row key={h.id} title={`Upcoming Holiday: ${h.name}`} sub={`${holidayDayLabel(h.date)} · ${h.tracks.length} songs`}
          actions={<Shuffle path={`${base}/${h.id}/random`} label={h.name} />}>
          {h.tracks.map((t, i) => <SongCard key={`${t.id}-${i}`} tracks={h.tracks} i={i} />)}
        </Row>
      ))}
      {!data.holidays.length && (
        <p className="muted music-home-empty">
          No holiday songs for the coming weeks. Songs count when their title, their album's title or their genre tag
          names a holiday (or it's a carol everyone knows, like "Silent Night").
        </p>
      )}
    </div>
  );
}
