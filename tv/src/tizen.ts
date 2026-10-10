// Samsung/Tizen bits: the remote's keys, device info, leaving the app. Everything here also works (as a no-op or
// a fallback) in an ordinary browser, where the app is developed.

/* eslint-disable @typescript-eslint/no-explicit-any */
declare global {
  interface Window {
    tizen?: any;
    webapis?: any;
  }
}

export const onTv = () => typeof window.tizen !== "undefined";

/** The remote's keys as keyCodes (Samsung TV key codes; arrows, OK and Back also map from a PC keyboard). */
export const KEY = {
  LEFT: 37, UP: 38, RIGHT: 39, DOWN: 40, ENTER: 13,
  BACK: 10009, ESC: 27, BACKSPACE: 8,
  PLAY_PAUSE: 10252, PLAY: 415, PAUSE: 19, STOP: 413, FF: 417, RW: 412, NEXT: 10233, PREV: 10232,
  RED: 403, GREEN: 404, YELLOW: 405, BLUE: 406, INFO: 457,
};

/** Back on the remote; Escape on a PC (Backspace too, but not while typing). */
export function isBack(e: KeyboardEvent): boolean {
  if (e.keyCode === KEY.BACK || e.keyCode === KEY.ESC) return true;
  const t = e.target as HTMLElement | null;
  return e.keyCode === KEY.BACKSPACE && !(t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA"));
}

/** Without this, the media and colour keys go to the TV instead of the app. */
export function registerKeys() {
  const keys = ["MediaPlayPause", "MediaPlay", "MediaPause", "MediaStop", "MediaFastForward", "MediaRewind",
    "MediaTrackNext", "MediaTrackPrevious", "ColorF0Red", "ColorF1Green", "ColorF2Yellow", "ColorF3Blue", "Info"];
  try {
    const dev = window.tizen?.tvinputdevice;
    if (!dev) return;
    const supported = new Set((dev.getSupportedKeys() as { name: string }[]).map((k) => k.name));
    for (const k of keys) if (supported.has(k)) dev.registerKey(k);
  } catch { /* not a TV, or the privilege is missing: the keys just don't reach the app */ }
}

export function exitApp() {
  try {
    window.tizen?.application.getCurrentApplication().exit();
  } catch { /* in a browser there's nothing to leave */ }
}

/** What to call this TV when linking it ("Samsung QN50LS03B"). */
export function deviceName(): string {
  try {
    const model = window.webapis?.productinfo?.getRealModel?.() || window.webapis?.productinfo?.getModel?.();
    if (model) return `Samsung ${model}`;
  } catch { /* fall through */ }
  return onTv() ? "Samsung TV" : "Browser";
}

const isIp = (ip: unknown): ip is string => typeof ip === "string" && /^\d+\.\d+\.\d+\.\d+$/.test(ip) && ip !== "0.0.0.0";

/** The TV's own address on the network ("192.168.1.42"), to look for servers next to it: Samsung's network API,
 *  else Tizen's system info (wired, then Wi-Fi). Null when neither says. */
export async function localIp(): Promise<string | null> {
  try {
    const ip = window.webapis?.network?.getIp?.();
    if (isIp(ip)) return ip;
  } catch { /* no Samsung network API (or no privilege) */ }
  const si = window.tizen?.systeminfo;
  if (!si) return null;
  for (const prop of ["ETHERNET_NETWORK", "WIFI_NETWORK"]) {
    const ip = await new Promise<string | null>((resolve) => {
      try {
        si.getPropertyValue(prop, (v: { ipAddress?: string }) => resolve(v?.ipAddress ?? null), () => resolve(null));
      } catch {
        resolve(null);
      }
      setTimeout(() => resolve(null), 2000);
    });
    if (isIp(ip)) return ip;
  }
  return null;
}

export const appVersion = (): string => {
  try {
    return window.tizen?.application.getCurrentApplication().appInfo.version ?? "dev";
  } catch {
    return "dev";
  }
};
