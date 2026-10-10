// Moving around with the remote's arrows ("spatial navigation"): from the focused element, the nearest focusable
// element in that direction gets the focus. Focusable = <button>, <input>, or anything with [data-focus], that is
// visible. A [data-row] container (a shelf of posters) remembers where its focus was, so going down and back up
// returns to the same poster rather than the nearest one.
//
// Menus: a [data-group] is a set of controls of its own (the rail, the music bar); arriving in one lands on its
// [data-entry] if it has one, and Left/Right inside it stay in it (or go to the rail). The rail is also [data-side]:
// the column on the left. Only Left enters it, Up/Down stay in it, and Right leaves it for the element the focus
// came from. A [data-cover] bar lies over the bottom of the page (the music bar): the page scrolls things above it.
// Tests: tv/test/nav.test.ts (npm test).

export type Dir = "left" | "right" | "up" | "down";

const SELECTOR = "button:not([disabled]), input, [data-focus]";
const SIDE = "[data-side]";
const GROUP = "[data-group]";
const rowMemory = new WeakMap<Element, HTMLElement>();
/** the last element focused outside the rail: where Right from the rail goes back to */
let lastContent: HTMLElement | null = null;

// however an element got the focus (a move, a click, a screen's ref.focus()): remember it for its row / the rail
document.addEventListener("focusin", (e) => {
  const el = e.target;
  if (!(el instanceof HTMLElement)) return;
  const row = el.closest("[data-row]");
  if (row) rowMemory.set(row, el);
  if (!el.closest(SIDE)) lastContent = el;
});

function visible(el: HTMLElement): boolean {
  if (el.offsetParent === null && getComputedStyle(el).position !== "fixed") return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
}

export function focusables(root: ParentNode = document): HTMLElement[] {
  // a modal layer ([data-trap]) keeps the focus inside itself
  const traps = document.querySelectorAll<HTMLElement>("[data-trap]");
  const scope = traps.length ? traps[traps.length - 1] : root;
  return Array.from(scope.querySelectorAll<HTMLElement>(SELECTOR)).filter(visible);
}

export function focus(el: HTMLElement | null | undefined): boolean {
  if (!el) return false;
  el.focus({ preventScroll: true });
  reveal(el);
  const row = el.closest("[data-row]");
  if (row) rowMemory.set(row, el);
  return true;
}

/** Scroll the focused element into view: shelves scroll sideways, the page (and the rail) scroll to keep it
 *  comfortably inside, above a [data-cover] bar. */
function reveal(el: HTMLElement) {
  const row = el.closest<HTMLElement>("[data-row]");
  if (row) {
    const r = el.getBoundingClientRect();
    const box = row.getBoundingClientRect();
    const pad = 80;
    if (r.left < box.left + pad) row.scrollLeft -= box.left + pad - r.left;
    else if (r.right > box.right - pad) row.scrollLeft += r.right - (box.right - pad);
  }
  const page = el.closest<HTMLElement>("[data-scroll]");
  if (page) {
    const r = el.getBoundingClientRect();
    const box = page.getBoundingClientRect();
    let end = box.bottom;
    for (const c of Array.from(document.querySelectorAll<HTMLElement>("[data-cover]"))) {
      if (c.contains(el) || page.contains(c) || !visible(c)) continue;
      const cb = c.getBoundingClientRect();
      if (cb.left < box.right && cb.right > box.left && cb.top < end) end = Math.max(box.top + box.height / 2, cb.top);
    }
    const top = box.top + (end - box.top) * 0.28;
    const bottom = end - 60;
    if (r.top < top) page.scrollTop -= top - r.top;
    else if (r.bottom > bottom) page.scrollTop += r.bottom - bottom;
  }
}

const usable = (el: HTMLElement | null, all: HTMLElement[]): el is HTMLElement => !!el && el.isConnected && all.includes(el);

/** Where the focus starts when there's none (or it was on something that's gone): the page, not the rail. */
function start(all: HTMLElement[]): boolean {
  if (document.querySelector("[data-trap]")) return focus(all[0]);
  const main = document.querySelector("main");
  if (main && focusFirst(main)) return true;
  return focus(all.find((el) => !el.closest(SIDE)) ?? all[0]);
}

