import type Hls from "hls.js"; // loaded on demand (it's most of the bundle), only when a video is converted
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError, type ItemDetail, type Probe } from "../api";
import Icon from "../components/Icon";
import { PLAY_LABEL, sxe } from "../format";
import { useApi } from "../useApi";

// Three ways a file reaches <video>, chosen by the server (file.playback.mode):
//  "file"      - the original bytes with HTTP Range; the browser seeks by itself.
//  "remux"     - FFmpeg copies the video and converts unsupported audio (AC3/EAC3/DTS...) to AAC.
//                It's a live stream, so seeking restarts it at ?t=; `offset` is where that stream
//                really starts (asked from /seek), and the clock shows offset + currentTime.
//  "transcode" - FFmpeg converts the video to H.264 (and the audio to AAC). Normally over HLS
//                (POST playback.hls_url -> a playlist of 4 s segments made on demand; hls.js, or Safari
//                natively), so the browser seeks by itself. Browsers with neither get the plain fMP4
//                stream (playback.transcode_url?t=), live like the remux but starting exactly at t.
// The server can't know what this browser decodes, so HEVC/AV1/VP9 arrive as "file"/"remux". The
// player converts when the browser says it can't decode them, when it fails to, or when the viewer
// picks a lower quality.
type Mode = "file" | "remux" | "transcode";

const QUALITIES = [2160, 1440, 1080, 720, 480, 360];
const QUALITY_KEY = "bams.quality";

/** Whether this browser says it decodes the file's video. Only asked for codecs the server passes through. */
function canDecode(v: Probe["video"] | undefined): boolean {
  if (!v) return true;
  const ten = v.bit_depth === 10;
  const type = ({
    HEVC: `video/mp4; codecs="${ten ? "hvc1.2.4.L123.B0" : "hvc1.1.6.L123.B0"}"`,
    AV1: `video/mp4; codecs="av01.0.08M.${ten ? "10" : "08"}"`,
    VP9: `video/mp4; codecs="vp09.${ten ? "02" : "00"}.40.${ten ? "10" : "08"}"`,
    VP8: `video/webm; codecs="vp8"`,
  } as Record<string, string>)[v.codec];
  if (!type) return true;
  const supported = (t: string) => "MediaSource" in window
    ? MediaSource.isTypeSupported(t)  // iOS Safari has no MediaSource
    : document.createElement("video").canPlayType(t) !== "";
  // Dolby Vision profile 5 has no HDR10 base layer: without DV support it decodes but shows green/purple
  if (v.hdr === "Dolby Vision" && v.dv_profile === 5 && !supported(`video/mp4; codecs="dvh1.05.06"`)) return false;
  return supported(type);
}

const nativeHls = () => document.createElement("video").canPlayType("application/vnd.apple.mpegurl") !== "";
/** What hls.js needs (its own isSupported(), without loading it first): Media Source Extensions with H.264 + AAC. */
const mseHls = () => "MediaSource" in window && MediaSource.isTypeSupported('video/mp4; codecs="avc1.640028,mp4a.40.2"');

function storedQuality(): number | null {
  try {
    return Number(localStorage.getItem(QUALITY_KEY)) || null;
  } catch {
    return null;
  }
}

/** Close an HLS session (FFmpeg stops, segments are deleted). keepalive: also works while the page unloads. */
function closeSession(id: string) {
  fetch(`/api/hls/${id}`, { method: "DELETE", keepalive: true }).catch(() => {});
}

