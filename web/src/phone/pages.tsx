import { Fragment, useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { app } from "../android";
import { Backdrop, Poster } from "../components/Art";
import Icon from "../components/Icon";
import { fmtClock, fmtLength, fmtRuntime, fmtSize, plural, sxe } from "../format";
import { musicCmd, playTracks, useLib, useMusicState } from "./App";
import { episodesOf, here, ik, rootOf, shelves, tracksOf, type Item, type Library, type Playlist, type RootKind, type RootRow, type Track } from "./lib";

const base = import.meta.env.BASE_URL;

/** While the app looks for the server, at start. */
export function StartPage() {
  return (
    <div className="phone-start">
      <img src={`${base}brand/bams-wordmark.png`} alt="BAMS" />
      <p className="muted">Looking for your server…</p>
      <div className="progress inline indeterminate"><div /></div>
    </div>
  );
}

const pct = (p: number) => `${Math.floor(p * 100)}%`;

function stateText(r: RootRow): string {
  const s = r.status;
  switch (s.state) {
    case "queued": return "Waiting to download";
    case "downloading": return `Downloading · ${pct(s.progress)} of ${fmtSize(s.bytes)}`;
    case "paused": return `Waiting for Wi-Fi · ${pct(s.progress)}`;
    case "failed": return s.error ?? "Failed";
    case "done": return fmtSize(s.bytes);
    default: return "";
  }
}

const KIND: Record<string, string> = {
  movie: "Movie", show: "Show", season: "Season", episode: "Episode", artist: "Artist", album: "Album", track: "Song",
};

function kindOf(lib: Library, r: RootRow): string {
  if (r.kind === "playlist") return "Playlist";
  if (r.kind === "user_playlist") return "Your playlist";
  const it = lib.items.get(ik(r.sid, r.id));
  return (it && KIND[it.kind]) ?? r.manifest?.root.kind ?? "";
}

/** Remove a download from the phone, after asking. */
function RemoveButton({ root, small }: { root: RootRow; small?: boolean }) {
  const [asking, setAsking] = useState(false);
  const busy = root.status.state !== "done" && root.status.state !== "failed";
  if (asking) {
    return (
      <span className="confirm">
        {busy ? "Stop this download?" : "Remove it from this phone?"}
        <button className="btn ghost small danger" onClick={() => app("removeDownload", { key: root.key }).catch(() => {})}>
          {busy ? "Stop" : "Remove"}
        </button>
        <button className="btn ghost small" onClick={() => setAsking(false)}>Cancel</button>
      </span>
    );
  }
  return small
    ? <button className="icon-btn subtle" onClick={() => setAsking(true)} aria-label={`Remove ${root.title}`} title="Remove from this phone">
        <Icon name="close" size={16} /></button>
    : <button className="btn ghost" onClick={() => setAsking(true)}><Icon name="close" /> {busy ? "Stop download" : "Remove download"}</button>;
}

function Card({ it, square, round }: { it: Item; square?: boolean; round?: boolean }) {
  const p = it.progress;
  const frac = p && !p.watched && p.duration ? p.position / p.duration : null;
  return (
    <Link to={`/t/${it.sid}/${it.id}`} className={`poster-card ${square ? "album-card" : ""} ${round ? "artist-card" : ""}`}>
      <div className={`poster-frame ${square ? "square" : ""} ${round ? "round" : ""}`}>
        <Poster src={it.poster} title={it.title} />
        {frac !== null && frac > 0 && <div className="progress"><div style={{ width: `${frac * 100}%` }} /></div>}
      </div>
      <div className="poster-title">{it.title}</div>
      <div className="poster-sub">{[it.kind === "album" ? it.parent_title : null, it.year].filter(Boolean).join(" · ")}</div>
    </Link>
  );
}

function PlaylistCard({ p }: { p: Playlist }) {
  return (
    <Link to={`/p/${p.sid}/${p.ref}`} className="poster-card album-card">
      <div className="poster-frame square"><Mosaic covers={p.covers} name={p.name} /></div>
      <div className="poster-title">{p.name}</div>
      <div className="poster-sub">{plural(p.tracks.length, "track")}</div>
    </Link>
  );
}

function Mosaic({ covers, name }: { covers: string[]; name: string }) {
  if (covers.length < 4) return <Poster src={covers[0]} title={name} />;
  return <div className="mosaic">{covers.slice(0, 4).map((c) => <img key={c} src={c} alt="" loading="lazy" />)}</div>;
}

function Empty() {
  return (
    <div className="lib-card settings-card">
      <h3>Nothing on this phone yet</h3>
      <p className="muted">Open your server (Servers), then press <strong>Download</strong> on a movie, an episode, a
        season or a whole show, a song, an album, an artist or a playlist. What you download plays here with no
        connection, in its original quality.</p>
    </div>
  );
}

/** The app's version, at the bottom of Downloads (which build is on the phone). */
function AppVersion() {
  const [v, setV] = useState<string | null>(null);
  useEffect(() => { app<{ version: string }>("info").then((i) => setV(i.version)).catch(() => {}); }, []);
  return v ? <p className="fine-print">BAMS for Android {v}</p> : null;
}

export function DownloadsPage() {
  const { lib } = useLib();
  if (!lib) return <div className="page muted">Loading…</div>;
  const { movies, shows, albums } = shelves(lib);
  const going = lib.roots.filter((r) => r.status.state !== "done");
  const done = lib.roots.filter((r) => r.status.state === "done").sort((a, b) => b.added - a.added);
  return (
    <div className="page">
      <div className="page-head">
        <h1>Downloads</h1>
        <span className="count">{fmtSize(lib.used)} on this phone</span>
      </div>
      {!lib.roots.length && <Empty />}
      {going.length > 0 && (
        <>
          <div className="section-head"><h2 className="section-title">Downloading</h2></div>
          <ul className="phone-list">
            {going.map((r) => (
              <li key={r.key} className="phone-row">
                <div className="phone-row-text">
                  <strong>{r.title}</strong>
                  <span className={`muted ${r.status.state === "failed" ? "bad" : ""}`}>{kindOf(lib, r)} · {stateText(r)}</span>
                  {r.status.state !== "failed" && (
                    <div className={`progress inline ${r.status.state === "queued" ? "indeterminate" : ""}`}>
                      <div style={r.status.state === "queued" ? undefined : { width: pct(r.status.progress) }} />
                    </div>
                  )}
                </div>
                <RemoveButton small root={r} />
              </li>
            ))}
          </ul>
        </>
      )}
      {movies.length > 0 && <Shelf title="Movies" to="/movies">{movies.map((i) => <Card key={ik(i.sid, i.id)} it={i} />)}</Shelf>}
      {shows.length > 0 && <Shelf title="TV Shows" to="/shows">{shows.map((i) => <Card key={ik(i.sid, i.id)} it={i} />)}</Shelf>}
      {albums.length > 0 && <Shelf title="Albums" to="/music">{albums.map((i) => <Card key={ik(i.sid, i.id)} it={i} square />)}</Shelf>}
      {lib.playlists.length > 0 && <Shelf title="Playlists" to="/music">{lib.playlists.map((p) => <PlaylistCard key={`${p.sid}:${p.ref}`} p={p} />)}</Shelf>}
      {done.length > 0 && (
        <>
          <div className="section-head"><h2 className="section-title">Downloaded</h2></div>
          <ul className="phone-list">
            {done.map((r) => (
              <li key={r.key} className="phone-row">
                <div className="phone-row-text">
                  <Link to={r.kind !== "item" ? `/p/${r.sid}/${r.kind}:${r.id}` : `/t/${r.sid}/${titleOf(lib, r)}`}><strong>{r.title}</strong></Link>
                  <span className="muted">{kindOf(lib, r)} · {stateText(r)}{lib.servers.size > 1 ? ` · ${lib.servers.get(r.sid) ?? ""}` : ""}</span>
                </div>
                <RemoveButton small root={r} />
              </li>
            ))}
          </ul>
        </>
      )}
      <AppVersion />
    </div>
  );
}

/** The page a download opens: an episode or a season opens its show, a track its album. */
function titleOf(lib: Library, r: RootRow): number {
  const it = lib.items.get(ik(r.sid, r.id));
  if (!it) return r.id;
  if (it.kind === "episode" || it.kind === "season") return it.ancestors.find((a) => a.kind === "show")?.id ?? r.id;
  if (it.kind === "track") return it.parent_id ?? r.id;
  return r.id;
}

function Shelf({ title, to, children }: { title: string; to: string; children: React.ReactNode }) {
  return (
    <section className="phone-shelf">
      <div className="section-head"><h2 className="section-title">{title}</h2><Link to={to} className="row-more">See all</Link></div>
      <div className="row-track">{children}</div>
    </section>
  );
}

export function MoviesPage() {
  const { lib } = useLib();
  if (!lib) return <div className="page muted">Loading…</div>;
  const { movies } = shelves(lib);
  return (
    <div className="page">
      <div className="page-head"><h1>Movies</h1><span className="count">{plural(movies.length, "movie")}</span></div>
      {!movies.length && <p className="muted">No movies downloaded.</p>}
      <div className="grid">{movies.map((i) => <Card key={ik(i.sid, i.id)} it={i} />)}</div>
    </div>
  );
}

export function ShowsPage() {
  const { lib } = useLib();
  if (!lib) return <div className="page muted">Loading…</div>;
  const { shows } = shelves(lib);
  return (
    <div className="page">
      <div className="page-head"><h1>TV Shows</h1><span className="count">{plural(shows.length, "show")}</span></div>
      {!shows.length && <p className="muted">No episodes downloaded.</p>}
      <div className="grid">{shows.map((i) => <Card key={ik(i.sid, i.id)} it={i} />)}</div>
    </div>
  );
}

const TABS = { artist: "Artists", album: "Albums", playlist: "Playlists" } as const;

export function MusicPage() {
  const { lib } = useLib();
  const [tab, setTab] = useState<keyof typeof TABS>("artist");
  if (!lib) return <div className="page muted">Loading…</div>;
  const { artists, albums } = shelves(lib);
  const n = tab === "artist" ? artists.length : tab === "album" ? albums.length : lib.playlists.length;
  return (
    <div className="page">
      <div className="page-head">
        <h1>Music</h1>
        <div className="segmented" role="tablist">
          {(Object.keys(TABS) as (keyof typeof TABS)[]).map((k) => (
            <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{TABS[k]}</button>
          ))}
        </div>
        <span className="count">{plural(n, tab)}</span>
      </div>
      {!n && <p className="muted">No {TABS[tab].toLowerCase()} downloaded.</p>}
      <div className="grid">
        {tab === "artist" && artists.map((i) => <Card key={ik(i.sid, i.id)} it={i} round />)}
        {tab === "album" && albums.map((i) => <Card key={ik(i.sid, i.id)} it={i} square />)}
        {tab === "playlist" && lib.playlists.map((p) => <PlaylistCard key={`${p.sid}:${p.ref}`} p={p} />)}
      </div>
    </div>
  );
}

/** Play downloaded movies/episodes with the app's player: [list] in order, from [index]. */
function playVideos(list: Item[], index: number, setErr: (e: string) => void) {
  app("playVideo", {
    queue: list.map((v) => ({
      sid: v.sid, id: v.id, title: v.kind === "episode" ? v.ancestors.find((a) => a.kind === "show")?.title ?? v.title : v.title,
      sub: v.kind === "episode" ? `${sxe(v.season_number ?? 0, v.episode_number)} ${v.title}` : v.year ? String(v.year) : null,
      position: v.progress?.watched ? 0 : v.progress?.position ?? 0, duration: v.progress?.duration ?? null,
    })),
    index,
  }).catch((e) => setErr(e.message));
}

export function TitlePage() {
  const { sid = "", id } = useParams();
  const { lib } = useLib();
  if (!lib) return <div className="page muted">Loading…</div>;
  const it = lib.items.get(ik(sid, Number(id)));
  if (!it) return <div className="page"><h1>Not on this phone</h1><p className="muted">It was removed from your downloads.</p></div>;
  if (it.kind === "artist" || it.kind === "album") return <MusicTitle lib={lib} it={it} />;
  return <VideoTitle lib={lib} it={it} />;
}

function VideoTitle({ lib, it }: { lib: Library; it: Item }) {
  const [err, setErr] = useState<string | null>(null);
  const eps = it.kind === "show" ? episodesOf(lib, it) : [];
  const seasons = [...new Set(eps.map((e) => e.season_number ?? 0))];
  const [season, setSeason] = useState<number | null>(null);
  const shown = season ?? seasons[0] ?? null;
  const root = rootOf(lib, it.sid, "item", it.id);
  const resumeAt = it.kind === "movie" && it.progress && !it.progress.watched ? it.progress.position : 0;
  const ready = it.kind === "movie" && here(lib, it.sid, it.id);
  const file = lib.fileOf.get(ik(it.sid, it.id));
  return (
    <div className="detail">
      <div className="detail-bg">
        <Backdrop src={it.backdrop} poster={it.poster} title={it.title} className="detail-img" />
        <div className="detail-shade" />
      </div>
      <div className="detail-body">
        <div className="detail-poster"><Poster src={it.poster} title={it.title} /></div>
        <div className="detail-info">
          <h1>{it.title}</h1>
          <div className="meta">
            {it.rating ? <span className="score">★ {it.rating.toFixed(1)}</span> : null}
            {it.year && <span>{it.year}</span>}
            <span>{it.kind === "show" ? plural(eps.length, "episode") + " on this phone" : fmtRuntime(it.runtime)}</span>
            {it.genres.map((g) => <span key={g} className="tag">{g}</span>)}
          </div>
          {it.tagline && <p className="tagline">{it.tagline}</p>}
          {it.overview && <p className="overview">{it.overview}</p>}
          <div className="actions">
            {it.kind === "movie" && (ready ? (
              <button className="btn primary" onClick={() => playVideos([it], 0, setErr)}>
                <Icon name="play" /> {resumeAt > 30 ? `Resume from ${fmtClock(resumeAt)}` : "Play"}
              </button>
            ) : <span className="muted">{file?.state === "missing" ? "Its storage isn't there (SD card out?)" : "Still downloading…"}</span>)}
            {it.kind === "show" && eps.some((e) => here(lib, e.sid, e.id)) && (
              <button className="btn primary" onClick={() => {
                const ready = eps.filter((e) => here(lib, e.sid, e.id));
                const next = ready.findIndex((e) => !e.progress?.watched);
                playVideos(ready, Math.max(0, next), setErr);
              }}><Icon name="play" /> Play</button>
            )}
            {root && <RemoveButton root={root} />}
          </div>
          {file && file.audio.length > 0 && <p className="tech-note">Sound: {file.audio.join(", ")}</p>}
          {err && <p className="key-msg bad">{err}</p>}
        </div>
      </div>
      {it.kind === "show" && seasons.length > 0 && (
        <section className="seasons">
          <div className="season-tabs">
            {seasons.map((s) => (
              <button key={s} className={`chip ${shown === s ? "on" : ""}`} onClick={() => setSeason(s)}>
                {s === 0 ? "Specials" : `Season ${s}`} <span className="chip-count">{eps.filter((e) => (e.season_number ?? 0) === s).length}</span>
              </button>
            ))}
          </div>
          <SeasonRemove lib={lib} show={it} season={shown} />
          <ol className="episodes">
            {eps.filter((e) => (e.season_number ?? 0) === shown).map((e, _i, list) => {
              const ok = here(lib, e.sid, e.id);
              const p = e.progress;
              const frac = p && !p.watched && p.duration ? p.position / p.duration : null;
              const own = rootOf(lib, e.sid, "item", e.id);
              const ready = list.filter((x) => here(lib, x.sid, x.id));
              return (
                <li key={e.id}>
                  <div className={`episode ${p?.watched ? "seen" : ""}`} role="button" tabIndex={0}
                    onClick={() => ok && playVideos(ready, ready.indexOf(e), setErr)}>
                    <span className="ep-num">{e.episode_number ?? "·"}</span>
                    <div className="ep-thumb">
                      {e.still ? <img className="ep-img" src={e.still} alt="" loading="lazy" />
                        : <Backdrop src={null} poster={it.poster} title={e.title} className="ep-img" />}
                      {ok && <span className="round-btn"><Icon name="play" size={16} /></span>}
                      {frac !== null && frac > 0 && <div className="progress"><div style={{ width: `${frac * 100}%` }} /></div>}
                    </div>
                    <div className="ep-text">
                      <div className="ep-title">{e.title} <span className="muted">· {sxe(e.season_number ?? 0, e.episode_number)}</span></div>
                      {!ok && <p className="muted">Still downloading…</p>}
                      {ok && e.overview && <p>{e.overview}</p>}
                    </div>
                    {own && <span onClick={(ev) => ev.stopPropagation()}><RemoveButton small root={own} /></span>}
                  </div>
                </li>
              );
            })}
          </ol>
        </section>
      )}
    </div>
  );
}

/** "Remove season" when that season was downloaded as one. */
function SeasonRemove({ lib, show, season }: { lib: Library; show: Item; season: number | null }) {
  const s = show.children.find((c) => c.kind === "season" && (c.season_number ?? 0) === season);
  const root = s ? rootOf(lib, show.sid, "item", s.id) : null;
  return root ? <div className="season-bar"><RemoveButton root={root} /></div> : null;
}

function MusicTitle({ lib, it }: { lib: Library; it: Item }) {
  const [err, setErr] = useState<string | null>(null);
  const tracks = tracksOf(lib, it);
  const root = rootOf(lib, it.sid, "item", it.id);
  const albums = it.kind === "artist"
    ? [...new Set(tracks.map((t) => t.album_id))].map((a) => lib.items.get(ik(it.sid, a))).filter((a): a is Item => !!a)
    : [];
  const play = (i: number, shuffle = false) => playTracks(tracks.filter((t) => here(lib, t.sid, t.id)), i, shuffle).catch((e) => setErr(e.message));
  return (
    <div className="detail music-detail">
      <div className="detail-bg">
        <Backdrop src={null} poster={it.poster} title={it.title} className="detail-img" />
        <div className="detail-shade" />
      </div>
      <div className="detail-body music-head">
        <div className={`music-art ${it.kind === "artist" ? "round" : ""}`}><Poster src={it.poster} title={it.title} /></div>
        <div className="detail-info">
          <div className="hero-kicker">{it.kind === "artist" ? "Artist" : "Album"}</div>
          <h1>{it.title}</h1>
          <div className="meta">
            {it.kind === "album" && it.parent_id && <Link to={`/t/${it.sid}/${it.parent_id}`} className="music-artist-link">{it.parent_title}</Link>}
            {it.year && <span>{it.year}</span>}
            <span>{plural(tracks.length, "track")} on this phone</span>
          </div>
          <div className="actions">
            <button className="btn primary" onClick={() => play(0)} disabled={!tracks.length}><Icon name="play" /> Play</button>
            <button className="btn ghost" onClick={() => play(0, true)} disabled={!tracks.length}><Icon name="shuffle" /> Shuffle</button>
            {root && <RemoveButton root={root} />}
          </div>
          {err && <p className="key-msg bad">{err}</p>}
        </div>
      </div>
      {albums.length > 1 && (
        <section className="music-section"><div className="grid">{albums.map((a) => <Card key={a.id} it={a} square />)}</div></section>
      )}
      <section className="music-section"><Tracks lib={lib} tracks={tracks} showAlbum={it.kind === "artist"} onPlay={(i) => play(i)} /></section>
    </div>
  );
}

function Tracks({ lib, tracks, showAlbum, numbered, onPlay }: {
  lib: Library; tracks: Track[]; showAlbum?: boolean; numbered?: boolean; onPlay: (i: number) => void;
}) {
  const m = useMusicState();
  const current = m.queue && m.index !== undefined ? m.queue[m.index] : null;
  const ready = tracks.filter((t) => here(lib, t.sid, t.id));
  return (
    <ol className="tracklist">
      {tracks.map((t, i) => {
        const ok = here(lib, t.sid, t.id);
        const on = current === `${t.sid}|${t.id}`;
        const own = rootOf(lib, t.sid, "item", t.id);
        return (
          <Fragment key={`${t.id}-${i}`}>
            <li className="track-row">
              <button className={`track ${on ? "on" : ""} ${ok ? "" : "gone"}`} disabled={!ok}
                title={ok ? undefined : "Still downloading"}
                onClick={() => (on ? musicCmd("toggle") : onPlay(ready.indexOf(t)))}>
                <span className="track-num"><span className="num">{numbered ? i + 1 : t.track_number ?? "·"}</span></span>
                <span className="track-text">
                  <span className="track-title">{t.title}</span>
                  {(showAlbum || t.artist !== t.album_artist) && (
                    <span className="muted track-sub">{[t.artist !== t.album_artist ? t.artist : null, showAlbum ? t.album : null].filter(Boolean).join(" · ")}</span>
                  )}
                </span>
                <span className="track-time">{fmtClock(t.duration)}</span>
              </button>
              {own && <RemoveButton small root={own} />}
            </li>
          </Fragment>
        );
      })}
    </ol>
  );
}

export function PlaylistPage() {
  const { sid = "", ref = "" } = useParams();
  const { lib } = useLib();
  const [err, setErr] = useState<string | null>(null);
  if (!lib) return <div className="page muted">Loading…</div>;
  const p = lib.playlists.find((x) => x.sid === sid && x.ref === ref);
  if (!p) return <div className="page"><h1>Not on this phone</h1><p className="muted">It was removed from your downloads.</p></div>;
  const root = rootOf(lib, sid, ref.split(":")[0] as RootKind, p.id);
  const ready = p.tracks.filter((t) => here(lib, t.sid, t.id));
  const play = (i: number, shuffle = false) => playTracks(ready, i, shuffle).catch((e) => setErr(e.message));
  return (
    <div className="detail music-detail">
      <div className="detail-body music-head">
        <div className="music-art"><Mosaic covers={p.covers} name={p.name} /></div>
        <div className="detail-info">
          <div className="hero-kicker">{p.own ? "Your playlist" : "Playlist"}</div>
          <h1>{p.name}</h1>
          <div className="meta"><span>{plural(p.tracks.length, "track")}</span>{p.duration ? <span>{fmtLength(p.duration)}</span> : null}</div>
          {p.description && <p className="overview">{p.description}</p>}
          <div className="actions">
            <button className="btn primary" onClick={() => play(0)} disabled={!ready.length}><Icon name="play" /> Play</button>
            <button className="btn ghost" onClick={() => play(0, true)} disabled={!ready.length}><Icon name="shuffle" /> Shuffle</button>
            {root && <RemoveButton root={root} />}
          </div>
          {err && <p className="key-msg bad">{err}</p>}
        </div>
      </div>
      <section className="music-section"><Tracks lib={lib} tracks={p.tracks} showAlbum numbered onPlay={(i) => play(i)} /></section>
    </div>
  );
}

type ServerRow = { id: string; name: string; addresses: string[]; online: string | null };

/** The app's servers: open one, add one (or another address of one), remove one. */
export function ServersPage() {
  const [list, setList] = useState<ServerRow[] | null>(null);
  const [address, setAddress] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const load = (check = true) => app<{ servers: ServerRow[] }>("servers", { check }).then((r) => setList(r.servers)).catch(() => setList([]));
  useEffect(() => { load(); }, []);

  const add = (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    setBusy("add");
    app("addServer", { address }).catch((x) => { setErr(x.message); setBusy(null); });  // on success the app opens it
  };
  const open = (s: ServerRow) => {
    setErr(null);
    setBusy(s.id);
    app("openServer", { id: s.id }).catch((x) => { setErr(x.message); setBusy(null); load(); });
  };

  return (
    <div className="page narrow">
      <div className="page-head"><h1>Servers</h1></div>
      <section className="lib-card settings-card">
        <div className="lib-head"><h3>Add a server</h3></div>
        <p className="muted">Type your BAMS server's address, as you'd open it in a browser: <code>192.168.1.5</code>,
          <code>192.168.1.5:8484</code> or <code>https://media.example.com</code>. To use a server away from home too,
          add its other address here as well: the app sees it's the same server and tries each address in turn.</p>
        <form className="key-row" onSubmit={add}>
          <input className="text-input" placeholder="Server address" value={address} onChange={(e) => setAddress(e.target.value)}
            autoCapitalize="off" autoCorrect="off" spellCheck={false} inputMode="url" aria-label="Server address" />
          <button className="btn small primary" disabled={!address.trim() || busy === "add"}>{busy === "add" ? "Connecting…" : "Connect"}</button>
        </form>
        {err && <p className="key-msg bad">{err}</p>}
      </section>
      <div className="section-head"><h2 className="section-title">Your servers</h2>
        <button className="btn ghost small" onClick={() => { setList(null); load(); }}><Icon name="refresh" size={16} /> Look again</button>
      </div>
      {!list && <p className="muted">Looking for them…</p>}
      {list && !list.length && <p className="muted">None yet.</p>}
      <div className="lib-list">
        {list?.map((s) => (
          <section key={s.id} className="lib-card settings-card">
            <div className="lib-head">
              <h3>{s.name}</h3>
              <span className={`status-pill ${s.online ? "ok" : "warn"}`}>{s.online ? "Reachable" : "Out of reach"}</span>
            </div>
            <ul className="phone-addresses">
              {s.addresses.map((a) => (
                <li key={a}>
                  <code>{a}</code>{s.online === a && <span className="muted"> · answering</span>}
                  {s.addresses.length > 1 && (
                    <button className="icon-btn subtle" aria-label={`Remove the address ${a}`} title="Forget this address"
                      onClick={() => app("removeAddress", { id: s.id, address: a }).then(() => load(false))}><Icon name="close" size={14} /></button>
                  )}
                </li>
              ))}
            </ul>
            <div className="key-row">
              <button className="btn small primary" disabled={!s.online || busy === s.id} onClick={() => open(s)}>
                {busy === s.id ? "Opening…" : "Open"}
              </button>
              {removing === s.id ? (
                <span className="confirm">
                  Forget {s.name}? Its downloads stay on the phone.
                  <button className="btn ghost small danger" onClick={() => app("removeServer", { id: s.id }).then(() => { setRemoving(null); load(false); })}>Forget</button>
                  <button className="btn ghost small" onClick={() => setRemoving(null)}>Cancel</button>
                </span>
              ) : <button className="btn small ghost" onClick={() => setRemoving(s.id)}>Forget server</button>}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
