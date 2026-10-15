// Music on the TV, the same pages as the web's (web/src/pages/Music.tsx): a music library (Artists / Albums /
// Playlists), an artist (bio, albums), an album (tracks by disc), a playlist. Playing goes to the TV's one music
// player (music.tsx), which keeps going while you browse.

import { useEffect, useMemo, useState } from "react";
import {
  apiFor, mediaFor, type ItemDetail, type ItemSummary, type Playlist, type PlaylistSummary, type QueueTrack, type UserPlaylist,
  type UserPlaylistSummary,
} from "../api";
import { qualityLine } from "../../../web/src/quality";
import { AddToPlaylistMenu, EditPlaylistMenu, HoldMenu, NewPlaylistMenu, PlaylistTrackMenu } from "../PlaylistMenus";
import { useFocusOnReady, useNav } from "../App";
import { Square } from "../Cards";
import { clock } from "../format";
import Icon from "../Icon";
import { useMusic } from "../music";
import { focusId } from "../nav";
import { QueuePanel } from "../Queue";
import { PlayRandomButton } from "../random";
import { session } from "../platform";

const TABS = { artist: "Artists", album: "Albums", playlist: "Playlists" } as const;
type Tab = keyof typeof TABS;

/** A music library: artists, albums or playlists. */
export function MusicLibrary({ id, rid, name }: { id: number; rid?: number; name: string }) {
  const nav = useNav();
  const key = rid === undefined ? `${id}` : `r${rid}.${id}`;
  const [tab, setTab] = useState<Tab>(() => (session.get(`bams.mtab.${key}`) as Tab) || "artist");
  const [items, setItems] = useState<ItemSummary[] | null>(null);
  const [lists, setLists] = useState<PlaylistSummary[] | null>(null);
  const [mine, setMine] = useState<UserPlaylistSummary[] | null>(null);
  const [making, setMaking] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    session.set(`bams.mtab.${key}`, tab);
    setItems(null);
    setLists(null);
    const api = apiFor(rid);
    if (tab === "playlist") {
      api.get<PlaylistSummary[]>(`/api/libraries/${id}/playlists`).then(setLists).catch((e) => setErr(e.message));
      api.get<UserPlaylistSummary[]>("/api/user-playlists").then(setMine).catch(() => setMine([]));
    }
    else api.get<ItemSummary[]>(`/api/libraries/${id}/items?kind=${tab}&sort=${tab === "album" ? "artist" : "title"}&limit=5000`)
      .then(setItems).catch((e) => setErr(e.message));
  }, [id, rid, tab, key]);

  useFocusOnReady(items !== null || lists !== null);
  const count = tab === "playlist" ? (lists && mine ? lists.length + mine.length : undefined) : items?.length;

  return (
    <div className="page">
      <div className="page-head">
        <h1>{name}</h1>
        <div className="chips">
          {(Object.keys(TABS) as Tab[]).map((t) => (
            <button key={t} data-fid={`tab-${t}`} className={`chip ${tab === t ? "on" : ""}`} onClick={() => setTab(t)}>{TABS[t]}</button>
          ))}
        </div>
        {count !== undefined && <span className="muted big">{count}</span>}
        <PlayRandomButton chip path={`/api/libraries/${id}/random`} rid={rid} />
      </div>
      {err && <p className="error big">{err}</p>}
      {items === null && lists === null && !err && <div className="spinner" />}
      {tab === "playlist" && (
        <>
          <h2 className="list-head">Your playlists</h2>
          <div className="grid squares">
            <button className="card square new-playlist" data-fid="pl-new" onClick={() => setMaking(true)}>
              <div className="square-art"><div className="no-art"><Icon name="plus" size={90} /></div></div>
              <div className="square-title">New playlist</div>
            </button>
            {mine?.map((p) => (
              <Square key={`u${p.id}`} fid={`upl-${p.id}`} rid={rid} img={p.covers[0] ?? null} title={p.name}
                sub={`${p.track_count} tracks`} onPress={() => nav.push({ name: "my-playlist", id: p.id, rid })} />
            ))}
          </div>
          <h2 className="list-head">From playlist files</h2>
          {lists && !lists.length && (
            <p className="muted big">None. BAMS imports playlist files (.m3u, .m3u8, .pls) it finds in this library's folders.</p>
          )}
          {making && <NewPlaylistMenu rid={rid} onClose={() => { setMaking(false); setTimeout(() => focusId("pl-new")); }}
            created={(p) => { setMaking(false); nav.push({ name: "my-playlist", id: p.id, rid }); }} />}
        </>
      )}
      {tab !== "playlist" && items && !items.length && <p className="muted big">Nothing here yet.</p>}
      <div className="grid squares">
        {tab !== "playlist" && items?.map((it) => (
          <Square key={it.id} fid={`m-${it.id}`} rid={rid} img={it.poster} title={it.title} round={it.kind === "artist"}
            sub={it.kind === "album" ? [it.parent_title, it.year].filter(Boolean).join(" · ") : `${it.child_count ?? 0} albums`}
            onPress={() => nav.push({ name: "detail", id: it.id, rid })} />
        ))}
        {tab === "playlist" && lists?.map((p) => (
          <Square key={p.id} fid={`pl-${p.id}`} rid={rid} img={p.covers[0] ?? null} title={p.name}
            sub={`${p.track_count} tracks`} onPress={() => nav.push({ name: "playlist", id: p.id, rid })} />
        ))}
      </div>
    </div>
  );
}

