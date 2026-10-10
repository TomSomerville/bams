import { useEffect, useRef, useState } from "react";
import { ridOf, sources, type ItemSummary } from "../api";
import { askAll, byTitle, keyOf, searchPaths, type Tagged } from "../../../web/src/everywhere";
import { useFocusOnReady, useNav } from "../App";
import { Poster, Square } from "../Cards";
import { clock } from "../format";
import Icon from "../Icon";
import { useMusic } from "../music";

type Item = Tagged<ItemSummary>;
type Hits = { video: Item[]; music: Item[]; tracks: Item[] };

/** The web's Search (web/src/pages/Search.tsx): shows & movies, artists, albums and tracks of every server on
 *  this TV, by title. The TV's on-screen keyboard opens on OK. */
export default function Search() {
  const nav = useNav();
  const music = useMusic();
  const [q, setQ] = useState(() => sessionStorage.getItem("bams.q") || "");
  const [hits, setHits] = useState<Hits | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    sessionStorage.setItem("bams.q", q);
    clearTimeout(timer.current);
    if (!q.trim()) return setHits(null);
    let alive = true;
    timer.current = setTimeout(() => {
      const p = searchPaths(q);
      const got = { video: [] as Item[][], music: [] as Item[][], tracks: [] as Item[][] };
      const show = () => alive && setHits({ video: byTitle(got.video), music: byTitle(got.music), tracks: byTitle(got.tracks, 50) });
      for (const k of ["video", "music", "tracks"] as const) {
        void askAll<ItemSummary>(sources(), p[k], (_r, l) => { got[k].push(l); show(); });
      }
    }, 350);
    return () => { alive = false; };
  }, [q]);

  useFocusOnReady(true);

  const artists = hits?.music.filter((i) => i.kind === "artist") ?? [];
  const albums = hits?.music.filter((i) => i.kind === "album") ?? [];
  const total = hits ? hits.video.length + hits.music.length + hits.tracks.length : 0;
  return (
    <div className="page">
      <div className="page-head"><h1>Search</h1></div>
      <input className="text-input wide-input" data-fid="q" data-autofocus placeholder="Title, artist, album, track…" value={q}
        onChange={(e) => setQ(e.target.value)} />
      {hits && !total && <p className="muted big">Nothing matches “{q}”.</p>}
      {!!hits?.video.length && (
        <section className="search-section">
          <h2>Shows &amp; movies</h2>
          <div className="grid">
            {hits.video.map((it) => (
              <Poster key={keyOf(it)} item={it} rid={ridOf(it.rid)} fid={`hit-${keyOf(it)}`}
                onPress={() => nav.push({ name: "detail", id: it.id, rid: ridOf(it.rid) })} />
            ))}
          </div>
        </section>
      )}
      {[{ title: "Artists", list: artists }, { title: "Albums", list: albums }].map((s) => s.list.length > 0 && (
        <section key={s.title} className="search-section">
          <h2>{s.title}</h2>
          <div className="grid squares">
            {s.list.map((it) => (
              <Square key={keyOf(it)} fid={`hit-${keyOf(it)}`} rid={ridOf(it.rid)} img={it.poster} title={it.title}
                round={it.kind === "artist"} sub={it.kind === "album" ? [it.parent_title, it.year].filter(Boolean).join(" · ") : null}
                onPress={() => nav.push({ name: "detail", id: it.id, rid: ridOf(it.rid) })} />
            ))}
          </div>
        </section>
      ))}
      {!!hits?.tracks.length && (
        <section className="search-section">
          <h2>Tracks</h2>
          <div className="tracks">
            {hits.tracks.map((t) => (
              <button key={keyOf(t)} className="track" data-fid={`hit-${keyOf(t)}`} onClick={() => void music.playItem(t.id, ridOf(t.rid))}>
                <span className="track-num"><Icon name="play" size={24} /></span>
                <span className="track-title">{t.title}<small>{[t.artist, t.parent_title].filter(Boolean).join(" · ")}</small></span>
                <span className="track-time">{clock(t.duration)}</span>
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
