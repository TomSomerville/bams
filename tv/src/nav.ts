// Moving around with the remote's arrows ("spatial navigation"): from the focused element, the nearest focusable
// element in that direction gets the focus. Focusable = <button>, <input>, or anything with [data-focus], that is
// visible. A [data-row] container (a shelf of posters) remembers where its focus was, so going down and back up
// returns to the same poster rather than the nearest one.

export type Dir = "left" | "right" | "up" | "down";

const SELECTOR = "button:not([disabled]), input, [data-focus]";
const rowMemory = new WeakMap<Element, HTMLElement>();

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

/** Scroll the focused element into view: shelves scroll sideways, the page scrolls to keep it comfortably inside. */
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
    const top = box.top + box.height * 0.28;
    const bottom = box.bottom - 60;
    if (r.top < top) page.scrollTop -= top - r.top;
    else if (r.bottom > bottom) page.scrollTop += r.bottom - bottom;
  }
}

/** Move the focus one step in `dir`. False when there's nothing that way (the caller may do something else). */
export function move(dir: Dir): boolean {
  const all = focusables();
  const cur = document.activeElement as HTMLElement | null;
  if (!cur || !all.includes(cur)) return focus(all[0]);
  const a = cur.getBoundingClientRect();
  const ax = a.left + a.width / 2, ay = a.top + a.height / 2;
  const curRow = cur.closest("[data-row]");
  let best: HTMLElement | null = null;
  let bestScore = Infinity;
  for (const el of all) {
    if (el === cur) continue;
    const b = el.getBoundingClientRect();
    const bx = b.left + b.width / 2, by = b.top + b.height / 2;
    let primary: number, secondary: number;
    // sideways only to things level with this one (at the end of a short shelf, Right does nothing rather than
    // dropping into the shelf below)
    // (a menu column like the rail counts as level with everything beside it)
    const level = (b.bottom > a.top + 4 && b.top < a.bottom - 4) || (!!el.closest("[data-group]") && !cur.closest("[data-group]"));
    switch (dir) {
      case "right": if (!level || (b.left < a.right - 4 && bx <= ax + 4)) continue; primary = Math.max(0, b.left - a.right); secondary = Math.abs(by - ay); break;
      case "left": if (!level || (b.right > a.left + 4 && bx >= ax - 4)) continue; primary = Math.max(0, a.left - b.right); secondary = Math.abs(by - ay); break;
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
  if (!best) return false;
  // into a menu ([data-entry] marks where to land, e.g. the rail's current section)
  const group = best.closest("[data-group]");
  if (group && !cur.closest("[data-group]")) {
    const entry = group.querySelector<HTMLElement>("[data-entry]");
    if (entry && visible(entry)) best = entry;
  }
  // up/down into another shelf: go back to where that shelf's focus was, if it's still there
  if (dir === "up" || dir === "down") {
    const row = best.closest("[data-row]");
    if (row && row !== curRow) {
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

export const currentFid = (): string | null =>
  (document.activeElement as HTMLElement | null)?.closest<HTMLElement>("[data-fid]")?.dataset.fid ?? null;
