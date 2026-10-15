// Any screen size, on a PC (theatre mode, development): the page is designed 1920 px wide (the TVs' page), so it's
// zoomed to the window's width, and its height follows the window's shape (1080 on 16:9, 1200 on 16:10) through
// --page-h (styles.css). The TVs stay at exactly 1920x1080, zoom 1.
// Under CSS zoom, getBoundingClientRect() is in zoomed pixels but scrollTop/scrollLeft aren't (measured in Chrome
// 155): nav.ts divides rectangles by pageZoom() before scrolling.

export const PAGE_W = 1920;

let current = 1;

/** The page's zoom (1 on the TVs). */
export const pageZoom = () => current;

function fit() {
  const w = window.innerWidth, h = window.innerHeight;
  if (!w || !h) return;
  current = w / PAGE_W;
  const root = document.documentElement;
  root.style.setProperty("zoom", String(current));
  root.style.setProperty("--page-h", `${Math.round((PAGE_W * h) / w)}px`);
}

/** Start fitting the page to the window (PCs only; main.tsx). */
export function installScaling() {
  fit();
  window.addEventListener("resize", fit);
}
