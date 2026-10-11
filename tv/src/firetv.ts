// Fire TV bits. On a Fire TV (Fire OS = Android) this same app runs in a WebView inside the Android app in firetv/.
// That app adds `window.BamsAndroid` (a Java object: device info, leaving the app, the native video player) and
// talks back by calling `window.bamsHost(event)`: remote keys the WebView doesn't pass on (Back, media keys) and the
// player's events. Everything here is a no-op in a browser and on a Samsung TV.
// Android side: firetv/app/src/main/java/media/bams/firetv/ (Bridge.kt, Video.kt, Caps.kt).

/** What the Fire TV decodes, from Android's codec list (Caps.kt). Video codecs are BAMS probe names ("HEVC"), with
 *  the largest picture the decoder takes; audio: names it decodes or can hand to the TV/receiver as-is. */
export type FireCaps = {
  video: Record<string, { w: number; h: number }>;
  audio: string[];
  h264HighBit: boolean;
  dvProfile5: boolean;
};

export type FireInfo = { model: string; name: string; version: string; ip: string | null; caps: FireCaps };

/** A player event from Video.kt, for the load with this `id`. Times in seconds. */
export type FirePlayerEvent = { id: number } & (
  | { type: "ready" }
  | { type: "time"; t: number; d: number | null; paused: boolean }
  | { type: "buffering"; on: boolean }
  | { type: "ended" }
  | { type: "error"; message: string });

type HostEvent = { type: "key"; code: number } | { type: "player"; event: FirePlayerEvent };

/* eslint-disable @typescript-eslint/no-explicit-any */
declare global {
  interface Window {
    BamsAndroid?: {
      info(): string;
      exit(): void;
      /** a tap at this point of the page (fractions of its width and height): opens the keyboard on a text box */
      showKeyboard(x: number, y: number): void;
      load(url: string, startMs: number, hls: boolean, id: number): void;
      play(): void;
      pause(): void;
      seek(ms: number): void;
      stop(): void;
      selectAudio(n: number): boolean;
    };
    bamsHost?: (e: HostEvent) => void;
  }
}

export const onFireTv = () => typeof window.BamsAndroid !== "undefined";

let info: { from: unknown; info: FireInfo } | null = null;

/** The device and what it decodes (asked once: reading Android's decoders takes a moment). */
export function fireInfo(): FireInfo | null {
  const bridge = window.BamsAndroid;
  if (!bridge) return null;
  if (info?.from !== bridge) {
    try {
      info = { from: bridge, info: JSON.parse(bridge.info()) as FireInfo };
    } catch {
      return null;
    }
  }
  return info.info;
}

let playerListener: ((e: FirePlayerEvent) => void) | null = null;

/** Where the native player's events go (one player at a time). */
export function onFirePlayer(fn: ((e: FirePlayerEvent) => void) | null) {
  playerListener = fn;
}

/** A key from the Android side, given to the app as if the WebView had sent it: one keydown on the focused element
 *  (bubbling up to App.tsx's listener on window), with the Samsung key code the app already knows. OK on a text box
 *  opens the on-screen keyboard instead, by having Android tap the box: the WebView opens a working keyboard only for
 *  a touch (asked for directly, Fire TV's keyboard flashed up and closed, and the box lost the focus). The keyboard's
 *  own Next/Done key reaches the page natively and sends the form. */
function pressKey(code: number) {
  const el = (document.activeElement ?? document.body) as HTMLElement;
  if (code === 13 && (el.tagName === "INPUT" || el.tagName === "TEXTAREA")) {
    const r = el.getBoundingClientRect();
    window.BamsAndroid?.showKeyboard((r.left + r.width / 2) / window.innerWidth, (r.top + r.height / 2) / window.innerHeight);
    return;
  }
  const ev = new KeyboardEvent("keydown", { bubbles: true, cancelable: true });
  Object.defineProperty(ev, "keyCode", { get: () => code });
  Object.defineProperty(ev, "which", { get: () => code });
  el.dispatchEvent(ev);
}

// only the Android side (and the tests) call it; harmless elsewhere
window.bamsHost = (e) => {
  if (e.type === "key") pressKey(e.code);
  else if (e.type === "player") playerListener?.(e.event);
};