export default function Player() {
  const { id } = useParams();
  const nav = useNavigate();
  const { data: item, error } = useApi<ItemDetail>(`/api/items/${id}`);
  const video = useRef<HTMLVideoElement>(null);
  const shell = useRef<HTMLDivElement>(null);
  const [t, setT] = useState(0);             // video.currentTime
  const [fileDur, setFileDur] = useState(0); // duration as the browser reports it (file and HLS)
  const [offset, setOffset] = useState(0);   // live modes: media time the current stream starts at
  const [reqT, setReqT] = useState(0);       // live modes: ?t= the stream was requested with
  const startAt = useRef(0);                 // where the next HLS session / file starts (stream switches)
  const [seeking, setSeeking] = useState(false);
  const [scrub, setScrub] = useState<number | null>(null); // timeline being dragged (live modes)
  const [fallback, setFallback] = useState(false); // switched to the transcode after the browser failed to decode
  const [quality, setQuality] = useState<number | null>(storedQuality); // max height; null = original
  const [menu, setMenu] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [idle, setIdle] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const idleTimer = useRef<number | undefined>(undefined);

  const file = item?.files.find((f) => f.available) ?? item?.files[0];
  const show = item?.ancestors.find((a) => a.kind === "show");
  const pb = file?.playback;
  const decodable = useMemo(() => canDecode(file?.probe?.video), [file]);
  const srcHeight = file?.probe?.video?.height ?? 0;
  const canConvert = !!(pb?.hls_url || pb?.transcode_url);
  const qualities = canConvert ? QUALITIES.filter((h) => h < srcHeight) : [];
  const height = quality && qualities.includes(quality) ? quality : null; // a remembered 720p means nothing for a 480p file
  const mustConvert = !!pb && (pb.mode === "transcode" || fallback || !decodable);
  const mode: Mode = !pb ? "file" : canConvert && (mustConvert || height) ? "transcode" : pb.mode;
  const useHls = mode === "transcode" && !!pb?.hls_url && !!file?.probe?.duration && (mseHls() || nativeHls());
  const live = mode === "remux" || (mode === "transcode" && !useHls); // a stream FFmpeg makes from ?t=
  const url = mode === "transcode" ? (pb?.transcode_url ?? pb?.url) : pb?.url;
  const total = live ? (pb?.duration ?? file?.probe?.duration ?? 0) : (fileDur || file?.probe?.duration || 0);
  const pos = live ? offset + t : t;
  const src = useHls ? undefined : url && (live ? `${url}?t=${reqT}${height ? `&h=${height}` : ""}` : url);

  // HLS: one server session per (file, quality). hls.js (or Safari) asks for segments as it plays/seeks.
  useEffect(() => {
    const v = video.current;
    if (!useHls || !file?.playback.hls_url || !v) return;
    let hls: Hls | null = null;
    let sid: string | null = null;
    let gone = false;
    const unload = () => { if (sid) closeSession(sid); };
    window.addEventListener("pagehide", unload);
    setProblem(null);
    const withMse = mseHls();
    Promise.all([api.post<{ id: string; playlist: string }>(file.playback.hls_url, { height }),
                 withMse ? import("hls.js").then((m) => m.default) : null])
      .then(([s, HlsJs]) => {
        if (gone) return closeSession(s.id);
        sid = s.id;
        const at = startAt.current;
        if (HlsJs) {
          hls = new HlsJs({ startPosition: at });
          hls.on(HlsJs.Events.ERROR, (_e, d) => {
            if (!d.fatal) return;
            const code = d.response?.code;
            setProblem(code === 503
              ? "The server is converting as many videos as it's allowed to at once (Settings). Try again in a moment."
              : "The converted stream stopped (the server log has the FFmpeg error). You can download the file instead.");
          });
          hls.loadSource(s.playlist);
          hls.attachMedia(v);
        } else {  // Safari: native HLS
          v.src = s.playlist;
          v.addEventListener("loadedmetadata", () => { if (at) v.currentTime = at; }, { once: true });
        }
      })
      .catch((e) => setProblem(e instanceof ApiError ? e.message : "Couldn't start converting this video."));
    return () => {
      gone = true;
      window.removeEventListener("pagehide", unload);
      hls?.destroy();
      unload();
    };
  }, [useHls, file?.id, height]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = () => {
    const v = video.current;
    if (!v) return;
    if (v.paused) v.play().catch(() => {});
    else v.pause();
  };
  const seek = async (s: number) => {
    const target = Math.max(0, Math.min(total || Infinity, s));
    if (!live) {
      if (video.current) video.current.currentTime = target;
      return;
    }
    if (!file) return;
    if (mode === "transcode") {  // re-encoded: the new stream starts exactly at target
      setOffset(target);
      setT(0);
      setReqT(Number(target.toFixed(2)));
      return;
    }
    setSeeking(true);
    try {
      const { t: start } = await api.get<{ t: number }>(`/api/files/${file.id}/seek?t=${target.toFixed(2)}`);
      setOffset(start);
    } catch {
      setOffset(target);
    }
    setT(0);
    setReqT(Number(target.toFixed(2)));  // new src -> the server starts a fresh stream there
    setSeeking(false);
  };
  /** The next stream (another mode, quality or HLS session) carries on from `at`. */
  const continueAt = (at: number) => {
    startAt.current = at;
    setOffset(at);
    setReqT(Number(at.toFixed(2)));
    setT(0);
    setProblem(null);
  };
  /** The browser can't decode this video after all: carry on from here with the server's H.264 version. */
  const toTranscode = (why: string) => {
    if (mode === "transcode" || !canConvert) return setProblem(why);
    continueAt(pos);
    setFallback(true);
  };
  const pickQuality = (h: number | null) => {
    setMenu(false);
    if (h === height) return;
    continueAt(pos);
    setQuality(h);
    try {
      if (h) localStorage.setItem(QUALITY_KEY, String(h));
      else localStorage.removeItem(QUALITY_KEY);
    } catch { /* private mode: not remembered */ }
  };
  const fullscreen = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else shell.current?.requestFullscreen?.();
  };

  // Key handler is registered once; read the latest position/seek through refs.
  const posRef = useRef(0);
  const seekRef = useRef(seek);
  posRef.current = pos;
  seekRef.current = seek;

  useEffect(() => {
    const wake = () => {
      setIdle(false);
      clearTimeout(idleTimer.current);
      idleTimer.current = window.setTimeout(() => setIdle(true), 3000);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === " " || e.key === "k") { e.preventDefault(); toggle(); }
      if (e.key === "Escape" && !document.fullscreenElement) nav(-1);
      if (e.key === "ArrowRight") seekRef.current(posRef.current + 10);
      if (e.key === "ArrowLeft") seekRef.current(posRef.current - 10);
      if (e.key === "f") fullscreen();
      if (e.key === "m" && video.current) { video.current.muted = !video.current.muted; setMuted(video.current.muted); }
      wake();
    };
    wake();
    window.addEventListener("mousemove", wake);
    window.addEventListener("keydown", key);
    return () => { window.removeEventListener("mousemove", wake); window.removeEventListener("keydown", key); };
  }, [nav]);

  if (error) return <div className="player"><div className="player-msg"><p>{error}</p></div></div>;
  if (!item) return <div className="player" />;

  const title = show ? show.title : item.title;
  const subtitle = item.kind === "episode" ? `${sxe(item.season_number!, item.episode_number!)} · ${item.title}` : item.year ?? "";
  const fmt = (sec: number) => {
    const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), ss = Math.floor(sec % 60);
    return `${h ? `${h}:` : ""}${String(m).padStart(h ? 2 : 1, "0")}:${String(ss).padStart(2, "0")}`;
  };
  const vcodec = pb?.video_codec ?? "Video";
  const note = mode === "remux" ? { text: `${pb?.audio_codec} → AAC`, why: `${pb?.audio_codec} audio converted to AAC by the server` }
    : mode !== "transcode" ? null
    : mustConvert ? { text: `${vcodec} → H.264${height ? ` ${height}p` : ""}`, why: `This browser can't decode ${vcodec} video, so the server converts it to H.264 while streaming` }
    : { text: `${height}p (converted)`, why: "Converted to a smaller size by the server (quality menu)" };

  return (
    <div ref={shell} className={`player ${idle && playing && !menu ? "idle" : ""}`}>
      {file ? (
        <video
          // a new element per stream kind: hls.js detaching must not wipe the next stream's src
          key={useHls ? `hls-${height ?? "full"}` : "direct"}
          ref={video}
          className="player-video"
          src={src}
          autoPlay
          playsInline
          onClick={toggle}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onTimeUpdate={(e) => setT(e.currentTarget.currentTime)}
          onDurationChange={(e) => !live && setFileDur(e.currentTarget.duration)}
          onLoadedMetadata={(e) => {
            const v = e.currentTarget;
            if (v.videoWidth === 0)
              toTranscode(`This browser can play the sound but not the ${pb?.video_codec ?? ""} video of this file, and the server can't convert it (no FFmpeg). You can download it.`);
            else if (mode === "file" && startAt.current) {  // back to the original file mid-way (quality menu)
              v.currentTime = startAt.current;
              startAt.current = 0;
            }
          }}
          onError={() => !useHls && toTranscode(mode === "transcode"
            ? "The server couldn't convert this file (its log has the FFmpeg error). You can download it instead."
            : `This browser can't play this file (${pb?.video_codec ?? "unknown codec"}), and the server can't convert it (no FFmpeg). You can download it.`)}
        />
      ) : (
        <div className="player-msg"><p>No playable file for this item.</p></div>
      )}

      {problem && file && (
        <div className="player-msg">
          <p>{problem}</p>
          <a className="btn ghost" href={file.download_url} download><Icon name="download" /> Download</a>
        </div>
      )}
      {seeking && <div className="player-msg subtle"><p>Seeking…</p></div>}
      {!playing && !problem && !seeking && file && (
        <button className="player-center" onClick={toggle} aria-label="Play">
          <span className="round-btn big"><Icon name="play" size={40} /></span>
        </button>
      )}

      <div className="player-top">
        <button className="icon-btn" onClick={() => nav(-1)} aria-label="Back"><Icon name="back" size={28} /></button>
        <div>
          <div className="player-title">{title}</div>
          {subtitle && <div className="muted">{subtitle}</div>}
        </div>
        {file && (
          <div className="player-stream" title={PLAY_LABEL[file.playback.method]}>
            {[file.probe?.video?.codec ?? file.playback.video_codec, file.probe?.video?.resolution ?? file.release?.resolution]
              .filter(Boolean).join(" · ")}
          </div>
        )}
      </div>

      <div className="player-bottom">
        <input
          className="timeline"
          type="range" min={0} max={total || 0} step={1} value={scrub ?? pos}
          // file/HLS seek while dragging; live modes restart the stream once, on release
          onChange={(e) => { const v = Number(e.target.value); if (live) setScrub(v); else seek(v); }}
          onPointerUp={() => { if (scrub !== null) { seek(scrub); setScrub(null); } }}
          onKeyUp={() => { if (scrub !== null) { seek(scrub); setScrub(null); } }}
          style={{ ["--pct" as string]: `${total ? ((scrub ?? pos) / total) * 100 : 0}%` }}
          aria-label="Seek"
        />
        <div className="player-controls">
          <button className="icon-btn" onClick={toggle} aria-label={playing ? "Pause" : "Play"}>
            <Icon name={playing ? "pause" : "play"} size={28} />
          </button>
          <button className="icon-btn" onClick={() => seek(pos - 10)} aria-label="Back 10 seconds"><Icon name="chevronLeft" size={24} /></button>
          <button className="icon-btn" onClick={() => seek(pos + 10)} aria-label="Forward 10 seconds"><Icon name="chevronRight" size={24} /></button>
          <button className={`icon-btn ${muted ? "off" : ""}`} aria-label={muted ? "Unmute" : "Mute"}
            onClick={() => { if (video.current) { video.current.muted = !video.current.muted; setMuted(video.current.muted); } }}>
            <Icon name="volume" size={24} />
          </button>
          <span className="time">{fmt(scrub ?? pos)} / {fmt(total)}</span>
          {note && <span className="muted audio-note" title={note.why}>{note.text}</span>}
          <span className="spacer" />
          {qualities.length > 0 && (
            <div className="quality">
              <button className="quality-btn" onClick={() => setMenu(!menu)} aria-haspopup="menu" aria-expanded={menu}
                title="Quality">{height ? `${height}p` : "Original"}</button>
              {menu && (
                <div className="quality-menu" role="menu">
                  <button role="menuitemradio" aria-checked={!height} onClick={() => pickQuality(null)}>
                    Original <span className="muted">{mustConvert ? "converted" : "as-is"}</span>
                  </button>
                  {qualities.map((h) => (
                    <button key={h} role="menuitemradio" aria-checked={height === h} onClick={() => pickQuality(h)}>
                      {h}p <span className="muted">converted</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
          {file && <a className="icon-btn" href={file.download_url} download title="Download"><Icon name="download" size={22} /></a>}
          <button className="icon-btn" title="Fullscreen (f)" onClick={fullscreen}><Icon name="fullscreen" size={24} /></button>
        </div>
      </div>
    </div>
  );
}
