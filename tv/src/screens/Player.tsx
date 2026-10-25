import { useCallback, useEffect, useRef, useState } from "react";
import { apiFor, mediaFor, refreshTicket, renewTickets, type FileInfo, type ItemDetail, type SubtitleSearch, type SubtitleTrack } from "../api";
import { useNav } from "../App";
import { AvplayEngine, ExoEngine, hasAvplay, hasExo, VideoEngine, type Engine } from "../engine";
import { clock, sxe } from "../format";
import Icon from "../Icon";
import { setKeyHandler } from "../keys";
import { focus, focusFirst } from "../nav";
import { caps, convertHeight, pickAudio, pickFile, plan, soundToAac, type Mode } from "../plan";
import { prefs, setPref } from "../prefs";
import { QueuePanel } from "../Queue";
import { entrySub, moveVideo, queueIndex, queueNext, removeVideo, untracked, useVideoQueue } from "../random";
import { isBack, KEY } from "../tizen";
import { pc } from "../platform";
import { cueAt, parseVtt, type Cue } from "../vtt";
import { defaultLanguage, languageName, OS_LANGUAGES } from "../../../web/src/subtitleLangs";

const OSD_HIDE = 5000;   // ms without a key before the controls fade while playing
const SEEK_SETTLE = 700; // ms after the last left/right press before the seek is made
const UP_NEXT = 10;      // seconds before the next episode starts by itself
const SLEEP_MORE = 2;    // sleep mode on an episode: this one, then this many more, then playback stops (as on the web)

/** The player: the file as-is when the TV can (AVPlay decodes MKV/HEVC/AC3..., a Fire TV what its decoders take),
 *  else an HLS session from the server (sound converted, or everything converted). Saves the position like the web player does.
 *  `rid`: the item is on another of this TV's servers (api.ts); everything then goes to that one. */
