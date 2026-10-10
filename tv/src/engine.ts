// Two ways to play video behind one interface:
// - AVPlay, Samsung's native player (webapis.avplay): hardware decoding of what the TV supports (MKV, HEVC, AC3...),
//   drawn on the video layer under the page through an <object type="application/avplayer">.
// - <video> (+ hls.js for HLS), for developing in a browser, and on a TV without AVPlay.
// Times are in seconds everywhere outside this file.

import Hls from "hls.js";
import { onTv } from "./tizen";

export type EngineEvents = {
  onTime: (t: number) => void;
  onEnd: () => void;
  onError: (msg: string) => void;
  onBuffering: (b: boolean) => void;
};

export interface Engine {
  readonly kind: "avplay" | "video";
  load(url: string, start: number, hls: boolean): Promise<void>;
  play(): void;
  pause(): void;
  paused(): boolean;
  seek(t: number): Promise<void>;
  time(): number;
  duration(): number | null;
  /** Switch to the n-th audio track of the file being played as-is. False if this player can't. */
  selectAudio(n: number): boolean;
  stop(): void;
  destroy(): void;
}

export const hasAvplay = () => onTv() && !!window.webapis?.avplay;

// ---------------------------------------------------------------- AVPlay

export class AvplayEngine implements Engine {
  readonly kind = "avplay";
  private av = window.webapis.avplay;
  private state: "idle" | "ready" | "playing" | "paused" = "idle";
  private t = 0;
  private onVis = () => {
    try {
      if (document.hidden) this.av.suspend();
      else this.av.restore();
    } catch { /* not open */ }
  };

  constructor(private ev: EngineEvents) {
    document.addEventListener("visibilitychange", this.onVis);
  }

  async load(url: string, start: number): Promise<void> {
    this.stop();
    const av = this.av;
    av.open(url);
    av.setDisplayRect(0, 0, 1920, 1080);  // AVPlay always counts in 1920x1080, whatever the panel
    try {
      av.setDisplayMethod("PLAYER_DISPLAY_MODE_LETTER_BOX");
    } catch { /* older firmware: default is fine */ }
    av.setListener({
      onbufferingstart: () => this.ev.onBuffering(true),
      onbufferingcomplete: () => this.ev.onBuffering(false),
      oncurrentplaytime: (ms: number) => {
        this.t = ms / 1000;
        this.ev.onTime(this.t);
      },
      onstreamcompleted: () => {
        this.state = "paused";
        this.ev.onEnd();
      },
      onerror: (type: string) => this.ev.onError(String(type)),
      onevent: () => undefined,
      onsubtitlechange: () => undefined,
      ondrmevent: () => undefined,
    });
    this.ev.onBuffering(true);
    await new Promise<void>((resolve, reject) => av.prepareAsync(resolve, (e: unknown) => reject(new Error(String((e as { name?: string })?.name ?? e)))));
    this.state = "ready";
    if (start > 1) await this.seek(start);
    this.t = start;
    av.play();
    this.state = "playing";
  }

  play() {
    if (this.state === "idle") return;
    this.av.play();
    this.state = "playing";
  }

  pause() {
    if (this.state !== "playing") return;
    this.av.pause();
    this.state = "paused";
  }

  paused() {
    return this.state !== "playing";
  }

  seek(t: number): Promise<void> {
    return new Promise((resolve) => {
      try {
        this.av.seekTo(Math.max(0, Math.floor(t * 1000)), () => {
          this.t = t;
          resolve();
        }, () => resolve());
      } catch {
        resolve();
      }
    });
  }

  time() {
    try {
      const ms = this.av.getCurrentTime();
      if (typeof ms === "number" && ms > 0) this.t = ms / 1000;
    } catch { /* keep the last one */ }
    return this.t;
  }

  duration() {
    try {
      const ms = this.av.getDuration();
      return ms > 0 ? ms / 1000 : null;
    } catch {
      return null;
    }
  }

  selectAudio(n: number): boolean {
    try {
      const tracks = (this.av.getTotalTrackInfo() as { index: number; type: string }[]).filter((x) => x.type === "AUDIO");
      if (!tracks[n]) return false;
      this.av.setSelectTrack("AUDIO", tracks[n].index);
      return true;
    } catch {
      return false;
    }
  }

  stop() {
    try {
      if (this.av.getState() !== "NONE") {
        this.av.stop();
        this.av.close();
      }
    } catch { /* already closed */ }
    this.state = "idle";
  }

  destroy() {
    this.stop();
    document.removeEventListener("visibilitychange", this.onVis);
  }
}

// ---------------------------------------------------------------- <video>

type HlsInstance = InstanceType<typeof Hls>;

export class VideoEngine implements Engine {
  readonly kind = "video";
  private hls: HlsInstance | null = null;
  private ended = () => this.ev.onEnd();
  private timeupdate = () => this.ev.onTime(this.v.currentTime);
  private waiting = () => this.ev.onBuffering(true);
  private playing = () => this.ev.onBuffering(false);
  private error = () => this.ev.onError(this.v.error?.message || `media error ${this.v.error?.code ?? ""}`);

  constructor(private v: HTMLVideoElement, private ev: EngineEvents) {
    v.addEventListener("ended", this.ended);
    v.addEventListener("timeupdate", this.timeupdate);
    v.addEventListener("waiting", this.waiting);
    v.addEventListener("playing", this.playing);
    v.addEventListener("canplay", this.playing);
    v.addEventListener("error", this.error);
  }

  async load(url: string, start: number, hls: boolean): Promise<void> {
    this.stop();
    const v = this.v;
    this.ev.onBuffering(true);
    if (hls && !v.canPlayType("application/vnd.apple.mpegurl")) {
      if (!Hls.isSupported()) throw new Error("This browser can't play HLS.");
      const h = new Hls({ startPosition: start, maxBufferLength: 30 });
      this.hls = h;
      h.on(Hls.Events.ERROR, (_e, d) => {
        if (d.fatal) this.ev.onError(`${d.type}: ${d.details}`);
      });
      h.loadSource(url);
      h.attachMedia(v);
    } else {
      v.src = url;
      if (start > 1) v.currentTime = start;
    }
    await v.play().catch(() => undefined);
  }

  play() { void this.v.play().catch(() => undefined); }
  pause() { this.v.pause(); }
  paused() { return this.v.paused; }

  seek(t: number): Promise<void> {
    this.v.currentTime = Math.max(0, t);
    return Promise.resolve();
  }

  time() { return this.v.currentTime; }
  duration() { return Number.isFinite(this.v.duration) && this.v.duration > 0 ? this.v.duration : null; }

  selectAudio(n: number): boolean {
    const tracks = (this.v as unknown as { audioTracks?: { length: number; [i: number]: { enabled: boolean } } }).audioTracks;
    if (!tracks || n >= tracks.length) return false;
    for (let i = 0; i < tracks.length; i++) tracks[i].enabled = i === n;
    return true;
  }

  stop() {
    this.hls?.destroy();
    this.hls = null;
    this.v.removeAttribute("src");
    this.v.load();
  }

  destroy() {
    this.stop();
    const v = this.v;
    v.removeEventListener("ended", this.ended);
    v.removeEventListener("timeupdate", this.timeupdate);
    v.removeEventListener("waiting", this.waiting);
    v.removeEventListener("playing", this.playing);
    v.removeEventListener("canplay", this.playing);
    v.removeEventListener("error", this.error);
  }
}