/** The nearest of `all` from `cur` in `dir` (null: nothing that way). `level`: sideways only to things level with it. */
function nearest(cur: HTMLElement, dir: Dir, all: HTMLElement[], level = true): HTMLElement | null {
  const a = cur.getBoundingClientRect();
  const ax = a.left + a.width / 2, ay = a.top + a.height / 2;
  const curRow = cur.closest("[data-row]");
  const inSide = !!cur.closest(SIDE);
  let best: HTMLElement | null = null;
  let bestScore = Infinity;
  for (const el of all) {
    if (el === cur) continue;
    const b = el.getBoundingClientRect();
    const bx = b.left + b.width / 2, by = b.top + b.height / 2;
    let primary: number, secondary: number;
    // sideways only to things level with this one (at the end of a short shelf, Right does nothing rather than
    // dropping into the shelf below); the rail counts as level with everything beside it
    const lv = !level || (b.bottom > a.top + 4 && b.top < a.bottom - 4) || (!inSide && !!el.closest(SIDE));
    switch (dir) {
      case "right": if (!lv || (b.left < a.right - 4 && bx <= ax + 4)) continue; primary = Math.max(0, b.left - a.right); secondary = Math.abs(by - ay); break;
      case "left": if (!lv || (b.right > a.left + 4 && bx >= ax - 4)) continue; primary = Math.max(0, a.left - b.right); secondary = Math.abs(by - ay); break;
      case "down": if (b.top < a.bottom - 4 && by <= ay + 4) continue; primary = Math.max(0, b.top - a.bottom); secondary = Math.abs(bx - ax); break;
      case "up": if (b.bottom > a.top + 4 && by >= ay - 4) continue; primary = Math.max(0, a.top - b.bottom); secondary = Math.abs(bx - ax); break;
    }
    // sideways moves stay in their row when they can
    const sameRow = curRow && el.closest("[data-row]") === curRow;
    const score = primary + secondary * (dir === "left" || dir === "right" ? (sameRow ? 0.5 : 3) : 1.2);
    if (score < bestScore) {
      bestScore = score;
      best = el;
    }
  }
  return best;
}

/** Move the focus one step in `dir`. False when there's nothing that way (the caller may do something else). */
export function move(dir: Dir): boolean {
  const all = focusables();
  const cur = document.activeElement as HTMLElement | null;
  if (!cur || !all.includes(cur)) return start(all);
  const side = cur.closest(SIDE);
  const group = cur.closest(GROUP);
  const sideways = dir === "left" || dir === "right";

  if (side) {
    // the rail: Up/Down within it; Right back to where the focus came from, else the nearest thing on the page
    if (!sideways) return focus(nearest(cur, dir, all.filter((el) => side.contains(el))));
    if (dir === "left") return false;
    const page = all.filter((el) => !el.closest(SIDE));
    if (usable(lastContent, page)) return focus(lastContent);
    return focus(nearest(cur, dir, page) ?? nearest(cur, dir, page, false)) || start(all);
  }

  // Up/Down never enter the rail (only Left does); Left/Right in a menu stay in it (or go to the rail)
  let pool = sideways ? all : all.filter((el) => !el.closest(SIDE));
  if (group && sideways) pool = pool.filter((el) => group.contains(el) || !!el.closest(SIDE));
  let best = nearest(cur, dir, pool);
  if (!best) return false;

  // into a menu ([data-entry] marks where to land, e.g. the rail's current section)
  const into = best.closest(GROUP);
  if (into && into !== group) {
    const entry = into.querySelector<HTMLElement>("[data-entry]");
    if (entry && visible(entry)) best = entry;
  }
  // up/down into another shelf: go back to where that shelf's focus was, if it's still there
  if (!sideways) {
    const row = best.closest("[data-row]");
    if (row && row !== cur.closest("[data-row]")) {
      const remembered = rowMemory.get(row);
      if (remembered && remembered.isConnected && visible(remembered)) best = remembered;
    }
  }
  return focus(best);
}

/** Focus the element marked [data-autofocus] (else the first focusable) inside `root`. */
export function focusFirst(root: ParentNode = document): boolean {
  const auto = root.querySelector<HTMLElement>("[data-autofocus]");
  if (auto && visible(auto)) return focus(auto);
  return focus(focusables(root)[0]);
}

/** Focus the element with this [data-fid] (a screen coming back restores where it was). */
export function focusId(fid: string | null | undefined): boolean {
  if (!fid) return false;
  const el = document.querySelector<HTMLElement>(`[data-fid="${CSS.escape(fid)}"]`);
  return !!el && visible(el) && focus(el);
}

/** A screen is on the page: put the focus back on `fid` (coming back to it), else on [data-autofocus] / the first
 *  thing in `root`. Keeps trying while the content is still arriving (Home's shelves come one by one): waits for
 *  `fid` a while, and for the content to stop growing before picking the first thing. Stops as soon as something
 *  has the focus another way (the user pressed a key meanwhile). Returns a cancel function. */
export function settleFocus(fid: string | null, root: () => ParentNode | null, wait = 4000): () => void {
  const STEP = 100, FID_WAIT = 1500;
  let waited = 0, count = -1;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const tick = () => {
    const a = document.activeElement;
    if (waited > 0 && a && a !== document.body && a.isConnected) return;  // focused meanwhile
    if (focusId(fid)) return;
    const r = root() ?? document;
    const n = focusables(r).length;
    const steady = n > 0 && n === count;  // nothing new since the last look
    if ((!fid || waited >= FID_WAIT) && (steady || waited >= wait) && focusFirst(r)) return;
    count = n;
    if (waited >= wait) return;
    waited += STEP;
    timer = setTimeout(tick, STEP);
  };
  timer = setTimeout(tick);
  return () => clearTimeout(timer);
}

export const currentFid = (): string | null =>
  (document.activeElement as HTMLElement | null)?.closest<HTMLElement>("[data-fid]")?.dataset.fid ?? null;
