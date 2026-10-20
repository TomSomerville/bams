// PC keyboards and USB remotes (theatre mode, and a browser in development). The screens know the Samsung remote's
// key codes (tizen.ts KEY); a PC sends other keys for the same buttons (BrowserBack, MediaPlayPause, a Media Center
// remote's Ctrl+P…). Each is turned into the code the screens already handle, as one keydown on the focused element
// (like the Fire TV bridge does, firetv.ts), so no screen needs to know about PCs. Keys a browser would act on
// itself (going back, printing, finding) are stopped first. Escape and Backspace are Back already (tizen.ts isBack).
// Also: type-to-search, media keys that the browser hands to the Media Session, and the browser's own Back.
// Tests: tv/test/pckeys.test.ts.

import { KEY } from "./tizen";

/** Fired on window: open Search with this text (`detail`: the letter typed, or "" for the Search key). */
export const SEARCH = "bams:search";
/** Fired on window: go Home. */
export const HOME = "bams:home";

const plain: Record<string, number> = {
  BrowserBack: KEY.BACK, GoBack: KEY.BACK,
  MediaPlayPause: KEY.PLAY_PAUSE, MediaPlay: KEY.PLAY, MediaPause: KEY.PAUSE, MediaStop: KEY.STOP,
  MediaTrackNext: KEY.NEXT, MediaTrackPrevious: KEY.PREV, MediaFastForward: KEY.FF, MediaRewind: KEY.RW,
};

// Windows Media Center remotes (and keyboards made like them) send their transport buttons as shortcuts
const mediaCenter: Record<string, number> = {
  "c+p": KEY.PAUSE, "cs+p": KEY.PLAY, "cs+s": KEY.STOP, "c+f": KEY.NEXT, "c+b": KEY.PREV,
  "cs+f": KEY.FF, "cs+b": KEY.RW,
};

const typing = (el: Element | null) => !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA");
const inPlayer = () => !!document.querySelector(".player");

/** Press `code` as the Samsung remote would: a keydown on the focused element, bubbling to App.tsx's listener. */
export function press(code: number) {
  const el = (document.activeElement ?? document.body) as HTMLElement;
  const ev = new KeyboardEvent("keydown", { bubbles: true, cancelable: true });
  Object.defineProperty(ev, "keyCode", { get: () => code });
  Object.defineProperty(ev, "which", { get: () => code });
  el.dispatchEvent(ev);
}

/** What a PC key means here: a remote code to press, an action, or null (leave it to the page as it is). */
export function translate(e: KeyboardEvent): { code: number } | { action: "home" | "menu" } | { search: string } | null {
  const k = e.key;  // our own presses carry only a keyCode (no key), so they never come back here
  if (k in plain) return { code: plain[k] };
  if (e.ctrlKey && !e.altKey && !e.metaKey && k.length === 1) {
    const code = mediaCenter[`${e.shiftKey ? "cs" : "c"}+${k.toLowerCase()}`];
    if (code) return { code };
  }
  if (k === "BrowserHome") return { action: "home" };
  if (k === "ContextMenu") return { action: "menu" };
  if (k === "BrowserSearch") return { search: "" };
  if (typing(e.target as Element) || typing(document.activeElement)) return null;
  if (k === " " && inPlayer()) return { code: KEY.PLAY_PAUSE };
  // type-to-search: a letter or digit, not a shortcut, not in the player or a menu
  if (/^[\p{L}\p{N}]$/u.test(k) && !e.ctrlKey && !e.altKey && !e.metaKey && !inPlayer()
      && !document.querySelector("[data-trap]")) return { search: k };
  return null;
}

/** What a translation means, in words (Settings → Remote test). */
export function meaning(t: ReturnType<typeof translate>): string {
  if (!t) return "used as it is";
  if ("search" in t) return "Search";
  if ("action" in t) return t.action === "home" ? "Home" : "the card's menu (like holding OK)";
  const names: Record<number, string> = { [KEY.BACK]: "Back", [KEY.PLAY_PAUSE]: "Play/pause", [KEY.PLAY]: "Play",
    [KEY.PAUSE]: "Pause", [KEY.STOP]: "Stop", [KEY.NEXT]: "Next", [KEY.PREV]: "Previous", [KEY.FF]: "Fast forward",
    [KEY.RW]: "Rewind" };
  return names[t.code] ?? `key ${t.code}`;
}

/** Settings → Remote test: sees every key first, with what it means here. */
let watcher: ((e: KeyboardEvent, means: string) => void) | null = null;
export function watchKeys(fn: typeof watcher) {
  watcher = fn;
}

function onKey(e: KeyboardEvent) {
  const t = translate(e);
  if (e.key) watcher?.(e, meaning(t));  // not our own presses (keyCode only)
  if (!t) return;
  e.preventDefault();
  e.stopImmediatePropagation();
  if ("code" in t) press(t.code);
  else if ("search" in t) window.dispatchEvent(new CustomEvent(SEARCH, { detail: t.search }));
  else if (t.action === "home") window.dispatchEvent(new Event(HOME));
  else {
    // the focused card's hold menu (as holding OK, or a right-click)
    const el = document.activeElement as HTMLElement | null;
    if (el?.hasAttribute("data-hold")) el.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true }));
  }
}

let installed = false;

/** Start listening (PCs only; App.tsx). */
export function installPcKeys() {
  if (installed) return;
  installed = true;
  window.addEventListener("keydown", onKey, true);  // capture: before App.tsx's listener and the browser
  // Chrome and Edge hand media keys to the Media Session (while media plays) instead of sending key events
  const ms = (navigator as Navigator & { mediaSession?: MediaSession }).mediaSession;
  if (ms) {
    const set = (a: MediaSessionAction, code: number) => {
      try {
        ms.setActionHandler(a, () => press(code));
      } catch { /* action not supported by this browser */ }
    };
    set("play", KEY.PLAY);
    set("pause", KEY.PAUSE);
    set("stop", KEY.STOP);
    set("nexttrack", KEY.NEXT);
    set("previoustrack", KEY.PREV);
    set("seekforward", KEY.FF);
    set("seekbackward", KEY.RW);
  }
  // The browser's own Back (its toolbar button, a mouse's back button, Alt+Left) would leave the page: keep spare
  // history entries above it, and treat going back onto one below as the remote's Back. Chrome's back button skips
  // entries a page added without a key press or click (its "history manipulation intervention"): added at load or
  // inside popstate they were skipped, and Back jumped past BAMS to the page before. So they're only ever added
  // during a key press or click, TRAP_DEPTH of them, so a few Backs in a row stay inside BAMS too.
  try {
    let spare = 0;  // our entries above where we are
    const arm = () => {
      for (; spare < TRAP_DEPTH; spare++) history.pushState({ bams: true }, "");
    };
    window.addEventListener("keydown", arm, true);
    window.addEventListener("pointerdown", arm, true);
    window.addEventListener("popstate", () => {
      spare = Math.max(0, spare - 1);
      press(KEY.BACK);
    });
  } catch { /* no history API: nothing to catch */ }
}

/** Spare history entries kept above the page (see installPcKeys). */
export const TRAP_DEPTH = 3;