/** A list of tracks; OK plays from that one. */
function TrackList({ tracks, rid, numbered = false, showAlbum = false, onHold }: {
  tracks: QueueTrack[]; rid?: number; numbered?: boolean; showAlbum?: boolean;
  /** holding OK on a track (hold.ts): its menu (add to a playlist; in your own playlist, move or take out) */
  onHold?: (i: number) => void;
}) {
  const music = useMusic();
  const discs = new Set(tracks.map((t) => t.disc_number ?? 1)).size > 1;
  let lastDisc: number | null = null;
  return (
    <div className="tracks">
      {tracks.map((t, i) => {
        const disc = t.disc_number ?? 1;
        const head = !numbered && discs && disc !== lastDisc ? <div className="disc-head">Disc {disc}</div> : null;
        lastDisc = disc;
        const on = music.current?.id === t.id && music.current.rid === rid;
        return (
          <div key={`${t.id}-${i}`}>
            {head}
            <button className={`track ${on ? "on" : ""}`} data-fid={`t-${t.id}-${i}`} disabled={!t.available}
              data-hold={onHold ? "" : undefined} onContextMenu={onHold ? (e) => { e.preventDefault(); onHold(i); } : undefined}
              onClick={() => (on ? music.toggle() : music.playTracks(tracks, rid, i))}>
              <span className="track-num">{on && music.playing ? <Icon name="music" size={26} /> : numbered ? i + 1 : t.track_number ?? ""}</span>
              <span className="track-title">{t.title}
                {(showAlbum || t.artist !== t.album_artist) && <small>{[t.artist !== t.album_artist ? t.artist : null, showAlbum ? t.album : null].filter(Boolean).join(" · ")}</small>}
              </span>
              <span className="track-time">{clock(t.duration)}</span>
            </button>
          </div>
        );
      })}
    </div>
  );
}

