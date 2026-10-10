import type Hls from "hls.js"; // loaded on demand (it's most of the bundle), only when a video goes over HLS
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ApiError, type ItemDetail, type Probe } from "../api";
import Icon from "../components/Icon";
import { fmtClock, PLAY_LABEL, sxe } from "../format";
import { useScope, type Call } from "../servers";
import { useApi } from "../useApi";

// Three ways a file reaches <video>, chosen by the server (file.playback.mode) and the viewer's choices:
//  "file"      - the original bytes with HTTP Range; the browser seeks by itself.
//  "remux"     - the video copied, the audio converted to AAC: for AC3/EAC3/DTS... audio, or another audio track
//                than the first (a browser plays only the first). Over HLS (POST hls_url {remux}: segments cut
//                at the file's keyframes), so the browser seeks by itself; if that isn't possible, the live
//                stream /remux?t=, which restarts to seek (`offset` = where it really starts, from /seek).
//  "transcode" - FFmpeg converts the video to H.264 too: video no browser decodes, a smaller quality, "Auto"
//                quality (several sizes, hls.js picks), or picture subtitles burned in. Over HLS, else the
//                live fMP4 stream /transcode?t= (starts exactly at t).
// The server can't know what this browser decodes, so HEVC/AV1/VP9 arrive as "file"/"remux". The player
// converts when the browser says it can't decode them, or when it fails to. Likewise Dolby audio: on a device
// that decodes AC3/EAC3 itself (TV browsers, Safari, Edge, Chromecast...) the remux copies it as it is
// ("pass-through", so an AV receiver gets the original), unless the viewer turns that off or it fails to play.
type Mode = "file" | "remux" | "transcode";
/** null = the default: the original when it plays as-is, else automatic */
type Quality = "auto" | number | null;

const QUALITIES = [2160, 1440, 1080, 720, 480, 360];
const FULL = 99999;  // "Full size": converted (the browser can't play the original) at the largest size
const SPEED_MIN = 0.1, SPEED_MAX = 3;
const SKIP_FORWARD = 30, SKIP_BACK = 10;  // seconds (buttons and arrow keys)
const CREDITS = 30;  // the up-next countdown starts this long before an episode ends (the credits)
const SUB_STEP = 100;  // ms: one press of the subtitle timing buttons (and the g / h keys)
const clampSpeed = (r: number) => Math.round(Math.min(SPEED_MAX, Math.max(SPEED_MIN, r)) * 100) / 100;
const KEYS = { quality: "bams.quality", audioLang: "bams.audioLang", subLang: "bams.subLang", surround: "bams.surround",
               passthrough: "bams.passthrough" };

