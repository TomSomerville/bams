// Music on the TV, the same pages as the web's (web/src/pages/Music.tsx): a music library (Artists / Albums /
// Playlists), an artist (bio, albums), an album (tracks by disc), a playlist. Playing goes to the TV's one music
// player (music.tsx), which keeps going while you browse.

import { useEffect, useMemo, useState } from "react";
import { apiFor, mediaFor, type ItemDetail, type ItemSummary, type Playlist, type PlaylistSummary, type QueueTrack } from "../api";
import { useFocusOnReady, useNav } from "../App";
import { Square } from "../Cards";
import { clock } from "../format";
import Icon from "../Icon";
import { useMusic } from "../music";

const TABS = { artist: "Artists", album: "Albums", playlist: "Playlists" } as const;
type Tab = keyof typeof TABS;

/** A music library: artists, albums or playlists. */
export function MusicLibrary({ id, rid, name }: { id: number; rid?: number; name: string }) {
  const nav = useNav();
  const key = rid === undefined ? `${id}` : `r${rid}.${id}`;
  const [tab, setTab] = useState<Tab>(() => (sessionStorage.getItem(`bams.mtab.${key}`) as Tab) || "artist");
  const [items, setItems] = useState<ItemSummary[] | null>(null);
  const [lists, setLists] = useState<PlaylistSummary[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    sessionStorage.setItem(`bams.mtab.${key}`, tab);
    setItems(null);
    setLists(null);
    const api = apiFor(rid);
    if (tab === "playlist") api.get<PlaylistSummary[]>(`/api/libraries/${id}/playlists`).then(setLists).catch((e) => setErr(e.message));
    else api.get<ItemSummary[]>(`/api/libraries/${id}/items?kind=${tab}&sort=${tab === "album" ? "artist" : "title"}&limit=5000`)
      .then(setItems).catch((e) => setErr(e.message));
  }, [id, rid, tab, key]);

  useFocusOnReady(items !== null || lists !== null);
  const count = tab === "playlist" ? lists?.length : items?.length;

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
      </div>
      {err && <p className="error big">{err}</p>}
      {items === null && lists === null && !err && <div className="spinner" />}
      {tab === "playlist" && lists && !lists.length && (
        <p className="muted big">No playlists. BAMS imports playlist files (.m3u, .m3u8, .pls) it finds in this library's folders.</p>
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
function TrackList({ tracks, rid, numbered = false, showAlbum = false }: {
  tracks: QueueTrack[]; rid?: number; numbered?: boolean; showAlbum?: boolean;
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
      {isAlbum && tracks && <TrackList tracks={tracks} rid={rid} />}
    </div>
  );
}

/** An imported playlist, in its own order. */
export function PlaylistScreen({ id, rid }: { id: number; rid?: number }) {
  const music = useMusic();
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
          </div>
        </div>
      </div>
      <TrackList tracks={p.tracks} rid={rid} numbered showAlbum />
    </div>
  );
}

/** The bar at the bottom while music is queued: what's playing, previous / play-pause / next / stop. The remote's
 *  media keys do the same from anywhere (App.tsx). */
export function NowPlaying() {
  const m = useMusic();
  const t = m.current;
  if (!t) return null;
  const media = mediaFor(t.rid);
  const pct = m.duration ? Math.min(100, (m.time / m.duration) * 100) : 0;
  return (
    <div className="now-playing" data-group data-cover>
      {t.poster ? <img className="np-cover" src={media(t.poster) ?? undefined} alt="" /> : <div className="np-cover no-art" />}
      <div className="np-text">
        <div className="np-title">{t.title}</div>
        <div className="np-sub">{[t.artist, t.album].filter(Boolean).join("  ·  ")}{m.error ? `  ·  ${m.error}` : ""}</div>
        <div className="np-bar"><div style={{ width: `${pct}%` }} /></div>
      </div>
      <span className="np-time">{clock(m.time)} / {clock(m.duration)}</span>
      <button className="round" data-fid="np-prev" onClick={m.prev} aria-label="Previous"><Icon name="prev" /></button>
      <button className="round" data-fid="np-play" onClick={m.toggle} aria-label={m.playing ? "Pause" : "Play"}>
        <Icon name={m.playing ? "pause" : "play"} />
      </button>
      <button className="round" data-fid="np-next" onClick={m.next} disabled={m.index + 1 >= m.queue.length} aria-label="Next"><Icon name="next" /></button>
      <button className="round" data-fid="np-stop" onClick={m.stop} aria-label="Stop"><Icon name="stop" /></button>
    </div>
  );
}
