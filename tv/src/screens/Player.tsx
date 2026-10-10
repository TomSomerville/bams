import { useCallback, useEffect, useRef, useState } from "react";
import { apiFor, mediaFor, refreshTicket, type FileInfo, type ItemDetail, type SubtitleTrack } from "../api";
import { useNav } from "../App";
import { AvplayEngine, hasAvplay, VideoEngine, type Engine } from "../engine";
import { clock, sxe } from "../format";
import Icon from "../Icon";
import { setKeyHandler } from "../keys";
import { focus, focusFirst } from "../nav";
import { pickAudio, pickFile, plan, type Mode } from "../plan";
import { prefs, setPref } from "../prefs";
import { isBack, KEY } from "../tizen";

type Cue = { start: number; end: number; text: string };

const OSD_HIDE = 5000;   // ms without a key before the controls fade while playing
const SEEK_SETTLE = 700; // ms after the last left/right press before the seek is made
const UP_NEXT = 10;      // seconds before the next episode starts by itself

/** The player: the file as-is when the TV can (AVPlay decodes MKV/HEVC/AC3...), else an HLS session from the
 *  server (sound converted, or everything converted). Saves the position like the web player does.
 *  `rid`: the item is on another of this TV's servers (api.ts); everything then goes to that one. */
export default function Player({ id, resume, rid }: { id: number; resume: boolean; rid?: number }) {
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
  const [buffering, setBuffering] = useState(true);
  const [osd, setOsd] = useState(true);
  const [menu, setMenu] = useState<"audio" | "subs" | null>(null);
  const [seekTo, setSeekTo] = useState<number | null>(null);
  const [upNext, setUpNext] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [subDelay, setSubDelay] = useState(prefs.subDelay);

  // what callbacks need without re-binding
  const st = useRef({ file: null as FileInfo | null, audio: 0, sub: null as SubtitleTrack | null, mode: null as Mode | null,
    session: null as string | null, started: false, startAt: 0, fellBack: false, duration: null as number | null,
    item: null as ItemDetail | null, seek: null as number | null, ended: false });
  const timers = useRef<{ osd?: ReturnType<typeof setTimeout>; seek?: ReturnType<typeof setTimeout>; next?: ReturnType<typeof setInterval> }>({});

  const duration = (): number | null => st.current.duration ?? engine.current?.duration() ?? null;

  const report = useCallback((keepalive = false, position?: number) => {
    const e = engine.current;
    if (!e || !st.current.started) return;
    const pos = position ?? e.time();
    void api.put(`/api/items/${id}/progress`, { position: pos, duration: duration() }, keepalive).catch(() => undefined);
  }, [id]);

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
        const r = await api.post<{ id: string; playlist: string }>(f.playback.hls_url, {
          remux: how.mode !== "convert", ts: true, passthrough: hasAvplay(), audio: s.audio, channels: 6, start: at,
          burn: burn ?? undefined,
        });
        s.session = r.id;
        url = media(r.playlist);
        hls = true;
      }
      if (!url) throw new Error("No address to play.");
      await e.load(url, at, hls);
      if (how.mode === "direct" && !cut && (f.audio_tracks?.length ?? 0) > 1 && !e.selectAudio(s.audio) && s.audio !== 0) {
        return void begin(at, "remux");  // this player can't switch tracks itself: the server picks it
      }
      setPaused(false);
    } catch (err) {
      fail((err as Error).message);
    }
  }, []);

  /** Something went wrong: fall back to the server converting everything once, else show the error. */
  const fail = (msg: string) => {
    const s = st.current;
    if (s.mode !== "convert" && !s.fellBack) {
      s.fellBack = true;
      const at = engine.current?.time() || s.startAt;
      return void begin(at > 0 ? at : s.startAt, "convert");
    }
    setBuffering(false);
    setError(msg || "This video couldn't be played.");
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
        const next = st.current.item?.next_id;
        if (next) setUpNext(UP_NEXT);
        else nav.back();
      },
      onError: (m: string) => fail(m),
      onBuffering: (b: boolean) => setBuffering(b),
    };
    engine.current = hasAvplay() ? new AvplayEngine(ev) : new VideoEngine(videoRef.current!, ev);
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
      const at = resume ? d.progress?.position ?? 0 : 0;
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

  // the controls fade while playing
  const wake = useCallback(() => {
    setOsd(true);
    clearTimeout(timers.current.osd);
    timers.current.osd = setTimeout(() => {
      if (engine.current && !engine.current.paused() && !document.querySelector("[data-trap]")) setOsd(false);
    }, OSD_HIDE);
  }, []);
  useEffect(() => { wake(); }, [wake]);

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
    const next = st.current.item?.next_id;
    if (next) nav.replace({ name: "player", id: next, rid, resume: true });
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
      if (error) {
        if (isBack(e) || k === KEY.ENTER) { nav.back(); return true; }
        return false;
      }
      if (menu) {
        if (isBack(e)) { setMenu(null); setTimeout(() => focus(document.querySelector<HTMLElement>(`[data-fid="osd-${menu}"]`))); return true; }
        return false;  // arrows and OK move within the menu
      }
      wake();
      const inButtons = !!(document.activeElement as HTMLElement | null)?.closest(".osd-buttons");
      switch (k) {
        case KEY.PLAY_PAUSE: toggle(); return true;
        case KEY.PLAY: if (engine.current?.paused()) toggle(); return true;
        case KEY.PAUSE: if (!engine.current?.paused()) toggle(); return true;
        case KEY.STOP: nav.back(); return true;
        case KEY.FF: seekBy(30); return true;
        case KEY.RW: seekBy(-10); return true;
        case KEY.NEXT: if (st.current.item?.next_id) playNext(); return true;
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
      if (k === KEY.UP) { (document.activeElement as HTMLElement).blur(); return true; }
      return false;  // left/right/OK among the buttons
    });
    return () => setKeyHandler(null);
  });

  const now = seekTo ?? time;
  const dur = duration();
  const subNow = now - subDelay;  // shown later by the timing set in the menu
  const cue = cues.length ? cues.find((c) => subNow >= c.start && subNow <= c.end) : undefined;
  const show = item?.ancestors.find((a) => a.kind === "show");
  const title = show ? show.title : item?.title ?? "";
  const subtitle = item?.kind === "episode" ? `${sxe(item)} · ${item.title}` : null;

  return (
    <div className={`player ${osd ? "" : "hide-cursor"}`}>
      {hasAvplay() ? <object className="avplayer" type="application/avplayer" /> : <video ref={videoRef} className="video" />}

      {cue && <div className={`subtitle ${osd ? "raised" : ""}`} dangerouslySetInnerHTML={{ __html: cue.text }} />}
      {buffering && !error && <div className="player-center"><div className="spinner" /></div>}
      {paused && !osd && <div className="player-center"><Icon name="pause" size={120} /></div>}

      <div className={`osd ${osd ? "on" : ""}`}>
        <div className="osd-top">
          <h1>{title}</h1>
          {subtitle && <div className="osd-sub">{subtitle}</div>}
        </div>
        <div className="osd-bottom">
          <div className="scrub">
            <span>{clock(now)}</span>
            <div className="scrub-bar">
              <div className="scrub-fill" style={{ width: dur ? `${Math.min(100, (now / dur) * 100)}%` : "0%" }} />
            </div>
            <span>{clock(dur)}</span>
          </div>
          <div className="osd-buttons">
            <button className="round" data-fid="osd-play" onClick={toggle}><Icon name={paused ? "play" : "pause"} /></button>
            <button className="round" data-fid="osd-back" onClick={() => seekBy(-10)}><Icon name="back10" /></button>
            <button className="round" data-fid="osd-fwd" onClick={() => seekBy(30)}><Icon name="fwd30" /></button>
            {(file?.audio_tracks?.length ?? 0) > 1 && (
              <button className="pill" data-fid="osd-audio" onClick={() => setMenu("audio")}><Icon name="audio" /> Sound</button>
            )}
            {!!file?.subtitles?.length && (
              <button className="pill" data-fid="osd-subs" onClick={() => setMenu("subs")}><Icon name="subs" /> Subtitles</button>
            )}
            {item?.next_id && <button className="pill" data-fid="osd-next" onClick={playNext}><Icon name="next" /> Next episode</button>}
            <span className="osd-mode">{mode === "direct" ? "Playing as-is" : mode === "remux" ? "Video as-is, sound converted" : mode === "convert" ? "Converted by the server" : ""}</span>
          </div>
          <div className="osd-hint">◀ ▶ skip back 10 s / ahead 30 s · OK pause · ▲▼ controls</div>
        </div>
      </div>

      {menu && file && (
        <Menu title={menu === "audio" ? "Sound" : "Subtitles"}
          extra={menu === "subs" && sub && !sub.image ? (
            <div className="menu-timing">
              <span>Timing</span>
              <button className="pill" onClick={() => { const v = Math.round((subDelay - 0.1) * 10) / 10; setSubDelay(v); setPref("subDelay", v); }}>Earlier</button>
              <strong>{subDelay === 0 ? "0.0 s" : `${subDelay > 0 ? "+" : ""}${subDelay.toFixed(1)} s`}</strong>
              <button className="pill" onClick={() => { const v = Math.round((subDelay + 0.1) * 10) / 10; setSubDelay(v); setPref("subDelay", v); }}>Later</button>
            </div>
          ) : null}
          options={menu === "audio"
            ? (file.audio_tracks ?? []).map((t) => ({ key: `a${t.index}`, label: t.label, on: t.index === audio, pick: () => chooseAudio(t.index) }))
            : [{ key: "off", label: "Off", on: !sub, pick: () => chooseSub(null) },
              ...(file.subtitles ?? []).map((t) => ({ key: t.id, label: t.label + (t.image ? " (the server converts the video)" : ""),
                on: sub?.id === t.id, pick: () => chooseSub(t) }))]} />
      )}

      {upNext !== null && item?.next_id && (
        <div className="upnext" data-trap>
          <h2>Next episode in {upNext}</h2>
          <div className="button-row">
            <button className="btn primary" ref={(b) => b?.focus()} onClick={playNext}><Icon name="play" size={30} /> Play now</button>
            <button className="btn" onClick={() => nav.back()}>Back</button>
          </div>
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

function Menu({ title, options, extra }: { title: string; extra?: React.ReactNode;
  options: { key: string; label: string; on: boolean; pick: () => void }[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setTimeout(() => focus(ref.current?.querySelector<HTMLElement>(".on") ?? ref.current?.querySelector("button")));
  }, []);
  return (
    <div className="menu" data-trap ref={ref}>
      <h2>{title}</h2>
      {extra}
      <div className="menu-list" data-scroll>
        {options.map((o) => (
          <button key={o.key} className={`menu-item ${o.on ? "on" : ""}`} onClick={o.pick}>
            <span className="tick">{o.on ? "✓" : ""}</span>{o.label}
          </button>
        ))}
      </div>
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

/** WebVTT -> cues. Keeps <i>/<b>, drops other markup. */
function parseVtt(text: string): Cue[] {
  const out: Cue[] = [];
  const t = (s: string) => {
    const p = s.trim().split(":").map(Number);
    return p.length === 3 ? p[0] * 3600 + p[1] * 60 + p[2] : p[0] * 60 + p[1];
  };
  for (const block of text.replace(/\r/g, "").split(/\n\n+/)) {
    const lines = block.split("\n");
    const i = lines.findIndex((l) => l.includes("-->"));
    if (i < 0) continue;
    const [a, b] = lines[i].split("-->");
    const body = lines.slice(i + 1).join("<br>")
      .replace(/<(?!\/?(i|b|br)>)[^>]*>/g, "")
      .replace(/&(?!(amp|lt|gt|nbsp);)/g, "&amp;");
    if (body.trim()) out.push({ start: t(a), end: t(b.trim().split(/\s/)[0]), text: body });
  }
  return out;
}