function pref(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function setPref(key: string, v: string | null) {
  try {
    if (v === null) localStorage.removeItem(key);
    else localStorage.setItem(key, v);
  } catch { /* private mode: not remembered */ }
}

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

/** Dolby audio the server can pass through (stream.PASSTHROUGH_AUDIO), as MP4 codec strings. */
const PASS_TYPES: Record<string, string> = { AC3: 'audio/mp4; codecs="ac-3"', EAC3: 'audio/mp4; codecs="ec-3"' };
/** Whether this device says it decodes the audio codec itself, so it needn't be converted to AAC. */
function canPassThrough(codec: string | null | undefined): boolean {
  const type = codec ? PASS_TYPES[codec] : undefined;
  if (!type) return false;
  return "MediaSource" in window ? MediaSource.isTypeSupported(type)
    : document.createElement("video").canPlayType(type) !== "";
}

const nativeHls = () => document.createElement("video").canPlayType("application/vnd.apple.mpegurl") !== "";
/** What hls.js needs (its own isSupported(), without loading it first): Media Source Extensions with H.264 + AAC. */
const mseHls = () => "MediaSource" in window && MediaSource.isTypeSupported('video/mp4; codecs="avc1.640028,mp4a.40.2"');

function storedQuality(): Quality {
  const q = pref(KEYS.quality);
  return q === "auto" ? "auto" : Number(q) || null;
}

/** Close an HLS session (FFmpeg stops, segments are deleted). keepalive: also works while the page unloads.
 *  `playlist` is the session's playlist URL and `call` its server's (this one or another, servers.tsx). */
function closeSession(call: Call, playlist: string) {
  call.send("DELETE", playlist.replace(/\/index\.m3u8$/, ""), undefined, true).catch(() => {});
}

/** A pop-up list of choices in the control bar (quality, sound, subtitles). */
function Menu({ label, title, open, setOpen, children }: {
  label: ReactNode; title: string; open: boolean; setOpen: (o: boolean) => void; children: ReactNode;
}) {
  return (
    <div className="quality">
      <button className="quality-btn" onClick={() => setOpen(!open)} aria-haspopup="menu" aria-expanded={open}
        title={title}>{label}</button>
      {open && <div className="quality-menu" role="menu"><div className="menu-title">{title}</div>{children}</div>}
    </div>
  );
}

function Choice({ on, onClick, children, note }: { on: boolean; onClick: () => void; children: ReactNode; note?: string }) {
  return (
    <button role="menuitemradio" aria-checked={on} onClick={onClick}>
      <span>{children}</span>{note && <span className="muted">{note}</span>}
    </button>
  );
}

/** /play/:id. Keyed by id, so going on to the next episode starts a fresh player. */
export default function PlayerPage() {
  const { id } = useParams();
  return <Player key={id} id={id!} />;
}

function Player({ id }: { id: string }) {
  const nav = useNavigate();
  const { call, media, to, rid } = useScope();  // this server, or another one (/r/:rid/play/:id)
  const [search] = useSearchParams();
  const { data: item, error } = useApi<ItemDetail>(`/api/items/${id}`);
  const video = useRef<HTMLVideoElement>(null);
  const shell = useRef<HTMLDivElement>(null);
  const [t, setT] = useState(0);             // video.currentTime
  const [fileDur, setFileDur] = useState(0); // duration as the browser reports it (file and HLS)
  const [offset, setOffset] = useState(0);   // live modes: media time the current stream starts at
  const [reqT, setReqT] = useState(0);       // live modes: ?t= the stream was requested with
  const startAt = useRef(0);                 // where the next HLS session / file starts (resume, stream switches)
  const [ready, setReady] = useState(false); // the start position is decided: streams may begin
  const [scrub, setScrub] = useState<number | null>(null); // timeline being dragged (live modes)
  const [fallback, setFallback] = useState(false); // switched to the transcode after the browser failed to decode
  const [copyFailed, setCopyFailed] = useState(false); // remux over HLS didn't work: use the live remux
  const [quality, setQuality] = useState<Quality>(storedQuality);
  const [audio, setAudio] = useState(0);
  const [sub, setSub] = useState<string | null>(null);
  const [surround, setSurround] = useState(() => pref(KEYS.surround) === "1");
  const [passPref, setPassPref] = useState(() => pref(KEYS.passthrough) !== "0"); // on unless turned off
  const [passFailed, setPassFailed] = useState(false); // the device said it decodes Dolby, then didn't
  const [menu, setMenu] = useState<"quality" | "audio" | "subs" | "speed" | null>(null);
  const [rate, setRate] = useState(1);      // playback speed; each video starts at normal speed
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [idle, setIdle] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [resumed, setResumed] = useState<number | null>(null); // "Resumed from 12:34" note
  const [upNext, setUpNext] = useState<number | null>(null);   // seconds until the next episode starts
  const idleTimer = useRef<number | undefined>(undefined);
  const played = useRef(false);  // playback really got going (only then is the position worth saving)
  const finished = useRef(false); // left for the next episode from the credits: counts as watched to the end
  const skipCredits = useRef(false); // the viewer cancelled the credits' up-next: not again this viewing
  // Play on by ourselves (a new episode, a new stream) unless the viewer paused. The autoplay attribute alone isn't
  // enough: some browsers (Safari, iOS, strict Firefox settings) refuse sound without a fresh tap on this element.
  const wantPlay = useRef(true);
  const [soundBlocked, setSoundBlocked] = useState(false); // playing muted because the browser refused sound
  const [subDelay, setSubDelay] = useState(0);  // ms the text subtitles are moved by (+ later, - earlier)
  const [trackEl, setTrackEl] = useState<HTMLTrackElement | null>(null);
  const [cuesLoaded, setCuesLoaded] = useState(0);
  const cueTimes = useRef(new WeakMap<TextTrackCue, [number, number]>()); // each cue's own times, before the delay

  const file = item?.files.find((f) => f.available) ?? item?.files[0];
  const show = item?.ancestors.find((a) => a.kind === "show");
  const pb = file?.playback;
  const audioTracks = file?.audio_tracks ?? [];
  const subTracks = file?.subtitles ?? [];
  const subTrack = subTracks.find((s) => s.id === sub) ?? null;
  const burn = subTrack?.image ? subTrack.id : null;  // painted on by the server: embedded or a VobSub sidecar
  const decodable = useMemo(() => canDecode(file?.probe?.video), [file]);
  const srcHeight = file?.probe?.video?.height ?? 0;
  const canConvert = !!(pb?.hls_url || pb?.transcode_url);  // only with FFmpeg on the server
  const qualities = canConvert ? QUALITIES.filter((h) => h < srcHeight) : [];
  const height = typeof quality === "number" && qualities.includes(quality) ? quality : null; // a remembered 720p means nothing for a 480p file
  const mustConvert = !!pb && (pb.mode === "transcode" || fallback || !decodable || burn !== null);
  const auto = height === null && (quality === "auto" || (quality === null && mustConvert));
  const mode: Mode = !pb ? "file"
    : canConvert && (mustConvert || height !== null || quality === "auto") ? "transcode"
    : canConvert && (pb.mode === "remux" || audio > 0) ? "remux"
    : pb.mode === "transcode" ? "file" : pb.mode;
  const channels = surround ? 6 : 2;
  const trackCodec = audioTracks[audio]?.codec ?? pb?.audio_codec;
  const passOk = useMemo(() => canPassThrough(trackCodec), [trackCodec]);
  const passthrough = mode === "remux" && passOk && passPref && !passFailed;
  const hlsOk = !!pb?.hls_url && !!file?.probe?.duration && (mseHls() || nativeHls());
  const useHls = hlsOk && (mode === "transcode" || (mode === "remux" && !copyFailed));
  const live = !useHls && (mode === "remux" || mode === "transcode"); // a stream FFmpeg makes from ?t=
  const total = live ? (pb?.duration ?? file?.probe?.duration ?? 0) : (fileDur || file?.probe?.duration || 0);
  // before anything played, an HLS stream is still at 0: where it's about to start is what counts (a stream
  // that fails then, e.g. the copy falling back to the live remux, must carry on from the resume point)
  const pos = live ? offset + t : t || (played.current ? 0 : startAt.current);
  const hlsKey = `${mode}|${auto}|${height}|${audio}|${channels}|${burn}|${passthrough}`;
  const liveParams = new URLSearchParams({ t: String(reqT) });
  if (audio) liveParams.set("audio", String(audio));
  if (channels > 2) liveParams.set("ch", String(channels));
  if (passthrough) liveParams.set("passthrough", "true");
  if (mode === "transcode" && height) liveParams.set("h", String(height));
  if (mode === "transcode" && burn !== null) liveParams.set("sub", burn);
  const liveUrl = mode === "transcode" ? pb?.transcode_url : file && media(`/api/files/${file.id}/remux`);
  const src = !ready || useHls || !pb ? undefined : live ? `${liveUrl}?${liveParams}` : pb.url;
  const watchable = item?.kind === "movie" || item?.kind === "episode";

  // Once the file is known: the remembered audio/subtitle languages, and where to start (resume).
  useEffect(() => {
    if (!item || !file) return;
    // the remembered language, else the browser's, else the track the file marks as default, else the first
    const lang = pref(KEYS.audioLang) ?? navigator.language.split("-")[0];
    const a = audioTracks.find((x) => x.language === lang) ?? audioTracks.find((x) => x.default);
    setAudio(a ? a.index : 0);
    const sl = pref(KEYS.subLang);  // text tracks only: a picture one would make the server convert the video
    const s = sl ? subTracks.find((x) => x.language === sl && !x.image && !x.forced) : undefined;
    setSub(s ? s.id : null);
    const p = item.progress;
    const at = search.get("start") === "0" || !p || p.watched || p.position < 30 ? 0 : p.position;
    startAt.current = at;
    setOffset(at);
    setReqT(Number(at.toFixed(2)));
    if (at) setResumed(at);
    setReady(true);
  }, [item?.id, file?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // The live remux can only start on a keyframe: ask where a stream requested at reqT really starts.
  useEffect(() => {
    if (!live || mode !== "remux" || !file || !reqT) return;
    let gone = false;
    call.get<{ t: number }>(`/api/files/${file.id}/seek?t=${reqT}`).then((r) => { if (!gone) setOffset(r.t); }).catch(() => {});
    return () => { gone = true; };
  }, [live, mode, file?.id, reqT]); // eslint-disable-line react-hooks/exhaustive-deps

  // HLS: one server session per stream choice. hls.js (or Safari) asks for segments as it plays/seeks.
  useEffect(() => {
    const v = video.current;
    if (!ready || !useHls || !file?.playback.hls_url || !v) return;
    let hls: Hls | null = null;
    let sid: string | null = null;  // the session's playlist URL
    let gone = false;
    const unload = () => { if (sid) closeSession(call, sid); };
    window.addEventListener("pagehide", unload);
    setProblem(null);
    const remux = mode === "remux";
    const withMse = mseHls();
    const body = { remux, auto: !remux && auto, height: remux ? null : height, audio, channels,
                   burn: remux ? null : burn, passthrough, start: startAt.current };
    const toLive = () => {  // copying didn't work out: the live remux, from here
      if (gone) return;
      continueAt(posRef.current);
      setCopyFailed(true);
    };
    const toAac = () => {  // the device didn't play the Dolby audio after all: converted, from here
      if (gone) return;
      continueAt(posRef.current);
      setPassFailed(true);
    };
    Promise.all([call.post<{ id: string; playlist: string }>(file.playback.hls_url, body),
                 withMse ? import("hls.js").then((m) => m.default) : null])
      .then(([s, HlsJs]) => {
        if (gone) return closeSession(call, s.playlist);
        sid = s.playlist;
        const at = startAt.current;
        if (HlsJs) {
          hls = new HlsJs({
            startPosition: at,
            // "Auto": assume a fast network at first (the full size), then follow what segments really take,
            // and don't convert more pixels than the window shows
            abrEwmaDefaultEstimate: 20_000_000, capLevelToPlayerSize: !remux && auto,
          });
          hls.on(HlsJs.Events.ERROR, (_e, d) => {
            if (!d.fatal) return;
            if (remux && passthrough && d.type === HlsJs.ErrorTypes.MEDIA_ERROR) return toAac();
            if (remux && d.response?.code !== 503) return toLive();
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
      .catch((e) => {
        if (remux && !(e instanceof ApiError && e.status === 503)) return toLive();
        setProblem(e instanceof ApiError ? e.message : "Couldn't start converting this video.");
      });
    return () => {
      gone = true;
      window.removeEventListener("pagehide", unload);
      hls?.destroy();
      unload();
    };
  }, [ready, useHls, file?.id, hlsKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // The chosen text subtitles: shown through the browser's own <track> rendering.
  useEffect(() => {
    const v = video.current;
    if (!v) return;
    const apply = () => {
      for (const tt of Array.from(v.textTracks)) tt.mode = subTrack && !subTrack.image && tt.label === subTrack.label ? "showing" : "disabled";
    };
    apply();
    v.textTracks.addEventListener("addtrack", apply);
    return () => v.textTracks.removeEventListener("addtrack", apply);
  }, [subTrack, src, useHls, offset]);

  // Subtitle timing: per file and track, remembered on this device (a badly timed subtitle file stays so).
  // The browser's cues are moved in place, so it needs no new stream and works in every mode.
  const delayKey = file && subTrack && !subTrack.image ? `bams.subDelay.${file.id}.${subTrack.id}` : null;
  useEffect(() => { setSubDelay(Number(delayKey && pref(delayKey)) || 0); }, [delayKey]);
  const changeDelay = (ms: number) => {
    if (!delayKey) return;
    ms = Math.round(ms / SUB_STEP) * SUB_STEP;
    setSubDelay(ms);
    setPref(delayKey, ms ? String(ms) : null);
  };
  const delayRef = useRef({ changeDelay, subDelay });
  delayRef.current = { changeDelay, subDelay };
  useEffect(() => {  // a <track> element loads its cues by itself: count each load to re-apply the delay
    if (!trackEl) return;
    const loaded = () => setCuesLoaded((n) => n + 1);
    if (trackEl.readyState === 2) loaded();
    trackEl.addEventListener("load", loaded);
    return () => trackEl.removeEventListener("load", loaded);
  }, [trackEl]);
  useEffect(() => {
    const cues = trackEl?.track.cues;
    if (!cues) return;
    const d = subDelay / 1000;
    for (const c of Array.from(cues)) {
      let own = cueTimes.current.get(c);
      if (!own) cueTimes.current.set(c, own = [c.startTime, c.endTime]);
      c.startTime = Math.max(0, own[0] + d);
      c.endTime = Math.max(c.startTime, own[1] + d);
    }
  }, [subDelay, cuesLoaded, trackEl]);

  // Watch state: the position goes to the server every 10 s while playing, on pause, and on leaving.
  const posRef = useRef(0);
  const totalRef = useRef(0);
  posRef.current = pos;
  totalRef.current = total;
  const report = (position: number, keepalive = false) => {
    if (!watchable || !played.current) return;
    // no duration yet (a file the scan hasn't probed): the position is still worth keeping
    call.send("PUT", `/api/items/${id}/progress`,
      { position: Math.max(0, position), duration: totalRef.current || null }, keepalive).catch(() => {});
  };
  const reportRef = useRef(report);
  reportRef.current = report;
  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => reportRef.current(posRef.current), 10_000);
    return () => clearInterval(timer);
  }, [playing]);
  useEffect(() => {
    const leave = () => reportRef.current(finished.current ? totalRef.current : posRef.current, true);
    window.addEventListener("pagehide", leave);
    return () => { window.removeEventListener("pagehide", leave); leave(); };
  }, []);

  // Up next: when an episode ends, the next one starts after a short countdown.
  useEffect(() => {
    if (upNext === null || !item?.next_id) return;
    if (upNext <= 0) return goNext(true);
    if (!playing && !video.current?.ended) return;  // paused during the credits: so is the countdown
    const timer = setTimeout(() => setUpNext(upNext - 1), 1000);
    return () => clearTimeout(timer);
  }, [upNext, item?.next_id, playing]); // eslint-disable-line react-hooks/exhaustive-deps

  // The credits: the up-next countdown starts CREDITS seconds before the end, as if the episode were over.
  const inCredits = !!item?.next_id && total > 4 * CREDITS && pos >= total - CREDITS;
  useEffect(() => {
    if (inCredits && playing && upNext === null && !skipCredits.current) setUpNext(10);
  }, [inCredits, playing]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (resumed === null) return;
    const timer = setTimeout(() => setResumed(null), 8000);
    return () => clearTimeout(timer);
  }, [resumed]);

  // a new <video> element per stream starts at 1x: carry the chosen speed over (also in onLoadedMetadata)
  useEffect(() => {
    if (video.current) video.current.playbackRate = rate;
  }, [rate]);

  const toggle = () => {
    const v = video.current;
    if (!v) return;
    wantPlay.current = v.paused;
    if (v.paused) v.play().catch(() => {});
    else v.pause();
  };
  /** The stream can play and should: start it, muted if the browser won't allow sound without a tap. */
  const autoStart = (v: HTMLVideoElement) => {
    if (!v.paused || v.ended || !wantPlay.current) return;
    v.play().catch((e) => {
      if (e?.name !== "NotAllowedError" || v.muted) return;
      v.muted = true;
      setMuted(true);
      setSoundBlocked(true);
      v.play().catch(() => {});
    });
  };
  const unmute = () => {
    const v = video.current;
    if (!v) return;
    v.muted = !v.muted;
    setMuted(v.muted);
    setSoundBlocked(false);
  };
  const seek = (s: number) => {
    const target = Math.max(0, Math.min(total || Infinity, s));
    setUpNext(null);
    if (!live) {
      if (video.current) video.current.currentTime = target;
      return;
    }
    // a new stream from there; for the remux, /seek then says where it really starts (effect above)
    setOffset(target);
    setT(0);
    setReqT(Number(target.toFixed(2)));
  };
  /** The next stream (another mode, quality, audio track or HLS session) carries on from `at`. */
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
  const pickQuality = (q: Quality) => {
    setMenu(null);
    if (q === quality) return;
    continueAt(pos);
    setQuality(q);
    setPref(KEYS.quality, q === null ? null : String(q));
  };
  const pickAudio = (i: number) => {
    setMenu(null);
    setPref(KEYS.audioLang, audioTracks[i]?.language ?? null);
    if (i === audio) return;
    continueAt(pos);
    setAudio(i);
  };
  const pickSurround = (on: boolean) => {
    setMenu(null);
    setPref(KEYS.surround, on ? "1" : null);
    if (on === surround) return;
    if (mode !== "file") continueAt(pos);
    setSurround(on);
  };
  const pickPass = (on: boolean) => {
    setMenu(null);
    setPref(KEYS.passthrough, on ? null : "0");
    if (on === passthrough) return;
    if (mode === "remux") continueAt(pos);
    setPassFailed(false);
    setPassPref(on);
  };
  const pickSub = (sid: string | null) => {
    setMenu(null);
    const next = subTracks.find((s) => s.id === sid) ?? null;
    setPref(KEYS.subLang, next?.language ?? null);
    if (!!next?.image !== !!subTrack?.image || (next?.image && next.id !== subTrack?.id)) continueAt(pos); // burned in or out: a new stream
    setSub(sid);
  };
  /** On to the next episode. `done`: from the credits / the end, so this one counts as watched. */
  const goNext = (done: boolean) => {
    if (!item?.next_id) return;
    finished.current = done;  // the report on leaving says where this one ended
    nav(to(`/play/${item.next_id}`), { replace: true });
  };
  const fullscreen = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else shell.current?.requestFullscreen?.();
  };

  // Key handler is registered once; read the latest position/seek through refs.
  const seekRef = useRef(seek);
  seekRef.current = seek;
  const unmuteRef = useRef(unmute);
  unmuteRef.current = unmute;

  useEffect(() => {
    const wake = () => {
      setIdle(false);
      clearTimeout(idleTimer.current);
      idleTimer.current = window.setTimeout(() => setIdle(true), 3000);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === " " || e.key === "k") { e.preventDefault(); toggle(); }
      if (e.key === "Escape" && !document.fullscreenElement) nav(-1);
      if (e.key === "ArrowRight") seekRef.current(posRef.current + SKIP_FORWARD);
      if (e.key === "ArrowLeft") seekRef.current(posRef.current - SKIP_BACK);
      if (e.key === "f") fullscreen();
      if (e.key === "g" || e.key === "h") {
        const d = delayRef.current;
        d.changeDelay(d.subDelay + (e.key === "h" ? SUB_STEP : -SUB_STEP));
      }
      if (e.key === ">" || e.key === "<") setRate((r) => clampSpeed(r + (e.key === ">" ? 0.25 : -0.25)));
      if (e.key === "m") unmuteRef.current();
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
  const subtitle = item.kind === "episode" ? `${sxe(item.season_number!, item.episode_number)} · ${item.title}` : item.year ?? "";
  const fmt = (sec: number) => fmtClock(sec) || "0:00";
  const vcodec = pb?.video_codec ?? "Video";
  const acodec = audioTracks[audio]?.codec ?? pb?.audio_codec;
  const note = passthrough
    ? { text: `${acodec} pass-through`,
        why: `This device decodes ${acodec} itself (and can hand it on to an AV receiver), so the server sends the original audio; the video is passed through untouched too` }
    : mode === "remux"
    ? { text: `${acodec} → AAC${channels > 2 && (audioTracks[audio]?.channels ?? 0) >= 6 ? " 5.1" : ""}`,
        why: `${acodec} audio converted to AAC by the server; the video is passed through untouched` }
    : mode !== "transcode" ? null
    : burn !== null ? { text: "Subtitles burned in", why: "Picture subtitles can only be shown by painting them into a converted video" }
    : mustConvert ? { text: `${vcodec} → H.264${height ? ` ${height}p` : auto ? " (auto)" : ""}`, why: `This browser can't decode ${vcodec} video, so the server converts it to H.264 while streaming` }
    : { text: auto ? "Auto (converted)" : `${height}p (converted)`, why: "Converted by the server (quality menu)" };
  const qualityLabel = height ? `${height}p` : auto ? "Auto" : mode === "transcode" ? "Full size" : "Original";
  const surroundSource = audioTracks.some((a) => (a.channels ?? 0) >= 6);
  const nextUp = upNext !== null && item.next_id;

  return (
    <div ref={shell} className={`player ${idle && playing && !menu ? "idle" : ""}`}>
      {file ? (
        <video
          // a new element per stream: hls.js detaching must not wipe the next stream's src
          key={useHls ? `hls-${hlsKey}` : live ? "live" : "direct"}
          ref={video}
          className="player-video"
          // another server's subtitle <track>s are cross-origin: they load only in CORS mode (BAMS allows any origin)
          crossOrigin={rid === null ? undefined : "anonymous"}
          src={src}
          autoPlay
          playsInline
          onClick={toggle}
          onPlay={() => { setPlaying(true); setUpNext(null); }}
          onPause={() => { setPlaying(false); reportRef.current(posRef.current); }}
          onTimeUpdate={(e) => {
            setT(e.currentTarget.currentTime);
            if (!e.currentTarget.paused) played.current = true;
          }}
          onCanPlay={(e) => autoStart(e.currentTarget)}
          onDurationChange={(e) => !live && setFileDur(e.currentTarget.duration)}
          onEnded={() => {
            report(totalRef.current || posRef.current);  // the end counts as watched
            if (item.next_id) setUpNext(10);
          }}
          onLoadedMetadata={(e) => {
            const v = e.currentTarget;
            v.playbackRate = rate;
            v.muted = muted;  // a new stream's element keeps the viewer's mute (or the browser's refusal)
            if (v.videoWidth === 0)
              toTranscode(`This browser can play the sound but not the ${pb?.video_codec ?? ""} video of this file, and the server can't convert it (no FFmpeg). You can download it.`);
            else if (mode === "file" && startAt.current) {  // resuming, or back to the original file mid-way
              v.currentTime = startAt.current;
              startAt.current = 0;
            }
          }}
          onError={() => passthrough ? (continueAt(pos), setPassFailed(true)) : !useHls && toTranscode(mode === "transcode"
            ? "The server couldn't convert this file (its log has the FFmpeg error). You can download it instead."
            : `This browser can't play this file (${pb?.video_codec ?? "unknown codec"}), and the server can't convert it (no FFmpeg). You can download it.`)}
        >
          {subTrack?.url && (
            <track key={`${subTrack.id}-${live ? offset : 0}`} ref={setTrackEl} kind="subtitles" default label={subTrack.label}
              srcLang={subTrack.language ?? undefined}
              src={live ? `${subTrack.url}?shift=${offset.toFixed(3)}` : subTrack.url} />
          )}
        </video>
      ) : (
        <div className="player-msg"><p>No playable file for this item.</p></div>
      )}

      {problem && file && (
        <div className="player-msg">
          <p>{problem}</p>
          <a className="btn ghost" href={file.download_url} download><Icon name="download" /> Download</a>
        </div>
      )}
      {nextUp && (
        <div className="up-next">
          <span className="muted">Next episode in {upNext}…</span>
          <button className="btn primary small" onClick={() => goNext(true)}>
            <Icon name="play" size={16} /> Play now</button>
          <button className="btn ghost small" onClick={() => { skipCredits.current = true; setUpNext(null); }}>Cancel</button>
        </div>
      )}
      {!playing && !problem && !nextUp && file && (
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
        {soundBlocked && muted && (
          <div className="resumed">Playing without sound: this browser wants a tap first
            <button className="link-btn" onClick={unmute}>Turn sound on</button></div>
        )}
        {resumed !== null && (
          <div className="resumed">Resumed from {fmt(resumed)}
            <button className="link-btn" onClick={() => { setResumed(null); seek(0); }}>Start over</button></div>
        )}
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
          <button className="icon-btn skip-btn" onClick={() => seek(pos - SKIP_BACK)} aria-label={`Back ${SKIP_BACK} seconds`}
            title={`Back ${SKIP_BACK} s (←)`}><Icon name="chevronLeft" size={24} /><span>{SKIP_BACK}</span></button>
          <button className="icon-btn skip-btn" onClick={() => seek(pos + SKIP_FORWARD)} aria-label={`Forward ${SKIP_FORWARD} seconds`}
            title={`Forward ${SKIP_FORWARD} s (→)`}><span>{SKIP_FORWARD}</span><Icon name="chevronRight" size={24} /></button>
          {item.next_id && (
            <button className="icon-btn" onClick={() => goNext(false)} aria-label="Next episode" title="Next episode">
              <Icon name="skipForward" size={22} /></button>
          )}
          <button className={`icon-btn ${muted ? "off" : ""}`} aria-label={muted ? "Unmute" : "Mute"} onClick={unmute}>
            <Icon name="volume" size={24} />
          </button>
          <span className="time">{fmt(scrub ?? pos)} / {fmt(total)}</span>
          {note && <span className="muted audio-note" title={note.why}>{note.text}</span>}
          <span className="spacer" />
          {subTracks.length > 0 && (
            <Menu label={<Icon name="subtitles" size={20} />} title="Subtitles" open={menu === "subs"}
              setOpen={(o) => setMenu(o ? "subs" : null)}>
              {delayKey && <>
                <div className="menu-title">Timing</div>
                <div className="sub-delay">
                  <button onClick={() => changeDelay(subDelay - SUB_STEP)} title="Earlier (g)"
                    aria-label={`Subtitles ${SUB_STEP} ms earlier`}>−{SUB_STEP}</button>
                  <span className={subDelay ? "" : "muted"}>{subDelay > 0 ? "+" : subDelay < 0 ? "−" : ""}
                    {(Math.abs(subDelay) / 1000).toFixed(1)} s</span>
                  <button onClick={() => changeDelay(subDelay + SUB_STEP)} title="Later (h)"
                    aria-label={`Subtitles ${SUB_STEP} ms later`}>+{SUB_STEP}</button>
                </div>
                <button disabled={!subDelay} onClick={() => changeDelay(0)}>Reset timing</button>
                <p className="speed-note">0.1 s a press: + shows them later, − earlier. Kept for this file on
                  this device. Keys: g / h</p>
                <div className="menu-title">Track</div>
              </>}
              <Choice on={!subTrack} onClick={() => pickSub(null)}>Off</Choice>
              {subTracks.map((s) => (
                <Choice key={s.id} on={s.id === sub} onClick={() => pickSub(s.id)}
                  note={s.image ? (canConvert ? "burned in" : "can't show") : s.source === "file" ? "file" : undefined}>
                  {s.label}
                </Choice>
              ))}
            </Menu>
          )}
          {(audioTracks.length > 1 || (surroundSource && canConvert) || (passOk && mode === "remux")) && (
            <Menu label={<Icon name="volume" size={20} />} title="Sound" open={menu === "audio"}
              setOpen={(o) => setMenu(o ? "audio" : null)}>
              {audioTracks.length > 1 && audioTracks.map((a) => (
                <Choice key={a.index} on={a.index === audio} onClick={() => pickAudio(a.index)}
                  note={a.index > 0 && !canConvert ? "needs FFmpeg" : undefined}>{a.label}</Choice>
              ))}
              {passOk && mode === "remux" && <>
                <div className="menu-title">{trackCodec} audio</div>
                <Choice on={passthrough} onClick={() => pickPass(true)}
                  note={passFailed ? "didn't play here" : "this device decodes it"}>Original (pass-through)</Choice>
                <Choice on={!passthrough} onClick={() => pickPass(false)}>Convert to AAC</Choice>
              </>}
              {surroundSource && canConvert && !passthrough && <>
                <div className="menu-title">When converting</div>
                <Choice on={!surround} onClick={() => pickSurround(false)}>Stereo</Choice>
                <Choice on={surround} onClick={() => pickSurround(true)} note="keeps 5.1">Surround</Choice>
              </>}
            </Menu>
          )}
          {file && (
            <Menu label={`${rate}x`} title="Speed" open={menu === "speed"} setOpen={(o) => setMenu(o ? "speed" : null)}>
              <div className="speed-pick">
                <input type="range" min={SPEED_MIN} max={SPEED_MAX} step={0.05} value={rate} aria-label="Playback speed"
                  onChange={(e) => setRate(clampSpeed(Number(e.target.value)))}
                  style={{ ["--pct" as string]: `${((rate - SPEED_MIN) / (SPEED_MAX - SPEED_MIN)) * 100}%` }} />
                <span className="speed-ends"><span>{SPEED_MIN}x</span><span>{SPEED_MAX}x</span></span>
              </div>
              {[0.5, 1, 1.25, 1.5, 2].map((r) => (
                <Choice key={r} on={rate === r} onClick={() => setRate(r)}>{r === 1 ? "Normal" : `${r}x`}</Choice>
              ))}
              {rate > 1.5 && mode === "transcode" && <p className="speed-note">Converted video: fast speeds need a
                server that converts faster than that, or playback pauses to catch up.</p>}
              <p className="speed-note">Keys: &lt; and &gt;</p>
            </Menu>
          )}
          {qualities.length > 0 && (
            <Menu label={qualityLabel} title="Quality" open={menu === "quality"} setOpen={(o) => setMenu(o ? "quality" : null)}>
              {!mustConvert && <Choice on={mode !== "transcode"} onClick={() => pickQuality(null)} note="as-is">Original</Choice>}
              <Choice on={auto} onClick={() => pickQuality(mustConvert ? null : "auto")} note="adapts">Auto</Choice>
              {mustConvert && <Choice on={mode === "transcode" && !auto && !height} onClick={() => pickQuality(FULL)}
                note="converted">Full size</Choice>}
              {qualities.map((h) => (
                <Choice key={h} on={height === h} onClick={() => pickQuality(h)} note="converted">{h}p</Choice>
              ))}
            </Menu>
          )}
          {file && <a className="icon-btn" href={file.download_url} download title="Download"><Icon name="download" size={22} /></a>}
          <button className="icon-btn" title="Fullscreen (f)" onClick={fullscreen}><Icon name="fullscreen" size={24} /></button>
        </div>
      </div>
    </div>
  );
}
