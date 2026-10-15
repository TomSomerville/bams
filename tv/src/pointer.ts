// The mouse on a PC (theatre mode, development), for air-mouse remotes and the odd real mouse. The page is driven by
// the remote's arrows; the mouse is a helper: the pointer shows while it moves and hides after POINTER_HIDE; hovering
// something focuses it (without scrolling the page under a resting pointer); the wheel scrolls; right-click opens a
// card's hold menu (cards handle "contextmenu" already). Some air mice send OK as a left click wherever the hidden
// pointer happens to be: while it's hidden, a click goes to the focused element instead. Not used on the TVs.

import { SELECTOR } from "./nav";

const POINTER_HIDE = 3000;

export function installPointer() {
  const root = document.documentElement;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const shown = () => root.classList.contains("pointer");
  window.addEventListener("mousemove", () => {
    root.classList.add("pointer");
    clearTimeout(timer);
    timer = setTimeout(() => root.classList.remove("pointer"), POINTER_HIDE);
  }, { passive: true });

  window.addEventListener("mouseover", (e) => {
    if (!shown()) return;
    const el = (e.target as Element | null)?.closest?.(SELECTOR) as HTMLElement | null;
    if (el && el !== document.activeElement) el.focus({ preventScroll: true });
  });

  window.addEventListener("click", (e) => {
    if (shown() || !e.isTrusted) return;
    const f = document.activeElement as HTMLElement | null;
    if (!f || f === document.body || f.contains(e.target as Node)) return;
    e.preventDefault();
    e.stopPropagation();
    f.click();
  }, true);

  window.addEventListener("wheel", (e) => {
    const t = e.target as Element | null;
    const row = t?.closest?.("[data-row]") as HTMLElement | null;
    if (row && (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY))) {
      row.scrollLeft += e.shiftKey ? e.deltaY : e.deltaX;
      return;
    }
    const page = t?.closest?.("[data-scroll]") as HTMLElement | null;
    if (page) page.scrollTop += e.deltaY;
  }, { passive: true });
}