/** An artist's or an album's page. */
export function MusicDetail({ item, rid }: { item: ItemDetail; rid?: number }) {
  const nav = useNav();
  const music = useMusic();
  const media = mediaFor(rid);
  const [tracks, setTracks] = useState<QueueTrack[] | null>(null);
  const [adding, setAdding] = useState<{ items: number[]; title: string; fid: string } | null>(null);
  const isAlbum = item.kind === "album" || item.kind === "track";
  useEffect(() => {
    if (isAlbum) apiFor(rid).get<QueueTrack[]>(`/api/items/${item.kind === "track" && item.parent_id ? item.parent_id : item.id}/tracks`)
      .then(setTracks).catch(() => setTracks([]));
  }, [item.id, item.kind, item.parent_id, rid, isAlbum]);
  useFocusOnReady(!isAlbum || tracks !== null);

  const artist = item.kind === "album" ? item.ancestors.find((a) => a.kind === "artist") : null;
  const x = item.extra ?? {};
  const credit = x.image_credit;
  const playId = item.kind === "track" && item.parent_id ? item.parent_id : item.id;
  const sub = item.kind === "artist"
    ? [`${item.children.length} albums`, x.country, x.life_span?.begin ? `since ${x.life_span.begin.slice(0, 4)}` : null]
    : [artist?.title, item.year, tracks ? `${tracks.length} tracks` : null,
       tracks ? clock(tracks.reduce((s, t) => s + (t.duration ?? 0), 0)) : null];

  return (
    <div className="page music-detail">
      <div className="detail-top">
        {item.poster ? <img className={`music-cover ${item.kind === "artist" ? "round-art" : ""}`} src={media(item.poster) ?? undefined} alt="" />
          : <div className="music-cover no-art"><Icon name="music" size={90} /></div>}
        <div className="detail-text">
          <div className="eyebrow">{item.kind === "artist" ? "Artist" : x.type || "Album"}</div>
          <h1>{item.title}</h1>
          <div className="meta">{sub.filter(Boolean).join("  ·  ")}</div>
          {item.overview && <p className="overview clamp4">{item.overview}</p>}
          {(x.wikipedia || credit) && (
            <p className="credit">
              {x.wikipedia && <>Text from Wikipedia (CC BY-SA). </>}
              {credit && <>Photo: {[credit.author, credit.license].filter(Boolean).join(", ")}, Wikimedia Commons.</>}
            </p>
          )}
          <div className="button-row">
            <button className="btn primary" data-autofocus data-fid="mplay" onClick={() => void music.playItem(playId, rid)}>
              <Icon name="play" size={30} /> Play
            </button>
            <button className="btn" data-fid="mshuffle" onClick={() => void music.playItem(playId, rid, { shuffle: true })}>
              <Icon name="shuffle" size={30} /> Shuffle
            </button>
            {item.kind === "artist" && <PlayRandomButton path={`/api/items/${item.id}/random`} rid={rid} />}
            <button className="btn" data-fid="maddpl" onClick={() => setAdding({ items: [playId], title: item.kind === "track" ? item.parent_title ?? item.title : item.title, fid: "maddpl" })}>
              <Icon name="listPlus" size={30} /> Add to playlist
            </button>
            {artist && <button className="btn" data-fid="martist" onClick={() => nav.push({ name: "detail", id: artist.id, rid })}>{artist.title}</button>}
          </div>
        </div>
      </div>
      {item.kind === "artist" && (
        <div className="grid squares">
          {item.children.map((a) => (
            <Square key={a.id} fid={`alb-${a.id}`} rid={rid} img={a.poster} title={a.title} sub={a.year ? String(a.year) : null}
              onPress={() => nav.push({ name: "detail", id: a.id, rid })} />
          ))}
        </div>
      )}
      {isAlbum && tracks && <TrackList tracks={tracks} rid={rid}
        onHold={(i) => setAdding({ items: [tracks[i].id], title: tracks[i].title, fid: `t-${tracks[i].id}-${i}` })} />}
      {adding && <AddToPlaylistMenu items={adding.items} title={adding.title} rid={rid}
        onClose={() => { const back = adding.fid; setAdding(null); setTimeout(() => focusId(back)); }} />}
    </div>
  );
}

