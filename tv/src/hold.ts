// Holding OK on the remote. On an element marked [data-hold] (a Continue Watching card), a long press sends it a
// "contextmenu" event (React's onContextMenu, the same as a right-click in a browser) instead of a click; its click
// waits until it's clear OK wasn't held. Everything else is clicked on the key-down, as before (App.tsx).
//
// Remotes differ: a Samsung TV (and a PC keyboard) sends a key-up when OK is let go, and may repeat key-downs while
// it's held; the Fire TV app passes only key-downs on (firetv.ts), repeated while held. So: a key-up before HOLD_MS
// is a press; repeated key-downs are a hold; no key-up by then is a hold once this remote has shown it sends them,
// else (no key-ups, no repeats: the Fire TV) a press. Tests: tv/test/hold.test.ts.

export const HOLD_MS = 800;   // held this long (with key-ups) = a long press
const NO_UP_WAIT = 600;       // without key-ups: the remote repeats a held key well before this (Android: 500 ms)
const REPEAT_GAP = 300;       // key-downs closer than this are a held key repeating

let pending: { el: HTMLElement; repeats: number; timer: ReturnType<typeof setTimeout> } | null = null;
let sendsUps = false;   // this remote sends a key-up for OK
let held = false;       // a long press fired: OK's key-downs are its repeats until it's let go
let lastDown = 0;

function longPress(el: HTMLElement) {
  held = true;
  el.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true }));
}

/** OK went down. True when it was taken care of here (the caller does nothing more with it). */
export function okDown(e: KeyboardEvent): boolean {
  const t = performance.now();
  const gap = t - lastDown;
  lastDown = t;
  if (pending) {
    pending.repeats++;
    return true;
  }
  if (held) {
    if (e.repeat || gap < REPEAT_GAP) return true;  // still held after the long press: nothing under it is pressed
    held = false;
  }
  const el = document.activeElement as HTMLElement | null;
  if (!el || !el.hasAttribute("data-hold")) return false;
  const p = {
    el, repeats: 0,
    timer: setTimeout(() => {
      pending = null;
      if (p.repeats > 0 || sendsUps) longPress(el);
      else el.click();
    }, sendsUps ? HOLD_MS : NO_UP_WAIT),
  };
  pending = p;
  return true;
}

/** OK was let go. */
export function okUp() {
  sendsUps = true;
  held = false;
  if (!pending) return;
  clearTimeout(pending.timer);
  const el = pending.el;
  pending = null;
  el.click();
}

/** Back to a fresh start (tests). */
export function resetHold(ups = false) {
  if (pending) clearTimeout(pending.timer);
  pending = null;
  sendsUps = ups;
  held = false;
  lastDown = 0;
}
