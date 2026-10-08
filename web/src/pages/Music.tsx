import { Fragment, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { ItemDetail, ItemSummary, QueueTrack, ServerLibrary } from "../api";
import { Backdrop, Poster } from "../components/Art";
import { AlbumCard, ArtistCard } from "../components/Cards";
import Icon from "../components/Icon";
import MusicFixMatch from "../components/MusicFixMatch";
import { fmtClock, fmtLength, plural } from "../format";
import { useMusic } from "../music";
import { useApi } from "../useApi";

// ------------------------------------------------------------------ library

const ALBUM_SORTS = { artist: "Artist", title: "Title", year: "Year", added: "Recently added" } as const;
const ARTIST_SORTS = { title: "Name", added: "Recently added" } as const;

export function MusicLibrary({ lib }: { lib: ServerLibrary }) {
  const [tab, setTab] = useState<"artist" | "album">("artist");
  const [albumSort, setAlbumSort] = useState<keyof typeof ALBUM_SORTS>("artist");
  const [artistSort, setArtistSort] = useState<keyof typeof ARTIST_SORTS>("title");
  const [genre, setGenre] = useState<string | null>(null);
  const sort = tab === "album" ? albumSort : artistSort;
  const { data: items } = useApi<ItemSummary[]>(`/api/libraries/${lib.id}/items?kind=${tab}&sort=${sort}&limit=5000`);

  const genres = useMemo(() => [...new Set((items ?? []).flatMap((i) => i.genres))].sort(), [items]);
  const list = (items ?? []).filter((i) => !genre || i.genres.includes(genre));
  const sorts = tab === "album" ? ALBUM_SORTS : ARTIST_SORTS;

  return (
    <div className="page">
      <div className="page-head">
        <h1>{lib.name}</h1>
        <div className="segmented" role="tablist">
          {(["artist", "album"] as const).map((k) => (
            <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""}
              onClick={() => { setTab(k); setGenre(null); }}>
              {k === "artist" ? "Artists" : "Albums"}
            </button>
          ))}
        </div>
        {items && <span className="count">{plural(list.length, tab)}</span>}
        <label className="sort">
          Sort
          <select value={sort} onChange={(e) => (tab === "album"
            ? setAlbumSort(e.target.value as keyof typeof ALBUM_SORTS)
            : setArtistSort(e.target.value as keyof typeof ARTIST_SORTS))}>
            {Object.entries(sorts).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
      </div>
      {genres.length > 1 && (
        <div className="chips">
          <button className={`chip ${!genre ? "on" : ""}`} onClick={() => setGenre(null)}>All</button>
          {genres.map((g) => (
            <button key={g} className={`chip ${genre === g ? "on" : ""}`} onClick={() => setGenre(g)}>{g}</button>
          ))}
        </div>
      )}
      {items && !items.length && (
        <p className="muted">No music found in this library yet. Scans run in the background; check their status in Settings.</p>
      )}
      <div className="grid">
        {list.map((i) => (tab === "album" ? <AlbumCard key={i.id} item={i} /> : <ArtistCard key={i.id} item={i} />))}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ artist / album pages

function About({ item }: { item: ItemDetail }) {
  const [open, setOpen] = useState(false);
  const x = item.extra;
  const credit = x.image_credit;
  if (!item.overview && !x.musicbrainz_url) {
    return item.match_status === "unmatched" ? (
      <p className="key-msg warn">
        Not found on MusicBrainz, so this shows what the files' tags and folders say. Use Fix match if it should be there.
      </p>
    ) : null;
  }
  return (
    <>
      {item.overview && (
        <p className={`overview music-overview ${open ? "open" : ""}`} onClick={() => setOpen(!open)}
          title={open ? undefined : "Show more"}>
          {item.overview}
        </p>
      )}
      <p className="music-credits">
        {x.wikipedia?.url && (
          <a href={x.wikipedia.url} target="_blank" rel="noreferrer">Wikipedia</a>
        )}
        {x.wikipedia?.url && <span className="muted"> (text CC BY-SA)</span>}
        {x.musicbrainz_url && <a href={x.musicbrainz_url} target="_blank" rel="noreferrer">MusicBrainz</a>}
        {credit && item.kind === "artist" && (
          <span className="muted">
            Photo: {credit.author ?? "unknown"}{credit.license ? `, ${credit.license}` : ""}
            {credit.url && <>, <a href={credit.url} target="_blank" rel="noreferrer">Wikimedia Commons</a></>}
          </span>
        )}
      </p>
    </>
  );
}

function Header({ item, kicker, sub, round, children }: {
  item: ItemDetail; kicker: string; sub: ReactNode; round?: boolean; children?: ReactNode;
}) {
  return (
    <>
      <div className="detail-bg">
        <Backdrop src={null} poster={item.poster} title={item.title} className="detail-img" />
        <div className="detail-shade" />
      </div>
      <div className="detail-body music-head">
        <div className={`music-art ${round ? "round" : ""}`}><Poster src={item.poster} title={item.title} /></div>
        <div className="detail-info">
          <div className="hero-kicker">{kicker}</div>
          <h1>{item.title}</h1>
          <div className="meta">{sub}</div>
          <About item={item} />
          {children}
        </div>
      </div>
    </>
  );
}

function Actions({ item, reload }: { item: ItemDetail; reload: () => void }) {
  const music = useMusic();
  const [fixing, setFixing] = useState(false);
  return (
    <div className="actions">
      <button className="btn primary" onClick={() => music.playItem(item.id)}><Icon name="play" /> Play</button>
      <button className="btn ghost" onClick={() => music.playItem(item.id, { shuffle: true })}><Icon name="shuffle" /> Shuffle</button>
      <button className="btn ghost" onClick={() => setFixing(true)}><Icon name="edit" /> Fix match</button>
      {fixing && <MusicFixMatch item={item} onClose={(changed) => { setFixing(false); if (changed) reload(); }} />}
    </div>
  );
}

const lifeSpan = (x: ItemDetail["extra"]) => {
  const b = x.life_span?.begin?.slice(0, 4), e = x.life_span?.end?.slice(0, 4);
  if (!b) return null;
  return x.type === "Person" ? (e ? `${b}–${e}` : `born ${b}`) : (e ? `${b}–${e}` : `since ${b}`);
};

function ArtistView({ item, reload }: { item: ItemDetail; reload: () => void }) {
  const tracks = item.children.reduce((n, a) => n + (a.child_count ?? 0), 0);
  return (
    <div className="detail music-detail">
      <Header item={item} kicker={item.extra.type === "Person" ? "Artist" : item.extra.type ?? "Artist"} round
        sub={<>
          <span>{plural(item.children.length, "album")}</span>
          <span>{plural(tracks, "track")}</span>
          {lifeSpan(item.extra) && <span>{lifeSpan(item.extra)}</span>}
          {item.extra.country && <span>{item.extra.country}</span>}
          {item.genres.map((g) => <span key={g} className="tag">{g}</span>)}
        </>}>
        <Actions item={item} reload={reload} />
      </Header>
      <section className="music-section">
        <h2>Albums</h2>
        <div className="grid">{item.children.map((a) => <AlbumCard key={a.id} item={a} showArtist={false} />)}</div>
      </section>
    </div>
  );
}

function Equalizer() {
  return <span className="eq" aria-label="Playing"><i /><i /><i /></span>;
}

/** Track rows. Clicking one plays the list from there. */
export function TrackList({ tracks, albumArtist, showAlbum = false }: {
  tracks: QueueTrack[]; albumArtist?: string; showAlbum?: boolean;
}) {
  const music = useMusic();
  const discs = new Set(tracks.map((t) => t.disc_number ?? 1));
  let lastDisc: number | null = null;
  return (
    <ol className="tracklist">
      {tracks.map((t, i) => {
        const disc = t.disc_number ?? 1;
        const header = discs.size > 1 && disc !== lastDisc ? <li className="disc-head"><Icon name="disc" size={16} /> Disc {disc}</li> : null;
        lastDisc = disc;
        const isCurrent = music.current?.id === t.id;
        const performer = t.artist !== albumArtist ? t.artist : null;
        return (
          <Fragment key={t.id}>
          {header}
          <li>
            <button className={`track ${isCurrent ? "on" : ""} ${t.available ? "" : "gone"}`} disabled={!t.available}
              title={t.available ? undefined : "File not found (moved, deleted, or drive offline)"}
              onClick={() => (isCurrent ? music.toggle() : music.playTracks(tracks, i))}>
              <span className="track-num">
                {isCurrent && music.playing ? <Equalizer /> : <span className="num">{t.track_number ?? "·"}</span>}
                <span className="hover-play"><Icon name={isCurrent && music.playing ? "pause" : "play"} size={14} /></span>
              </span>
              <span className="track-text">
                <span className="track-title">{t.title}</span>
                {(performer || showAlbum) && (
                  <span className="muted track-sub">{[performer, showAlbum ? t.album : null].filter(Boolean).join(" · ")}</span>
                )}
              </span>
              {t.playback.mode === "transcode" && <span className="np-badge" title="Converted to AAC while streaming">Converted</span>}
              <span className="track-time">{fmtClock(t.duration)}</span>
            </button>
          </li>
          </Fragment>
        );
      })}
    </ol>
  );
}

function formatNote(tracks: QueueTrack[]): string | null {
  const kinds = new Set(tracks.map((t) => [t.playback.container, t.playback.audio_codec].filter(Boolean).join(" ")));
  if (!tracks.length || kinds.size === 0) return null;
  const fmt = [...kinds].filter(Boolean).join(", ") || "Unknown format";
  const converted = tracks.filter((t) => t.playback.mode === "transcode").length;
  if (!converted) return `${fmt} · plays as-is in the browser`;
  return `${fmt} · ${converted === tracks.length ? "all tracks" : plural(converted, "track")} converted to AAC while streaming (browsers can't play this format)`;
}

function AlbumView({ item, reload }: { item: ItemDetail; reload: () => void }) {
  const { data: tracks } = useApi<QueueTrack[]>(`/api/items/${item.id}/tracks`);
  const artist = item.ancestors[0];
  const note = tracks ? formatNote(tracks) : null;
  return (
    <div className="detail music-detail">
      <Header item={item} kicker={[item.extra.type ?? "Album", ...(item.extra.secondary_types ?? [])].join(" · ")}
        sub={<>
          {artist && <Link to={`/title/${artist.id}`} className="music-artist-link">{artist.title}</Link>}
          {item.year && <span>{item.year}</span>}
          <span>{plural(item.children.length, "track")}</span>
          {item.duration ? <span>{fmtLength(item.duration)}</span> : null}
          {item.genres.map((g) => <span key={g} className="tag">{g}</span>)}
        </>}>
        <Actions item={item} reload={reload} />
      </Header>
      <section className="music-section">
        {tracks ? <TrackList tracks={tracks} albumArtist={artist?.title} /> : <p className="muted">Loading tracks…</p>}
        {note && <p className="tech-note">{note}</p>}
      </section>
    </div>
  );
}

/** /title/:id for music items. A track shows its album. */
export function MusicDetail({ item, reload }: { item: ItemDetail; reload: () => void }) {
  const { data: album, reload: reloadAlbum } = useApi<ItemDetail>(
    item.kind === "track" && item.parent_id ? `/api/items/${item.parent_id}` : null);
  if (item.kind === "artist") return <ArtistView item={item} reload={reload} />;
  if (item.kind === "album") return <AlbumView item={item} reload={reload} />;
  return album ? <AlbumView item={album} reload={reloadAlbum} /> : <div className="page muted">Loading…</div>;
}