/** An imported playlist, in its own order. */
export function PlaylistScreen({ id, rid }: { id: number; rid?: number }) {
  const music = useMusic();
  const nav = useNav();
  const [adding, setAdding] = useState<{ track: QueueTrack; fid: string } | null>(null);
  const media = mediaFor(rid);
  const [p, setP] = useState<Playlist | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    apiFor(rid).get<Playlist>(`/api/playlists/${id}`).then(setP).catch((e) => setErr(e.message));
  }, [id, rid]);
  useFocusOnReady(p !== null);
  const length = useMemo(() => (p ? p.tracks.reduce((s, t) => s + (t.duration ?? 0), 0) : 0), [p]);
  if (err) return <div className="page"><p className="error big">{err}</p></div>;
  if (!p) return <div className="page"><div className="spinner" /></div>;
  return (
    <div className="page music-detail">
      <div className="detail-top">
        {p.covers[0] ? <img className="music-cover" src={media(p.covers[0]) ?? undefined} alt="" />
          : <div className="music-cover no-art"><Icon name="music" size={90} /></div>}
        <div className="detail-text">
          <div className="eyebrow">Playlist · {p.library_name}</div>
          <h1>{p.name}</h1>
          <div className="meta">{p.tracks.length} tracks  ·  {clock(length)}{p.missing ? `  ·  ${p.missing} not found` : ""}</div>
          <div className="button-row">
            <button className="btn primary" data-autofocus data-fid="pplay" onClick={() => music.playTracks(p.tracks, rid)}>
              <Icon name="play" size={30} /> Play
            </button>
            <button className="btn" data-fid="pshuffle" onClick={() => music.playTracks(p.tracks, rid, 0, true)}>
              <Icon name="shuffle" size={30} /> Shuffle
            </button>
            <button className="btn" data-fid="pcopy" onClick={() => {
              apiFor(rid).post<UserPlaylistSummary>("/api/user-playlists", { name: p.name, copy_of: p.id })
                .then((c) => nav.push({ name: "my-playlist", id: c.id, rid })).catch((e) => setErr(e.message));
            }}><Icon name="plus" size={30} /> Make a copy</button>
          </div>
        </div>
      </div>
      <TrackList tracks={p.tracks} rid={rid} numbered showAlbum
        onHold={(i) => setAdding({ track: p.tracks[i], fid: `t-${p.tracks[i].id}-${i}` })} />
      {adding && <AddToPlaylistMenu items={[adding.track.id]} title={adding.track.title} rid={rid}
        onClose={() => { const back = adding.fid; setAdding(null); setTimeout(() => focusId(back)); }} />}
    </div>
  );
}

/** One of your playlists: play it, hold OK on a song to move it or take it out, rename it, delete it. */
export function UserPlaylistScreen({ id, rid }: { id: number; rid?: number }) {
  const music = useMusic();
  const nav = useNav();
  const media = mediaFor(rid);
  const [p, setP] = useState<UserPlaylist | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [menu, setMenu] = useState<number | null>(null);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const load = () => apiFor(rid).get<UserPlaylist>(`/api/user-playlists/${id}`).then(setP).catch((e) => setErr(e.message));
  useEffect(() => { void load(); }, [id, rid]); // eslint-disable-line react-hooks/exhaustive-deps
  useFocusOnReady(p !== null);
  if (err && !p) return <div className="page"><p className="error big">{err}</p></div>;
  if (!p) return <div className="page"><div className="spinner" /></div>;

  const save = (tracks: QueueTrack[], focusAt: number) => {
    setP({ ...p, tracks, track_count: tracks.length });
    setMenu(null);
    setTimeout(() => {
      const t = tracks[Math.min(focusAt, tracks.length - 1)];
      if (!(t && focusId(`t-${t.id}-${Math.min(focusAt, tracks.length - 1)}`))) focusId("uplay");
    });
    apiFor(rid).put<UserPlaylist>(`/api/user-playlists/${p.id}/tracks`, { tracks: tracks.map((t) => t.id) })
      .then(setP).catch((e) => { setErr(e.message); void load(); });
  };
  const move = (i: number, by: -1 | 1) => {
    const next = [...p.tracks];
    next.splice(i + by, 0, ...next.splice(i, 1));
    save(next, i + by);
  };
  const closeMenu = (i: number) => {
    setMenu(null);
    setTimeout(() => focusId(`t-${p.tracks[i].id}-${i}`));
  };
  const del = () => apiFor(rid).del(`/api/user-playlists/${p.id}`).then(() => nav.back()).catch((e) => setErr(e.message));

  return (
    <div className="page music-detail">
      <div className="detail-top">
        {p.covers[0] ? <img className="music-cover" src={media(p.covers[0]) ?? undefined} alt="" />
          : <div className="music-cover no-art"><Icon name="music" size={90} /></div>}
        <div className="detail-text">
          <div className="eyebrow">Your playlist</div>
          <h1>{p.name}</h1>
          <div className="meta">{p.tracks.length} tracks  ·  {clock(p.duration ?? 0)}</div>
          {p.description && <p className="playlist-desc">{p.description}</p>}
          {err && <p className="error">{err}</p>}
          <div className="button-row">
            {p.tracks.length > 0 && <>
              <button className="btn primary" data-autofocus data-fid="uplay" onClick={() => music.playTracks(p.tracks, rid)}>
                <Icon name="play" size={30} /> Play
              </button>
              <button className="btn" data-fid="ushuffle" onClick={() => music.playTracks(p.tracks, rid, 0, true)}>
                <Icon name="shuffle" size={30} /> Shuffle
              </button>
            </>}
            <button className="btn" data-fid="uedit" data-autofocus={p.tracks.length ? undefined : true} onClick={() => setEditing(true)}>
              <Icon name="edit" size={30} /> Edit
            </button>
            <button className="btn" data-fid="udelete" onClick={() => setDeleting(true)}><Icon name="close" size={30} /> Delete</button>
          </div>
        </div>
      </div>
      {p.tracks.length ? <TrackList tracks={p.tracks} rid={rid} numbered showAlbum onHold={setMenu} />
        : <p className="muted big">No songs yet. Hold OK on a song, or press "Add to playlist" on an album or an artist.</p>}
      {menu !== null && p.tracks[menu] && (
        <PlaylistTrackMenu title={p.tracks[menu].title} first={menu === 0} last={menu === p.tracks.length - 1}
          onMove={(by) => move(menu, by)} onRemove={() => save(p.tracks.filter((_, k) => k !== menu), menu)}
          onClose={() => closeMenu(menu)} />
      )}
      {editing && <EditPlaylistMenu playlist={p} rid={rid} onClose={() => { setEditing(false); setTimeout(() => focusId("uedit")); }}
        saved={() => { setEditing(false); void load(); setTimeout(() => focusId("uedit")); }} />}
      {deleting && (
        <HoldMenu title={`Delete ${p.name}?`} sub="Its songs stay in your library." onClose={() => { setDeleting(false); setTimeout(() => focusId("udelete")); }}>
          <div className="button-row">
            <button className="btn primary" onClick={() => void del()}>Delete</button>
            <button className="btn" onClick={() => { setDeleting(false); setTimeout(() => focusId("udelete")); }}>Cancel</button>
          </div>
        </HoldMenu>
      )}
    </div>
  );
}

