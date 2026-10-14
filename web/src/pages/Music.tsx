import { Fragment, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import type {
  ItemDetail, ItemSummary, Playlist, PlaylistSummary, QueueTrack, ServerLibrary, UserPlaylist, UserPlaylistSummary,
} from "../api";
import { Backdrop, Poster } from "../components/Art";
import { AlbumCard, ArtistCard } from "../components/Cards";
import Icon from "../components/Icon";
import MusicFixMatch from "../components/MusicFixMatch";
import { fmtClock, fmtLength, plural } from "../format";
import { useScope } from "../servers";
import { useMusic } from "../music";
import { PlayRandomButton } from "../random";
import { DownloadButton } from "../components/Download";
import { AddToPlaylist, EditPlaylistDialog, NewPlaylistDialog } from "../components/Playlists";
import { useReorder } from "../components/useReorder";
import { useApi } from "../useApi";

// ------------------------------------------------------------------ library

const ALBUM_SORTS = { artist: "Artist", title: "Title", year: "Year", added: "Recently added" } as const;
const ARTIST_SORTS = { title: "Name", added: "Recently added" } as const;

const TABS = { artist: "Artists", album: "Albums", playlist: "Playlists" } as const;

export function MusicLibrary({ lib }: { lib: ServerLibrary }) {
  const { libName } = useScope();
  const [tab, setTab] = useState<keyof typeof TABS>("artist");
  const [albumSort, setAlbumSort] = useState<keyof typeof ALBUM_SORTS>("artist");
  const [artistSort, setArtistSort] = useState<keyof typeof ARTIST_SORTS>("title");
  const [genre, setGenre] = useState<string | null>(null);
  const sort = tab === "album" ? albumSort : artistSort;
  const { data: items } = useApi<ItemSummary[]>(
    tab === "playlist" ? null : `/api/libraries/${lib.id}/items?kind=${tab}&sort=${sort}&limit=5000`);
  const { data: lists } = useApi<PlaylistSummary[]>(tab === "playlist" ? `/api/libraries/${lib.id}/playlists` : null);
  const { data: mine } = useApi<UserPlaylistSummary[]>(tab === "playlist" ? "/api/user-playlists" : null);
  const [making, setMaking] = useState(false);
  const nav = useNavigate();
  const { to } = useScope();

  const genres = useMemo(() => [...new Set((items ?? []).flatMap((i) => i.genres))].sort(), [items]);
  const list = (items ?? []).filter((i) => !genre || i.genres.includes(genre));
  const sorts = tab === "album" ? ALBUM_SORTS : ARTIST_SORTS;

  return (
    <div className="page">
      <div className="page-head">
        <h1>{libName(lib.id, lib.name)}</h1>
        <div className="segmented" role="tablist">
          {(Object.keys(TABS) as (keyof typeof TABS)[]).map((k) => (
            <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""}
              onClick={() => { setTab(k); setGenre(null); }}>
              {TABS[k]}
            </button>
          ))}
        </div>
        {tab === "playlist" ? (lists && mine && <span className="count">{plural(lists.length + mine.length, "playlist")}</span>)
          : items && <span className="count">{plural(list.length, tab)}</span>}
        <PlayRandomButton className="btn ghost small page-random" path={`/api/libraries/${lib.id}/random`} />
        {tab !== "playlist" && <label className="sort">
          Sort
          <select value={sort} onChange={(e) => (tab === "album"
            ? setAlbumSort(e.target.value as keyof typeof ALBUM_SORTS)
            : setArtistSort(e.target.value as keyof typeof ARTIST_SORTS))}>
            {Object.entries(sorts).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>}
      </div>
      {tab === "playlist" && (
        <>
          <div className="section-head playlists-head">
            <h2 className="section-title">Your playlists</h2>
            <button className="btn primary small" onClick={() => setMaking(true)}><Icon name="plus" size={16} /> New playlist</button>
          </div>
          {mine && !mine.length && (
            <p className="muted">None yet. Make one here, or press <Icon name="listPlus" size={14} /> on a song, an album or an
              artist to add it to a playlist. Your playlists are yours alone: other accounts don't see them.</p>
          )}
          <div className="grid">{mine?.map((p) => <PlaylistCard key={`u${p.id}`} p={p} />)}</div>
          <div className="section-head playlists-head"><h2 className="section-title">From playlist files</h2></div>
          {lists && !lists.length && (
            <p className="muted">
              None. BAMS imports playlist files (.m3u, .m3u8, .pls) it finds in this library's folders, and keeps them in
              step with those files on every scan.
            </p>
          )}
          <div className="grid">{lists?.map((p) => <PlaylistCard key={p.id} p={p} />)}</div>
          {making && <NewPlaylistDialog onClose={() => setMaking(false)} created={(p) => nav(to(`/my-playlist/${p.id}`))} />}
        </>
      )}
      {tab !== "playlist" && genres.length > 1 && (
        <div className="chips">
          <button className={`chip ${!genre ? "on" : ""}`} onClick={() => setGenre(null)}>All</button>
          {genres.map((g) => (
            <button key={g} className={`chip ${genre === g ? "on" : ""}`} onClick={() => setGenre(g)}>{g}</button>
          ))}
        </div>
      )}
      {tab !== "playlist" && items && !items.length && (
        <p className="muted">No music found in this library yet. Scans run in the background; check their status in Settings.</p>
      )}
      {tab !== "playlist" && <div className="grid">
        {list.map((i) => (tab === "album" ? <AlbumCard key={i.id} item={i} /> : <ArtistCard key={i.id} item={i} />))}
      </div>}
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
  const { rid, remote } = useScope();
  const [fixing, setFixing] = useState(false);
  return (
    <div className="actions">
      <button className="btn primary" onClick={() => music.playItem(item.id, { rid })}><Icon name="play" /> Play</button>
      <button className="btn ghost" onClick={() => music.playItem(item.id, { shuffle: true, rid })}><Icon name="shuffle" /> Shuffle</button>
      {(!remote || remote.is_admin) && <button className="btn ghost" onClick={() => setFixing(true)}><Icon name="edit" /> Fix match</button>}
      {item.kind === "artist" && <PlayRandomButton path={`/api/items/${item.id}/random`} />}
      <AddToPlaylist items={[item.id]} title={item.title} />
      <DownloadButton id={item.id} title={item.title} what={item.kind === "artist" ? " artist" : " album"} />
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

/** Track rows. Clicking one plays the list from there. `edit`: one of your playlists, whose rows can be dragged
 *  into another order (by their handle) and taken out. */
export function TrackList({ tracks, albumArtist, showAlbum = false, numbered = false, edit }: {
  /** numbered: number rows by their place in the list (a playlist), not by their track number */
  tracks: QueueTrack[]; albumArtist?: string; showAlbum?: boolean; numbered?: boolean;
  edit?: { move: (from: number, to: number) => void; remove: (i: number) => void };
}) {
  const music = useMusic();
  const { listRef, dragging, handle, rowClass } = useReorder<HTMLOListElement>(tracks.length, edit?.move ?? (() => {}));
  const discs = new Set(tracks.map((t) => t.disc_number ?? 1));
  let lastDisc: number | null = null;
  return (
    <ol className={`tracklist ${dragging ? "dragging" : ""}`} ref={edit ? listRef : undefined}>
      {tracks.map((t, i) => {
        const disc = t.disc_number ?? 1;
        const header = !numbered && discs.size > 1 && disc !== lastDisc ? <li className="disc-head"><Icon name="disc" size={16} /> Disc {disc}</li> : null;
        lastDisc = disc;
        const isCurrent = music.current?.id === t.id;
        const performer = t.artist !== albumArtist ? t.artist : null;
        return (
          <Fragment key={`${t.id}-${i}`}>
          {header}
          <li className={`track-row ${edit ? rowClass(i) : ""}`}>
            {edit && (
              <button type="button" className="reorder-handle track-handle" aria-label={`Move ${t.title}`} {...handle(i)}>
                <Icon name="grip" size={16} />
              </button>
            )}
            <button className={`track ${isCurrent ? "on" : ""} ${t.available ? "" : "gone"}`} disabled={!t.available}
              title={t.available ? undefined : "File not found (moved, deleted, or drive offline)"}
              onClick={() => (isCurrent ? music.toggle() : music.playTracks(tracks, i))}>
              <span className="track-num">
                {isCurrent && music.playing ? <Equalizer /> : <span className="num">{numbered ? i + 1 : t.track_number ?? "·"}</span>}
                <span className="hover-play"><Icon name={isCurrent && music.playing ? "pause" : "play"} size={14} /></span>
              </span>
              <span className="track-text">
                <span className="track-title">{t.title}</span>
                {(performer || showAlbum) && (
                  <span className="muted track-sub">{[performer, showAlbum ? t.album : null].filter(Boolean).join(" · ")}</span>
                )}
              </span>
              {t.playback.mode === "transcode" && (
                <span className="np-badge" title={`Converted to ${t.playback.output === "flac" ? "FLAC" : "AAC"} while streaming`}>Converted</span>
              )}
              <span className="track-time">{fmtClock(t.duration)}</span>
            </button>
            {!edit && <AddToPlaylist small items={[t.id]} title={t.title} />}
            {t.available && <DownloadButton small id={t.id} title={t.title} audio={[t.playback.audio_codec]} />}
            {edit && (
              <button type="button" className="icon-btn subtle" onClick={() => edit.remove(i)} title="Take out of this playlist"
                aria-label={`Take ${t.title} out of this playlist`}><Icon name="close" size={16} /></button>
            )}
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
  const converted = tracks.filter((t) => t.playback.mode === "transcode");
  const cue = tracks.some((t) => t.start != null) ? " · one file split by its cue sheet" : "";
  if (!converted.length) return `${fmt}${cue} · plays as-is in the browser`;
  const to = converted[0].playback.output === "flac" ? "FLAC (lossless)" : "AAC";
  return `${fmt}${cue} · ${converted.length === tracks.length ? "all tracks" : plural(converted.length, "track")} converted to ${to} while streaming (browsers can't play this format)`;
}

function AlbumView({ item, reload }: { item: ItemDetail; reload: () => void }) {
  const { to } = useScope();
  const { data: tracks } = useApi<QueueTrack[]>(`/api/items/${item.id}/tracks`);
  const artist = item.ancestors[0];
  const note = tracks ? formatNote(tracks) : null;
  return (
    <div className="detail music-detail">
      <Header item={item} kicker={[item.extra.type ?? "Album", ...(item.extra.secondary_types ?? [])].join(" · ")}
        sub={<>
          {artist && <Link to={to(`/title/${artist.id}`)} className="music-artist-link">{artist.title}</Link>}
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

// ------------------------------------------------------------------ playlists

/** Up to four album covers in a square, or a note icon when the playlist has none. */
function Mosaic({ covers, name }: { covers: string[]; name: string }) {
  if (covers.length < 4) return <Poster src={covers[0] ?? null} title={name} />;
  return <div className="mosaic">{covers.map((c) => <img key={c} src={c} alt="" loading="lazy" />)}</div>;
}

/** A playlist's card: an imported one or one of yours (`user`). */
function PlaylistCard({ p }: { p: PlaylistSummary | UserPlaylistSummary }) {
  const music = useMusic();
  const { call, to } = useScope();
  const own = "user" in p;
  const play = async (e: React.MouseEvent) => {
    e.preventDefault();
    const pl = await call.get<Playlist>(own ? `/api/user-playlists/${p.id}` : `/api/playlists/${p.id}`);
    music.playTracks(pl.tracks);
  };
  return (
    <Link to={to(own ? `/my-playlist/${p.id}` : `/playlist/${p.id}`)} className="poster-card album-card">
      <div className="poster-frame square">
        <Mosaic covers={p.covers} name={p.name} />
        {p.track_count > 0 && (
          <div className="poster-hover">
            <button className="round-btn" aria-label={`Play ${p.name}`} onClick={play}><Icon name="play" size={18} /></button>
          </div>
        )}
      </div>
      <div className="poster-title">{p.name}</div>
      <div className="poster-sub">{plural(p.track_count, "track")}</div>
    </Link>
  );
}

/** /playlist/:id: an imported playlist, in its own order. */
export function PlaylistPage() {
  const { id } = useParams();
  const music = useMusic();
  const { to, libName } = useScope();
  const { data: p, error } = useApi<Playlist>(`/api/playlists/${id}`);
  if (error) return <div className="page"><h1>Playlist not found</h1><p className="muted">{error}</p></div>;
  if (!p) return <div className="page muted">Loading…</div>;
  return (
    <div className="detail music-detail">
      <div className="detail-body music-head">
        <div className="music-art"><Mosaic covers={p.covers} name={p.name} /></div>
        <div className="detail-info">
          <div className="hero-kicker">Playlist</div>
          <h1>{p.name}</h1>
          <div className="meta">
            <Link to={to(`/library/${p.library_id}`)} className="music-artist-link">{libName(p.library_id, p.library_name)}</Link>
            <span>{plural(p.track_count, "track")}</span>
            {p.duration ? <span>{fmtLength(p.duration)}</span> : null}
          </div>
          <p className="music-credits muted">
            <span>Imported from <code>{p.path}</code> (kept in step with it on every scan)</span>
            {p.missing > 0 && <span>{p.missing} {p.missing === 1 ? "entry isn't" : "entries aren't"} in this library (streams or files elsewhere)</span>}
          </p>
          {p.tracks.length > 0 && (
            <div className="actions">
              <button className="btn primary" onClick={() => music.playTracks(p.tracks)}><Icon name="play" /> Play</button>
              <button className="btn ghost" onClick={() => music.playTracks(p.tracks, 0, true)}><Icon name="shuffle" /> Shuffle</button>
              <MakeCopy p={p} />
              <DownloadButton kind="playlist" id={p.id} title={p.name} what=" playlist" />
            </div>
          )}
        </div>
      </div>
      <section className="music-section">
        {p.tracks.length ? <TrackList tracks={p.tracks} showAlbum numbered /> : <p className="muted">None of its entries are in this library.</p>}
      </section>
    </div>
  );
}

/** An imported playlist as one of yours, to change (its file can't be: media folders are read-only to BAMS). */
function MakeCopy({ p }: { p: Playlist }) {
  const { call, to } = useScope();
  const nav = useNavigate();
  const [err, setErr] = useState<string | null>(null);
  const copy = () => call.post<UserPlaylistSummary>("/api/user-playlists", { name: p.name, copy_of: p.id })
    .then((c) => nav(to(`/my-playlist/${c.id}`))).catch((e) => setErr(e.message));
  return (
    <>
      <button className="btn ghost" onClick={copy} title="Make a playlist of your own from it, to change"><Icon name="plus" /> Make a copy</button>
      {err && <p className="key-msg bad">{err}</p>}
    </>
  );
}

/** /my-playlist/:id: one of your playlists. Drag rows to reorder, take songs out, rename, delete. */
export function UserPlaylistPage() {
  const { id } = useParams();
  const music = useMusic();
  const nav = useNavigate();
  const { call, to } = useScope();
  const { data, error, reload } = useApi<UserPlaylist>(`/api/user-playlists/${id}`);
  const [p, setP] = useState<UserPlaylist | null>(null);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => setP(data), [data]);
  if (error) return <div className="page"><h1>Playlist not found</h1><p className="muted">{error}</p></div>;
  if (!p) return <div className="page muted">Loading…</div>;

  const save = (tracks: QueueTrack[]) => {
    setP({ ...p, tracks, track_count: tracks.length });  // at once; the server's answer follows
    call.put<UserPlaylist>(`/api/user-playlists/${p.id}/tracks`, { tracks: tracks.map((t) => t.id) })
      .then(setP).catch((e) => { setErr(e.message); reload(); });
  };
  const move = (from: number, toIdx: number) => {
    const next = [...p.tracks];
    next.splice(toIdx, 0, ...next.splice(from, 1));
    save(next);
  };
  const remove = (i: number) => save(p.tracks.filter((_, k) => k !== i));
  // deleted: back where it was opened from (a library's Playlists tab), or Home
  const del = () => call.del(`/api/user-playlists/${p.id}`)
    .then(() => (window.history.length > 1 ? nav(-1) : nav(to("/"), { replace: true }))).catch((e) => setErr(e.message));

  return (
    <div className="detail music-detail">
      <div className="detail-body music-head">
        <div className="music-art"><Mosaic covers={p.covers} name={p.name} /></div>
        <div className="detail-info">
          <div className="hero-kicker">Your playlist</div>
          <h1>{p.name}</h1>
          <div className="meta">
            <span>{plural(p.track_count, "track")}</span>
            {p.duration ? <span>{fmtLength(p.duration)}</span> : null}
          </div>
          {p.description && <p className="overview">{p.description}</p>}
          <div className="actions">
            {p.tracks.length > 0 && <>
              <button className="btn primary" onClick={() => music.playTracks(p.tracks)}><Icon name="play" /> Play</button>
              <button className="btn ghost" onClick={() => music.playTracks(p.tracks, 0, true)}><Icon name="shuffle" /> Shuffle</button>
            </>}
            <button className="btn ghost" onClick={() => setEditing(true)}><Icon name="edit" /> Edit</button>
            {p.tracks.length > 0 && <DownloadButton kind="user_playlist" id={p.id} title={p.name} what=" playlist" />}
            {deleting ? (
              <span className="confirm">
                Delete {p.name}? Its songs stay in your library.
                <button className="btn ghost small danger" onClick={del}>Delete</button>
                <button className="btn ghost small" onClick={() => setDeleting(false)}>Cancel</button>
              </span>
            ) : <button className="btn ghost" onClick={() => setDeleting(true)}><Icon name="close" /> Delete</button>}
          </div>
          {err && <p className="key-msg bad">{err}</p>}
        </div>
      </div>
      <section className="music-section">
        {p.tracks.length ? <TrackList tracks={p.tracks} showAlbum numbered edit={{ move, remove }} />
          : <p className="muted">No songs yet. Press <Icon name="listPlus" size={14} /> on a song, or "Add to playlist" on an
              album or an artist.</p>}
      </section>
      {editing && <EditPlaylistDialog playlist={p} onClose={() => setEditing(false)}
        saved={() => { setEditing(false); reload(); }} />}
    </div>
  );
}
