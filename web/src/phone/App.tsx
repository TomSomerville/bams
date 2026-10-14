import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Route, Routes } from "react-router-dom";
import { app, DOWNLOADS_CHANGED } from "../android";
import { Poster } from "../components/Art";
import Icon from "../components/Icon";
import { fmtClock } from "../format";
import { qualityLine } from "../quality";
import { build, ik, type Library, type Raw, type Track } from "./lib";
import { DownloadsPage, MoviesPage, MusicPage, PlaylistPage, ServersPage, ShowsPage, StartPage, TitlePage } from "./pages";

// The Android app's own pages: what's on the phone (playable with no connection), and the app's server list.
// Styled with the web UI's own stylesheet and parts, so they look like the rest of BAMS.

const LibCtx = createContext<{ lib: Library | null; reload: () => void }>({ lib: null, reload: () => {} });
export const useLib = () => useContext(LibCtx);

export type MusicState = {
  ready: boolean; playing?: boolean; index?: number; position?: number; duration?: number | null;
  shuffle?: boolean; queue?: string[];
};
const MusicCtx = createContext<MusicState>({ ready: false });
export const useMusicState = () => useContext(MusicCtx);

/** Play downloaded tracks with the app's music player (it plays on with the screen off). */
export function playTracks(tracks: Track[], index = 0, shuffle = false) {
  const original = (u: string | null) => u?.replace(/^\/dl\/[^/]+\/images\//, "/api/images/") ?? null;
  return app("musicPlay", {
    tracks: tracks.map((t) => ({ sid: t.sid, id: t.id, file: t.file_id, title: t.title, artist: t.artist, album: t.album,
      poster: original(t.poster), start: t.start, end: t.end })),
    index, shuffle,
  });
}

export const musicCmd = (cmd: string, value?: number) => app("musicCmd", value === undefined ? { cmd } : { cmd, value });

type ServerRow = { id: string; name: string; addresses: string[]; online: string | null };

/** Offline: which server stopped answering; online again: a way back to it. */
function Banner() {
  const [lost, setLost] = useState<string | null>(null);
  const [online, setOnline] = useState<ServerRow[]>([]);
  const [busy, setBusy] = useState(false);
  const look = useCallback((check: boolean) => {
    app<{ servers: ServerRow[] }>("servers", { check }).then((r) => setOnline(r.servers.filter((s) => s.online))).catch(() => {});
  }, []);
  useEffect(() => {
    app<{ lost: string } | null>("current").then((c) => setLost(c?.lost ?? null)).catch(() => {});
    look(true);
    const again = () => look(true);
    const t = window.setInterval(again, 30_000);
    window.addEventListener("bams:network", again);
    return () => { window.clearInterval(t); window.removeEventListener("bams:network", again); };
  }, [look]);
  const open = (s: ServerRow) => {
    setBusy(true);
    app("openServer", { id: s.id }).catch(() => { setBusy(false); look(true); });
  };
  if (online.length) {
    const s = online[0];
    return (
      <button className="config-banner phone-banner online" onClick={() => open(s)} disabled={busy}>
        <Icon name="server" size={18} />
        <span><strong>{s.name}</strong> can be reached.</span>
        <span className="config-banner-cta">{busy ? "Opening…" : "Go online"} <Icon name="chevronRight" size={16} /></span>
      </button>
    );
  }
  return (
    <div className="config-banner phone-banner" role="status">
      <Icon name="alert" size={18} />
      <span>{lost ? <>Can't reach <strong>{lost}</strong>. </> : "No server in reach. "}Your downloads play from this phone.</span>
    </div>
  );
}

function NowPlaying() {
  const m = useMusicState();
  const { lib } = useLib();
  if (!m.ready || !m.queue?.length || m.index === undefined || !lib) return null;
  const [sid, id] = (m.queue[m.index] ?? "").split("|");
  const t = lib.tracks.get(ik(sid, Number(id)));
  if (!t) return null;
  const dur = m.duration ?? t.duration ?? 0;
  const pos = m.position ?? 0;
  const pct = dur ? Math.min(100, (pos / dur) * 100) : 0;
  return (
    <div className="now-playing" role="region" aria-label="Now playing">
      <div className="np-track">
        <Link to={`/t/${sid}/${t.album_id}`} className="np-cover"><Poster src={t.poster} title={t.album} /></Link>
        <div className="np-text">
          <Link to={`/t/${sid}/${t.album_id}`} className="np-title">{t.title}</Link>
          <Link to={`/t/${sid}/${t.artist_id}`} className="np-artist muted">{t.artist}</Link>
          {/* downloaded files play as they are: the file's own quality */}
          {qualityLine({ ...t.playback, mode: "file" }) && <span className="np-quality">{qualityLine({ ...t.playback, mode: "file" })}</span>}
        </div>
      </div>
      <div className="np-center">
        <div className="np-buttons">
          <button className="icon-btn" onClick={() => musicCmd("prev")} aria-label="Previous"><Icon name="skipBack" size={20} /></button>
          <button className="icon-btn np-play" onClick={() => musicCmd("toggle")} aria-label={m.playing ? "Pause" : "Play"}>
            <Icon name={m.playing ? "pause" : "play"} size={22} />
          </button>
          <button className="icon-btn" onClick={() => musicCmd("next")} disabled={m.index + 1 >= m.queue.length && !m.shuffle} aria-label="Next">
            <Icon name="skipForward" size={20} />
          </button>
        </div>
        <div className="np-seek">
          <span className="time">{fmtClock(pos)}</span>
          <input type="range" className="timeline" min={0} max={dur || 1} step={0.5} value={Math.min(pos, dur || 1)}
            style={{ ["--pct" as string]: `${pct}%` }} onChange={(e) => musicCmd("seek", Number(e.target.value))} aria-label="Seek" />
          <span className="time">{fmtClock(dur)}</span>
        </div>
      </div>
      <div className="np-right">
        <button className={`icon-btn ${m.shuffle ? "active" : ""}`} onClick={() => musicCmd("shuffle")} aria-label="Shuffle">
          <Icon name="shuffle" size={18} />
        </button>
        <button className="icon-btn" onClick={() => musicCmd("stop")} aria-label="Stop and clear the queue"><Icon name="close" size={18} /></button>
      </div>
    </div>
  );
}

function Shell({ children }: { children: ReactNode }) {
  const m = useMusicState();
  const base = import.meta.env.BASE_URL;
  return (
    <div className={`shell ${m.ready && m.queue?.length ? "has-np" : ""}`}>
      <nav className="sidebar">
        <NavLink to="/downloads" className="brand" aria-label="Downloads">
          <img src={`${base}brand/bams-wordmark.png`} alt="BAMS — Bad Ass Media Server" />
        </NavLink>
        <NavLink to="/downloads" className="brand-icon" aria-label="Downloads"><img src={`${base}brand/bams-icon.png`} alt="" /></NavLink>
        <div className="nav-group">
          <NavLink to="/downloads" className="nav-item"><Icon name="download" /> <span>Downloads</span></NavLink>
          <div className="nav-label nav-server"><span>On this phone</span></div>
          <NavLink to="/movies" className="nav-item"><Icon name="film" /> <span>Movies</span></NavLink>
          <NavLink to="/shows" className="nav-item"><Icon name="tv" /> <span>TV Shows</span></NavLink>
          <NavLink to="/music" className="nav-item"><Icon name="music" /> <span>Music</span></NavLink>
        </div>
        <div className="nav-group bottom">
          <NavLink to="/servers" className="nav-item"><Icon name="server" /> <span>Servers</span></NavLink>
        </div>
      </nav>
      <div className="main">
        <Banner />
        {children}
      </div>
      <NowPlaying />
    </div>
  );
}

export default function App() {
  const [lib, setLib] = useState<Library | null>(null);
  const [music, setMusic] = useState<MusicState>({ ready: false });
  const reload = useCallback(() => {
    app<Raw>("library").then((r) => setLib(build(r))).catch(() => {});
  }, []);
  useEffect(() => {
    reload();
    app<MusicState>("musicState").then(setMusic).catch(() => {});
    const onMusic = (e: Event) => setMusic((e as CustomEvent<MusicState>).detail);
    window.addEventListener(DOWNLOADS_CHANGED, reload);
    window.addEventListener("bams:progress", reload);
    window.addEventListener("bams:music", onMusic);
    return () => {
      window.removeEventListener(DOWNLOADS_CHANGED, reload);
      window.removeEventListener("bams:progress", reload);
      window.removeEventListener("bams:music", onMusic);
    };
  }, [reload]);

  return (
    <LibCtx.Provider value={{ lib, reload }}>
      <MusicCtx.Provider value={music}>
        <Routes>
          <Route path="/start" element={<StartPage />} />
          <Route path="*" element={
            <Shell>
              <Routes>
                <Route path="/movies" element={<MoviesPage />} />
                <Route path="/shows" element={<ShowsPage />} />
                <Route path="/music" element={<MusicPage />} />
                <Route path="/t/:sid/:id" element={<TitlePage />} />
                <Route path="/p/:sid/:ref" element={<PlaylistPage />} />
                <Route path="/servers" element={<ServersPage />} />
                <Route path="*" element={<DownloadsPage />} />
              </Routes>
            </Shell>
          } />
        </Routes>
      </MusicCtx.Provider>
    </LibCtx.Provider>
  );
}