/** The bar at the bottom while music is queued: what's playing, previous / play-pause / next / stop. The remote's
 *  media keys do the same from anywhere (App.tsx). */
export function NowPlaying() {
  const m = useMusic();
  const [queue, setQueue] = useState(false);
  const t = m.current;
  if (!t) return null;
  const media = mediaFor(t.rid);
  const pct = m.duration ? Math.min(100, (m.time / m.duration) * 100) : 0;
  return (
    <>
    <div className="now-playing" data-group data-cover>
      {t.poster ? <img className="np-cover" src={media(t.poster) ?? undefined} alt="" /> : <div className="np-cover no-art" />}
      <div className="np-text">
        <div className="np-title">{t.title}</div>
        <div className="np-sub">{[t.artist, t.album].filter(Boolean).join("  ·  ")}{m.error ? `  ·  ${m.error}` : ""}</div>
        {qualityLine(t.playback, m.converted) && <div className="np-quality">{qualityLine(t.playback, m.converted)}</div>}
        <div className="np-bar"><div style={{ width: `${pct}%` }} /></div>
      </div>
      <span className="np-time">{clock(m.time)} / {clock(m.duration)}</span>
      <button className="round" data-fid="np-prev" onClick={m.prev} aria-label="Previous"><Icon name="prev" /></button>
      <button className="round" data-fid="np-play" onClick={m.toggle} aria-label={m.playing ? "Pause" : "Play"}>
        <Icon name={m.playing ? "pause" : "play"} />
      </button>
      <button className="round" data-fid="np-next" onClick={m.next} disabled={m.index + 1 >= m.queue.length} aria-label="Next"><Icon name="next" /></button>
      <button className="round" data-fid="np-queue" onClick={() => setQueue(true)} aria-label="Up next"><Icon name="list" /></button>
      <button className="round" data-fid="np-stop" onClick={m.stop} aria-label="Stop"><Icon name="stop" /></button>
    </div>
    {queue && (
      <QueuePanel at={m.index} onJump={m.jump} onMove={m.move} onRemove={m.remove}
        rows={m.queue.map((x, i) => ({ key: `${x.id}-${i}`, title: x.title, sub: [x.artist, x.album].filter(Boolean).join("  ·  ") }))}
        onClose={() => { setQueue(false); setTimeout(() => focusId("np-queue")); }} />
    )}
    </>
  );
}