export default function Player({ id, resume, rid, sleep: sleeping, shuffle }: { id: number; resume: boolean; rid?: number;
  /** sleep mode: episodes still to play after this one (0 = stop after it), carried over from the last episode */
  sleep?: number;
  /** reached through a holiday's Shuffle: while in its queue, nothing is kept (no progress, no Continue Watching) */
  shuffle?: boolean }) {
  const quiet = () => !!shuffle && untracked(id, rid);
  const api = apiFor(rid);      // this item's server
  const media = mediaFor(rid);
  const nav = useNav();
  const videoRef = useRef<HTMLVideoElement>(null);
  const engine = useRef<Engine | null>(null);
  const [item, setItem] = useState<ItemDetail | null>(null);
  const [file, setFile] = useState<FileInfo | null>(null);
  const [audio, setAudio] = useState(0);
  const [sub, setSub] = useState<SubtitleTrack | null>(null);
  const [cues, setCues] = useState<Cue[]>([]);
  const [mode, setMode] = useState<Mode | null>(null);
  const [time, setTime] = useState(0);
  const [paused, setPaused] = useState(false);
  const [, setClockTick] = useState(0);  // the "ends at" time moves on while paused too
  useEffect(() => {
    const t = setInterval(() => setClockTick((n) => n + 1), 20_000);
    return () => clearInterval(t);
  }, []);
  const [buffering, setBuffering] = useState(true);
  const [osd, setOsd] = useState(true);
  // "find": Check OpenSubtitles, "findLang": its language list
  const [menu, setMenu] = useState<"audio" | "subs" | "find" | "findLang" | null>(null);
  const [seekTo, setSeekTo] = useState<number | null>(null);
  const [upNext, setUpNext] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [subDelay, setSubDelay] = useState(prefs.subDelay);
  const [sleep, setSleep] = useState<number | null>(sleeping ?? null);  // null = off
  const [slept, setSlept] = useState(false);  // sleep mode stopped playback at the end
  const [found, setFound] = useState<SubtitleTrack[]>([]);  // fetched from OpenSubtitles while playing
  const [removed, setRemoved] = useState<string[]>([]);      // downloaded subtitles taken off while playing
  const [subNote, setSubNote] = useState<string | null>(null);  // why a removal failed
  const [osLang, setOsLang] = useState(() => defaultLanguage(prefs.osLang, prefs.subLang || null));

  // what callbacks need without re-binding
  const st = useRef({ file: null as FileInfo | null, audio: 0, sub: null as SubtitleTrack | null, mode: null as Mode | null,
    session: null as string | null, started: false, startAt: 0, fellBack: false, duration: null as number | null,
    item: null as ItemDetail | null, seek: null as number | null, ended: false, sleep: sleeping ?? null as number | null,
    // a PC's fallback steps (fail): Dolby sound copied this time, AAC wanted instead, the remux tried
    passed: false, noPass: false, triedRemux: false,
    // begin() calls so far (a later one, or leaving, makes an earlier one stale); when a stream that played was lost
    starts: 0, lostAt: 0 });
  const timers = useRef<{ osd?: ReturnType<typeof setTimeout>; seek?: ReturnType<typeof setTimeout>; next?: ReturnType<typeof setInterval> }>({});

  // Play Random (random.tsx): while this video is in the random queue, "next" is the queue's next, not the next episode
  const vq = useVideoQueue();
  const qAt = queueIndex(id, rid);
  const [queueOpen, setQueueOpen] = useState(false);
  const nextOf = (): number | null => {
    const q = queueNext(id, rid);
    return q !== undefined ? q : st.current.item?.next_id ?? null;
  };
  const nextId = item ? nextOf() : null;

  const duration = (): number | null => st.current.duration ?? engine.current?.duration() ?? null;

  const report = useCallback((keepalive = false, position?: number) => {
    const e = engine.current;
    if (!e || !st.current.started || quiet()) return;  // a holiday's Shuffle: kept nowhere
    const pos = position ?? e.time();
    void api.put(`/api/items/${id}/progress`, { position: pos, duration: duration() }, keepalive).catch(() => undefined);
  }, [id, rid, shuffle]);

  const closeSession = () => {
    const sid = st.current.session;
    st.current.session = null;
    if (sid) void api.del(`/api/hls/${sid}`).catch(() => undefined);
  };

  /** Start (or restart) playback at `at` with the current file / audio / subtitles. `force` = a fallback mode. */
  const begin = useCallback(async (at: number, force?: Mode) => {
    const s = st.current;
    const f = s.file, e = engine.current;
    if (!f || !e) return;
    // A start can take a while (the server reading the file). If the viewer left meanwhile, or another start
    // followed, this one must stop: the TV has one player, and a late load() took it over from the next video.
    const n = ++s.starts;
    const stale = () => n !== s.starts || engine.current !== e;
    const burn = s.sub?.image ? s.sub.id : null;
    const how = force ? { mode: force, why: "fallback" } : plan(f, s.audio, burn);
    setError(null);
    setBuffering(true);
    closeSession();
    s.mode = how.mode;
    setMode(how.mode);
    s.startAt = at;
    try {
      if (rid === undefined) await refreshTicket();  // another server's: kept fresh by its api calls
      if (stale()) return;
      let url: string | null;
      let hls = false;
      // Samsung's player can't seek in a file it streams itself (resume and skipping froze), so on the TV even what
      // it plays as-is comes as HLS that the server cuts from the file: video and Dolby sound copied, nothing
      // converted. MPEG-TS segments: it plays no fMP4 HLS.
      const cut = how.mode === "direct" && hasAvplay() && !!f.playback.hls_url;
      if (how.mode === "direct" && !cut) {
        url = media(f.stream_url);
      } else {
        if (!f.playback.hls_url) throw new Error("The server can't convert video (FFmpeg wasn't found there).");
        // a Fire TV and a PC's browser take fMP4 (which keeps Dolby Vision; hls.js refuses E-AC-3 in MPEG-TS);
        // Dolby sound is copied when the device plays it (on a PC, until that failed once)
        const track = f.probe?.audio[s.audio];
        s.passed = hasAvplay() || ((hasExo() || pc()) && !s.noPass && !!track && caps().audio.has(track.codec));
        const r = await api.post<{ id: string; playlist: string }>(f.playback.hls_url, {
          remux: how.mode !== "convert", ts: !hasExo() && !pc(), audio: s.audio, channels: 6, start: at,
          passthrough: s.passed,
          height: how.mode === "convert" ? convertHeight() : undefined, burn: burn ?? undefined,
        });
        if (stale()) return void api.del(`/api/hls/${r.id}`).catch(() => undefined);
        s.session = r.id;
        url = media(r.playlist);
        hls = true;
      }
      if (!url) throw new Error("No address to play.");
      await e.load(url, at, hls);
      if (stale()) return;
      if (how.mode === "direct" && !cut && (f.audio_tracks?.length ?? 0) > 1 && !e.selectAudio(s.audio) && s.audio !== 0) {
        return void begin(at, "remux");  // this player can't switch tracks itself: the server picks it
      }
      setPaused(false);
    } catch (err) {
      if (!stale()) fail((err as Error).message);
    }
  }, []);

  /** Something went wrong: fall back to the server converting everything once, else show the error. A PC's browser
   *  first tries the cheap steps, as the web player does: Dolby sound converted to AAC, the file remuxed (video
   *  copied, sound converted). Each retry first gets fresh media tickets: a server restart kills the old ones. */
  const fail = (msg: string) => {
    const s = st.current;
    const now = engine.current?.time() || s.startAt;
    const at = now > 0 ? now : s.startAt;
    const retry = (mode: Mode) => void renewTickets().then(() => begin(at, mode));
    // a Fire TV whose Dolby output can't be opened (stuck since the last video: `stall`): the sound converted to AAC by
    // the server, the video still copied, before converting everything
    if (hasExo() && /^ERROR_CODE_AUDIO_TRACK_/.test(msg) && aacNext()) return retry("remux");
    // the stream played fine for a while, so it was lost (the server restarted), not unplayable: the same way again
    // first, rather than the server converting a video this device plays (once a minute, so a dead server ends here)
    if (s.mode && now > s.startAt + 10 && Date.now() - s.lostAt > 60000) {
      s.lostAt = Date.now();
      return retry(s.mode);
    }
    if (pc() && s.mode === "remux" && s.passed && !s.noPass) {
      s.noPass = true;
      return retry("remux");
    }
    if (pc() && s.mode === "direct" && !s.triedRemux && st.current.file?.playback.hls_url) {
      s.triedRemux = true;
      return retry("remux");
    }
    if (s.mode !== "convert" && !s.fellBack) {
      s.fellBack = true;
      return retry("convert");
    }
    setBuffering(false);
    setError(msg || "This video couldn't be played.");
  };

  /** Dolby sound went to the device as-is: the next try has the server convert it to AAC (once). */
  const aacNext = () => {
    const s = st.current;
    if (!s.file || !s.mode || !soundToAac(s.file, s.audio, s.mode, s.passed, s.noPass)) return false;
    s.noPass = true;
    return true;
  };

  /** The Fire TV's player is playing but stuck at one place (Video.kt): with Dolby sound as-is, its one Dolby output
   *  is likely stuck (the picture came, the sound never started), so the sound is converted to AAC; anything else
   *  falls back as an error would. */
  const stall = () => {
    if (aacNext()) {
      const at = engine.current?.time() || st.current.startAt;
      return void renewTickets().then(() => begin(at, "remux"));
    }
    fail("The video stopped and didn't go on.");
  };

  // load the title, make the engine, go
  useEffect(() => {
    document.documentElement.classList.add("playing");
    const ev = {
      onTime: (t: number) => {
        setTime(t);
        if (t > st.current.startAt + 1) st.current.started = true;
      },
      onEnd: () => {
        if (st.current.ended) return;
        st.current.ended = true;
        const d = duration();
        report(false, d ?? engine.current?.time());
        const next = nextOf();
        if (st.current.sleep === 0) setSlept(true);  // sleep mode: that was the last one
        else if (next) setUpNext(UP_NEXT);
        else nav.back();
      },
      onError: (m: string) => fail(m),
      onBuffering: (b: boolean) => setBuffering(b),
      onStall: () => stall(),
      onPaused: (p: boolean) => setPaused(p),
    };
    engine.current = hasAvplay() ? new AvplayEngine(ev) : hasExo() ? new ExoEngine(ev) : new VideoEngine(videoRef.current!, ev);
    api.get<ItemDetail>(`/api/items/${id}`).then((d) => {
      const f = pickFile(d.files);
      if (!f) throw new Error("No file of this is available right now (drive offline or moved).");
      const a = pickAudio(f);
      const s = pickSub(f, a);
      Object.assign(st.current, { item: d, file: f, audio: a, sub: s, duration: f.probe?.duration ?? null });
      setItem(d);
      setFile(f);
      setAudio(a);
      setSub(s);
      const at = resume && !quiet() ? d.progress?.position ?? 0 : 0;
      void begin(at);
    }).catch((e) => {
      setBuffering(false);
      setError((e as Error).message);
    });
    return () => {
      report(true);
      closeSession();
      engine.current?.destroy();
      engine.current = null;
      document.documentElement.classList.remove("playing");
      Object.values(timers.current).forEach((t) => { clearTimeout(t as number); clearInterval(t as number); });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // the position goes to the server every 10 s while playing
  useEffect(() => {
    if (paused) return report();
    const t = setInterval(() => report(), 10000);
    return () => clearInterval(t);
  }, [paused, report]);

  // text subtitles: the server's WebVTT, drawn here (the same for every way of playing)
  useEffect(() => {
    setCues([]);
    if (!sub || sub.image || !sub.url) return;
    let live = true;
    api.text(sub.url).then((v) => live && setCues(parseVtt(v))).catch(() => undefined);
    return () => { live = false; };
  }, [sub]);

  // the controls fade OSD_HIDE after the last key, once the video plays: while it's paused, still starting, restarting
  // after a seek or a menu is open, look again each second (a one-off check at OSD_HIDE left them up for good when
  // the stream was still loading then)
  const wake = useCallback(() => {
    setOsd(true);
    clearTimeout(timers.current.osd);
    const hide = () => {
      if (engine.current && !engine.current.paused() && !document.querySelector("[data-trap]")) setOsd(false);
      else timers.current.osd = setTimeout(hide, 1000);
    };
    timers.current.osd = setTimeout(hide, OSD_HIDE);
  }, []);
  useEffect(() => { wake(); }, [wake]);
  // a PC's mouse moving shows the controls too (they take its clicks while the pointer shows: styles.css)
  useEffect(() => {
    if (!pc()) return;
    window.addEventListener("mousemove", wake);
    return () => window.removeEventListener("mousemove", wake);
  }, [wake]);

  const toggle = () => {
    const e = engine.current;
    if (!e) return;
    if (e.paused()) {
      e.play();
      setPaused(false);
    } else {
      e.pause();
      setPaused(true);
    }
    wake();
  };

  const seekBy = (d: number) => {
    const e = engine.current;
    if (!e) return;
    const dur = duration() ?? Infinity;
    const from = st.current.seek ?? e.time();
    const target = Math.max(0, Math.min(dur - 2, from + d));
    st.current.seek = target;
    setSeekTo(target);
    wake();
    clearTimeout(timers.current.seek);
    timers.current.seek = setTimeout(() => {
      st.current.seek = null;
      setSeekTo(null);
      setTime(target);
      void e.seek(target);
    }, SEEK_SETTLE);
  };

  const playNext = () => {
    clearInterval(timers.current.next);
    const next = nextOf();
    // sleep mode counts down; going on by hand after it stopped means someone's awake: off
    const left = st.current.sleep;
    if (next) nav.replace({ name: "player", id: next, rid, resume: true, sleep: left ? left - 1 : undefined,
      shuffle: quiet() || undefined });
  };

  // the up-next countdown
  useEffect(() => {
    if (upNext === null) return;
    if (upNext <= 0) return playNext();
    const t = setTimeout(() => setUpNext((n) => (n === null ? n : n - 1)), 1000);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [upNext]);

  const chooseAudio = (n: number) => {
    setMenu(null);
    const f = st.current.file;
    const t = f?.audio_tracks?.find((x) => x.index === n);
    setPref("audioLang", t?.language ?? null);
    if (n === st.current.audio) return;
    st.current.audio = n;
    setAudio(n);
    const e = engine.current;
    const now = e?.time() ?? 0;
    if (st.current.mode === "direct" && !hasAvplay() && f && plan(f, n, null).mode === "direct" && e?.selectAudio(n)) return;
    void begin(now);  // the server makes the stream with that track
  };

  const toggleSleep = () => {
    const n = sleep !== null ? null : nextOf() ? SLEEP_MORE : 0;
    st.current.sleep = n;
    setSleep(n);
    wake();
  };

  /** A subtitle picked from OpenSubtitles: now one of the file's tracks, shown at once. */
  const takeFound = (t: SubtitleTrack) => {
    setFound((f) => f.some((x) => x.id === t.id) || st.current.file?.subtitles?.some((x) => x.id === t.id) ? f : [...f, t]);
    chooseSub(t);
    setTimeout(() => focus(document.querySelector<HTMLElement>('[data-fid="osd-subs"]')));
  };
  const pickOsLang = (code: string) => {
    setOsLang(code);
    setPref("osLang", code);
    setMenu("find");
  };

  const chooseSub = (t: SubtitleTrack | null) => {
    setMenu(null);
    setPref("subLang", t ? t.language ?? "" : "");
    const was = st.current.sub;
    st.current.sub = t;
    setSub(t);
    // picture subtitles are painted on by the server: changing to/from them restarts the stream
    if (was?.image || t?.image) void begin(engine.current?.time() ?? 0);
  };

  // the remote, before the focus moves
  useEffect(() => {
    setKeyHandler((e) => {
      const k = e.keyCode;
      if (upNext !== null) {
        if (k === KEY.ENTER) { playNext(); return true; }
        if (isBack(e)) { setUpNext(null); nav.back(); return true; }
        return true;
      }
      if (error || slept) {
        if (isBack(e) || k === KEY.ENTER) { nav.back(); return true; }
        return false;
      }
      wake();  // every key counts, menu keys too
      if (queueOpen) {
        if (isBack(e)) { setQueueOpen(false); setTimeout(() => focus(document.querySelector<HTMLElement>('[data-fid="osd-queue"]'))); return true; }
        return false;  // arrows and OK move within Up next
      }
      if (menu) {
        if (isBack(e) && menu === "findLang") { setMenu("find"); return true; }
        if (isBack(e)) { setMenu(null); setTimeout(() => focus(document.querySelector<HTMLElement>(`[data-fid="osd-${menu === "audio" ? "audio" : "subs"}"]`))); return true; }
        return false;  // arrows and OK move within the menu
      }
      const active = document.activeElement as HTMLElement | null;
      const onExit = !!active?.closest(".osd-exit");  // a PC's back arrow, top left
      const inButtons = onExit || !!active?.closest(".osd-buttons");
      switch (k) {
        case KEY.PLAY_PAUSE: toggle(); return true;
        case KEY.PLAY: if (engine.current?.paused()) toggle(); return true;
        case KEY.PAUSE: if (!engine.current?.paused()) toggle(); return true;
        case KEY.STOP: nav.back(); return true;
        case KEY.FF: seekBy(30); return true;
        case KEY.RW: seekBy(-10); return true;
        case KEY.NEXT: if (nextOf()) playNext(); return true;
      }
      if (isBack(e)) {
        if (osd && inButtons) { (document.activeElement as HTMLElement).blur(); setOsd(false); return true; }
        nav.back();
        return true;
      }
      if (!osd || !inButtons) {
        if (k === KEY.LEFT) { seekBy(-10); return true; }
        if (k === KEY.RIGHT) { seekBy(30); return true; }
        if (k === KEY.ENTER) { toggle(); return true; }
        if (k === KEY.UP || k === KEY.DOWN) {
          setOsd(true);
          setTimeout(() => focusFirst(document.querySelector(".osd-buttons") ?? document));
          return true;
        }
        return true;
      }
      if (onExit) {
        if (k === KEY.DOWN) { focusFirst(document.querySelector(".osd-buttons") ?? document); return true; }
        if (k === KEY.UP) { active!.blur(); return true; }
        if (k === KEY.LEFT || k === KEY.RIGHT) return true;
        return false;  // OK presses it (App.tsx)
      }
      if (k === KEY.UP) {
        const exit = document.querySelector<HTMLElement>(".osd-exit");
        if (exit) focus(exit);  // a PC: up to the back arrow
        else (document.activeElement as HTMLElement).blur();
        return true;
      }
      return false;  // left/right/OK among the buttons
    });
    return () => setKeyHandler(null);
  });

  const now = seekTo ?? time;
  const dur = duration();
  // the web player's times (web/src/pages/Player.tsx): what's left, and when it will be done by this device's clock
  const left = dur ? Math.max(0, dur - now) : null;
  const endsAt = left !== null ? new Date(Date.now() + left * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : null;
  const cue = cueAt(cues, now, subDelay);  // shown later by the timing set in the menu
  const show = item?.ancestors.find((a) => a.kind === "show");
  const title = show ? show.title : item?.title ?? "";
  const subtitle = item?.kind === "episode" ? `${sxe(item)} · ${item.title}` : null;
  const subs = [...(file?.subtitles ?? []), ...found.filter((f) => !file?.subtitles?.some((x) => x.id === f.id))]
    .filter((t) => !removed.includes(t.id));
  // who may remove a downloaded subtitle: whoever downloaded it, or an admin (of the server the video is on)
  const me = rid === undefined ? nav.user : nav.servers.find((x) => x.id === rid)?.user ?? null;
  const mayRemove = (t: SubtitleTrack) => t.source === "download" && !!me && (me.is_admin || t.added_by === me.id);
  const removeSub = async (t: SubtitleTrack) => {
    setSubNote(null);
    try {
      await api.del(`/api/files/${file!.id}/subtitles/${t.id}`);
    } catch (e) {
      return setSubNote((e as Error).message);
    }
    setRemoved((r) => [...r, t.id]);
    if (st.current.sub?.id === t.id) {
      st.current.sub = null;
      setSub(null);
    }
    // the focus was on its Remove button, which is gone: back on the ticked option
    setTimeout(() => focus(document.querySelector<HTMLElement>(".menu .menu-item.on") ?? document.querySelector<HTMLElement>(".menu .menu-item")));
  };

  return (
    <div className={`player ${osd ? "" : "hide-cursor"}`}>
      {/* Fire TV: ExoPlayer draws under the WebView, nothing to put here */}
      {hasAvplay() ? <object className="avplayer" type="application/avplayer" /> : hasExo() ? null : <video ref={videoRef} className="video" />}

      {cue && <div className={`subtitle ${osd ? "raised" : ""}`} dangerouslySetInnerHTML={{ __html: cue.text }} />}
      {buffering && !error && <div className="player-center"><div className="spinner" /></div>}
      {paused && !osd && <div className="player-center"><Icon name="pause" size={120} /></div>}

      <div className={`osd ${osd ? "on" : ""}`}>
        <div className="osd-top">
          {pc() ? (
            <div className="osd-title-row">
              {/* a PC: the browser's Back can't be relied on, so the player has its own (Up from the buttons) */}
              <button className="round osd-exit" data-fid="osd-exit" aria-label="Back" onClick={() => nav.back()}>
                <Icon name="arrowLeft" />
              </button>
              <div>
                <h1>{title}</h1>
                {subtitle && <div className="osd-sub">{subtitle}</div>}
              </div>
            </div>
          ) : (<>
            <h1>{title}</h1>
            {subtitle && <div className="osd-sub">{subtitle}</div>}
          </>)}
        </div>
        <div className="osd-bottom">
          <div className="scrub-times">
            <span>{clock(now)}</span>
            <span>{left !== null ? `-${clock(left)}` : clock(dur)}{endsAt && <span className="ends-at"> ({endsAt})</span>}</span>
          </div>
          <div className="scrub">
            <div className="scrub-bar">
              <div className="scrub-fill" style={{ width: dur ? `${Math.min(100, (now / dur) * 100)}%` : "0%" }} />
            </div>
          </div>
          <div className="osd-buttons">
            <button className="round" data-fid="osd-play" onClick={toggle}><Icon name={paused ? "play" : "pause"} /></button>
            <button className="round" data-fid="osd-back" onClick={() => seekBy(-10)}><Icon name="back10" /></button>
            <button className="round" data-fid="osd-fwd" onClick={() => seekBy(30)}><Icon name="fwd30" /></button>
            {(file?.audio_tracks?.length ?? 0) > 1 && (
              <button className="pill" data-fid="osd-audio" onClick={() => setMenu("audio")}><Icon name="audio" /> Sound</button>
            )}
            {(subs.length > 0 || !!item?.opensubtitles) && (
              <button className="pill" data-fid="osd-subs" onClick={() => setMenu("subs")}><Icon name="subs" /> Subtitles</button>
            )}
            {nextId && <button className="pill" data-fid="osd-next" onClick={playNext}><Icon name="next" /> {qAt >= 0 ? "Next" : "Next episode"}</button>}
            {qAt >= 0 && <button className="pill" data-fid="osd-queue" onClick={() => setQueueOpen(true)}><Icon name="list" /> Up next</button>}
            {(item?.kind === "movie" || item?.kind === "episode") && (
              <button className={`pill ${sleep !== null ? "on" : ""}`} data-fid="osd-sleep" onClick={toggleSleep}>
                <Icon name="sleep" /> {sleep === null ? "Sleep" : sleep ? `Sleep: this + ${sleep} more` : "Sleep: stop after this"}
              </button>
            )}
            <span className="osd-mode">{mode === "direct" ? "Playing as-is" : mode === "remux" ? "Video as-is, sound converted" : mode === "convert" ? "Converted by the server" : ""}</span>
          </div>
          <div className="osd-hint">◀ ▶ skip back 10 s / ahead 30 s · OK pause · ▲▼ controls</div>
        </div>
      </div>

      {queueOpen && qAt >= 0 && (
        <QueuePanel at={qAt} rows={vq.items.map((e) => ({ key: `${e.id}`, title: e.title, sub: entrySub(e) }))}
          onMove={moveVideo} onRemove={removeVideo}
          onJump={(i) => { const v = vq.items[i]; if (v && v.id !== id) nav.replace({ name: "player", id: v.id, rid, resume: true, shuffle: quiet() || undefined }); }}
          onClose={() => { setQueueOpen(false); setTimeout(() => focus(document.querySelector<HTMLElement>('[data-fid="osd-queue"]'))); }} />
      )}
      {(menu === "find" || menu === "findLang") && file && (
        <FindSubs fileId={file.id} rid={rid} lang={osLang} picking={menu === "findLang"} current={sub?.id ?? null}
          tracks={subs} onLang={() => setMenu("findLang")} onPickLang={pickOsLang} onUse={takeFound} />
      )}
      {(menu === "audio" || menu === "subs") && file && (
        <Menu title={menu === "audio" ? "Sound" : "Subtitles"}
          extra={menu === "subs" && (sub && !sub.image || subNote) ? (<>
            {subNote && <p className="os-note bad">{subNote}</p>}
            {sub && !sub.image && <div className="menu-timing">
              <span>Timing</span>
              <button className="pill" onClick={() => { const v = Math.round((subDelay - 0.1) * 10) / 10; setSubDelay(v); setPref("subDelay", v); }}>Earlier</button>
              <strong>{subDelay === 0 ? "0.0 s" : `${subDelay > 0 ? "+" : ""}${subDelay.toFixed(1)} s`}</strong>
              <button className="pill" onClick={() => { const v = Math.round((subDelay + 0.1) * 10) / 10; setSubDelay(v); setPref("subDelay", v); }}>Later</button>
            </div>}
          </>) : null}
          options={menu === "audio"
            ? (file.audio_tracks ?? []).map((t) => ({ key: `a${t.index}`, label: t.label, on: t.index === audio, pick: () => chooseAudio(t.index) }))
            : [{ key: "off", label: "Off", on: !sub, pick: () => chooseSub(null) },
              ...subs.map((t) => ({ key: t.id, label: t.label + (t.image ? " (the server converts the video)"
                : t.source === "download" ? " (OpenSubtitles)" : ""), on: sub?.id === t.id, pick: () => chooseSub(t),
                remove: mayRemove(t) ? () => void removeSub(t) : undefined })),
              ...(item?.opensubtitles ? [{ key: "os", label: "Check OpenSubtitles…", on: false, pick: () => setMenu("find") }] : [])]} />
      )}

      {upNext !== null && nextId && (
        <div className="upnext" data-trap>
          <h2>{qAt >= 0 ? "Next" : "Next episode"} in {upNext}</h2>
          <div className="button-row">
            <button className="btn primary" ref={(b) => b?.focus()} onClick={playNext}><Icon name="play" size={30} /> Play now</button>
            <button className="btn" onClick={() => nav.back()}>Back</button>
          </div>
        </div>
      )}

      {slept && !error && (
        <div className="player-error" data-trap>
          <h2>Sleep mode</h2>
          <p>Playback stopped here.</p>
          <button className="btn primary" ref={(b) => b?.focus()} onClick={() => nav.back()}>Back</button>
        </div>
      )}

      {error && (
        <div className="player-error" data-trap>
          <h2>Can't play this</h2>
          <p>{error}</p>
          <button className="btn primary" ref={(b) => b?.focus()} onClick={() => nav.back()}>Back</button>
        </div>
      )}
    </div>
  );
}

/** A player menu (Sound, Subtitles). An option with `remove` gets a Remove button beside it (Right from the option). */
function Menu({ title, options, extra }: { title: string; extra?: React.ReactNode;
  options: { key: string; label: string; on: boolean; pick: () => void; remove?: () => void }[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setTimeout(() => focus(ref.current?.querySelector<HTMLElement>(".on") ?? ref.current?.querySelector("button")));
  }, []);
  return (
    <div className="menu" data-trap ref={ref}>
      <h2>{title}</h2>
      {extra}
      <div className="menu-list" data-scroll>
        {options.map((o) => {
          const option = (
            <button key={o.key} className={`menu-item ${o.on ? "on" : ""}`} onClick={o.pick}>
              <span className="tick">{o.on ? "✓" : ""}</span>{o.label}
            </button>
          );
          return o.remove ? <div key={o.key} className="menu-row">{option}<button className="pill" onClick={o.remove}>Remove</button></div> : option;
        })}
      </div>
    </div>
  );
}

/** "Check OpenSubtitles": what OpenSubtitles has for the playing file in one language; OK on one fetches it (on the
 *  server, which keeps it for that file) and shows it. The language button opens the list of languages. */
function FindSubs({ fileId, rid, lang, picking, current, tracks, onLang, onPickLang, onUse }: {
  fileId: number; rid?: number; lang: string; picking: boolean; current: string | null; tracks: SubtitleTrack[];
  onLang: () => void; onPickLang: (code: string) => void; onUse: (t: SubtitleTrack) => void;
}) {
  const api = apiFor(rid);
  const ref = useRef<HTMLDivElement>(null);
  const [res, setRes] = useState<SubtitleSearch | null>(null);
  const [busy, setBusy] = useState<number | "search" | null>("search");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setBusy("search");
    setErr(null);
    api.get<SubtitleSearch>(`/api/files/${fileId}/opensubtitles?languages=${encodeURIComponent(lang)}`)
      .then((r) => { if (live) setRes(r); })
      .catch((e) => { if (live) { setRes(null); setErr((e as Error).message); } })
      .finally(() => { if (live) setBusy(null); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileId, lang]);

  // the focus: the language picked (list), else the first result, else the language button
  useEffect(() => {
    if (busy === "search" && !picking) return;
    setTimeout(() => focus(ref.current?.querySelector<HTMLElement>(picking ? ".menu-item.on" : ".os-result")
      ?? ref.current?.querySelector<HTMLElement>("button")));
  }, [picking, busy === "search"]); // eslint-disable-line react-hooks/exhaustive-deps

  const use = async (fid: number) => {
    const r = res?.results.find((x) => x.file_id === fid);
    if (!r) return;
    const have = r.track ? tracks.find((t) => t.id === r.track) : undefined;
    if (have) return onUse(have);
    setBusy(fid);
    setErr(null);
    try {
      const d = await api.post<{ track: SubtitleTrack }>(`/api/files/${fileId}/opensubtitles`,
        { file_id: r.file_id, language: r.language, release: r.release, hearing_impaired: r.hearing_impaired });
      onUse(d.track);
    } catch (e) {
      setErr((e as Error).message);
      setBusy(null);
    }
  };

  if (picking) {
    return (
      <div className="menu" data-trap ref={ref}>
        <h2>Subtitle language</h2>
        <div className="menu-list" data-scroll>
          {OS_LANGUAGES.map((c) => (
            <button key={c} className={`menu-item ${c === lang ? "on" : ""}`} onClick={() => onPickLang(c)}>
              <span className="tick">{c === lang ? "✓" : ""}</span>{languageName(c)}
            </button>
          ))}
        </div>
      </div>
    );
  }
  return (
    <div className="menu" data-trap ref={ref}>
      <h2>OpenSubtitles</h2>
      <button className="pill os-lang" onClick={onLang}>Language: {languageName(lang)}</button>
      {busy === "search" && <p className="os-note">Searching OpenSubtitles…</p>}
      {err && <p className="os-note bad">{err}</p>}
      {res && busy !== "search" && !res.results.length && (
        <p className="os-note">Nothing in {languageName(lang)}. Try another language.</p>
      )}
      {res && busy !== "search" && res.results.length > 0 && (
        <div className="menu-list" data-scroll>
          {res.results.map((r) => (
            <button key={r.file_id} className={`menu-item os-result ${r.track && r.track === current ? "on" : ""}`}
              onClick={() => use(r.file_id)}>
              <span className="tick">{r.track && r.track === current ? "✓" : ""}</span>
              <span>
                <span>{r.release || "(no release name)"}</span>
                <span className="os-meta">{[busy === r.file_id ? "Downloading…" : null, r.hash_match ? "made for this file" : null,
                  r.hearing_impaired ? "for the hard of hearing" : null, `${r.downloads.toLocaleString()} downloads`,
                  r.ai || r.machine ? "machine-translated" : null, r.track ? "on this video" : null].filter(Boolean).join(" · ")}</span>
              </span>
            </button>
          ))}
        </div>
      )}
      <p className="os-note">Subtitles from OpenSubtitles.com. If one doesn't fit, come back and try another.</p>
    </div>
  );
}

/** The subtitles to start with: the language picked last time (Off stays off), else forced ones in the sound's
 *  language (signs, foreign dialogue), else none. */
function pickSub(f: FileInfo, audio: number): SubtitleTrack | null {
  const subs = f.subtitles ?? [];
  if (!subs.length) return null;
  const lang = prefs.subLang;
  if (lang === "") return null;
  if (lang) {
    const t = subs.find((s) => s.language === lang && !s.forced && !s.image) ?? subs.find((s) => s.language === lang && !s.forced);
    if (t) return t;
  }
  const audioLang = f.audio_tracks?.find((t) => t.index === audio)?.language;
  return subs.find((s) => s.forced && !s.image && (!audioLang || s.language === audioLang)) ?? null;
}
