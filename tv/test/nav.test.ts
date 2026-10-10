// Spatial navigation (src/nav.ts) on pages laid out like the app's screens (same class names and data-* marks as
// Rail.tsx, Cards.tsx and the screens), with the app's styles at the TV's 1920x1080.
import * as nav from "../src/nav";
import { eq, focused, mount, ok, test, wait } from "./harness";

const { move, focus, focusId, settleFocus } = nav;
const el = (fid: string) => document.querySelector<HTMLElement>(`[data-fid="${fid}"]`)!;
const main = () => document.querySelector<HTMLElement>("main")!;
const onScreen = (fid: string) => {
  const r = el(fid).getBoundingClientRect();
  return r.top >= 0 && r.bottom <= 1080 && r.right > 0 && r.left < 1920;
};

// ---- fixtures: the same markup as the real components

/** Rail.tsx: Home, `libs` libraries, (another server's), Search, Settings; `active` gets data-entry. */
function rail(active: string | null = "home", libs = 3, remote = 0): string {
  const item = (id: string) =>
    `<button data-fid="rail-${id}" class="rail-item ${id === active ? "active" : ""}" ${id === active ? "data-entry" : ""}>` +
    `<svg class="icon" width="40" height="40"></svg><span>${id}</span></button>`;
  const ids = ["home", ...Array.from({ length: libs }, (_, i) => `lib${i + 1}`)];
  const far = Array.from({ length: remote }, (_, i) => `r1-lib${i + 1}`);
  return `<nav class="rail" data-group data-side data-scroll><img class="rail-logo" alt="">${ids.map(item).join("")}` +
    (far.length ? `<div class="rail-server"><span>Other</span></div>${far.map(item).join("")}` : "") +
    `${item("search")}${item("settings")}</nav>`;
}
const poster = (fid: string) => `<button class="card poster" data-fid="${fid}"><div class="no-art"><span>${fid}</span></div></button>`;
const shelf = (row: string, n: number) =>
  `<section class="shelf"><h2>${row}</h2><div class="shelf-row" data-row>${Array.from({ length: n }, (_, i) => poster(`${row}-${i}`)).join("")}</div></section>`;
const nowPlaying = `<div class="now-playing" data-group data-cover><div class="np-cover no-art"></div><div class="np-text"><div class="np-title">Song</div></div>` +
  ["prev", "play", "next", "stop"].map((b) => `<button class="round" data-fid="np-${b}"><svg width="40" height="40"></svg></button>`).join("") + `</div>`;
/** App.tsx's shell around a screen. */
const shell = (screen: string, opts: { active?: string | null; libs?: number; remote?: number; np?: boolean } = {}) =>
  `<div class="shell ${opts.np ? "has-np" : ""}">${rail(opts.active === undefined ? "home" : opts.active, opts.libs ?? 3, opts.remote ?? 0)}` +
  `<main class="content" data-scroll>${screen}</main>${opts.np ? nowPlaying : ""}</div>`;
/** Home.tsx: the banner (nothing to focus in it), then shelves. */
const home = (rows: number, per = 12) =>
  `<div class="home"><div class="hero"><div class="hero-shade"></div></div>${Array.from({ length: rows }, (_, i) => shelf(`r${i}`, per)).join("")}</div>`;
/** Settings.tsx: a short page. */
const settings = `<div class="page"><div class="page-head"><h1>Settings</h1></div><div class="panel"><h2>Playback</h2>` +
  `<button class="toggle" data-fid="convert" data-autofocus>Always convert<span class="switch"></span></button>` +
  `<button class="toggle" data-fid="dts">DTS<span class="switch"></span></button></div></div>`;
/** Library.tsx: sort chips, genre chips, a grid of `n` posters. */
const library = (n: number) => `<div class="page"><div class="page-head"><h1>Movies</h1><div class="chips">` +
  ["title", "added", "year"].map((s) => `<button class="chip" data-fid="sort-${s}">${s}</button>`).join("") + `</div></div>` +
  `<div class="chips genres" data-row>` + ["all", "action", "drama", "comedy"].map((g) => `<button class="chip" data-fid="genre-${g}">${g}</button>`).join("") + `</div>` +
  `<div class="grid">${Array.from({ length: n }, (_, i) => poster(`item-${i}`)).join("")}</div></div>`;
/** Detail.tsx for a show: buttons, season chips, episodes. */
const detail = `<div class="detail"><div class="detail-shade"></div><div class="detail-body"><div class="detail-top"><div class="detail-text">` +
  `<h1>Show</h1><div class="button-row"><button class="btn primary" data-fid="play" data-autofocus>Play</button>` +
  `<button class="btn" data-fid="watched">Mark watched</button></div></div></div>` +
  `<div class="chips seasons" data-row>${[1, 2, 3].map((s) => `<button class="chip" data-fid="season-${s}">Season ${s}</button>`).join("")}</div>` +
  `<div class="episodes">${Array.from({ length: 8 }, (_, i) => `<button class="episode" data-fid="ep-${i}"><div class="ep-still"></div><div class="ep-text"><div class="ep-title">${i + 1}. Episode</div></div></button>`).join("")}</div></div></div>`;

function press(...dirs: nav.Dir[]) {
  for (const d of dirs) move(d);
}

// ---- the rail (the menu on the left)

test("Right from the rail's Home reaches Home's shelves (the banner beside it has nothing to focus)", () => {
  mount(shell(home(3)));
  focus(el("rail-home"));
  press("right");
  ok(focused().startsWith("r0-") || focused().startsWith("r1-"), `focus should be on a shelf, is on ${focused()}`);
});

test("Right from the rail goes back to the poster it was left from", () => {
  mount(shell(home(4)));
  focus(el("r2-3"));
  press("left", "left", "left", "left");  // to r2-0, then into the rail
  eq(focused(), "rail-home", "Left from the first poster lands on the rail's current section");
  press("right");
  eq(focused(), "r2-0", "back to where it left");
});

test("Right from the rail's last item reaches a short page", () => {
  mount(shell(settings, { active: "settings", libs: 6 }));
  focus(el("rail-settings"));
  press("right");
  ok(["convert", "dts"].includes(focused()), `focus should be on Settings, is on ${focused()}`);
});

test("Right from the rail after moving through it still returns to the page", () => {
  mount(shell(library(30), { active: "lib1" }));
  focus(el("item-8"));
  press("left");  // item-7 in the grid
  eq(focused(), "item-7");
  focus(el("item-7"));
  press("left", "left");
  ok(focused().startsWith("rail-"), `in the rail: ${focused()}`);
  press("down", "down", "down");
  press("right");
  eq(focused(), "item-7", "back on the grid where it was");
});

test("Up/Down in the rail stay in the rail", () => {
  mount(shell(home(3), { np: true }));
  focus(el("rail-home"));
  press("down");
  eq(focused(), "rail-lib1");
  press("up", "up");
  eq(focused(), "rail-home", "top of the rail: stays");
  focus(el("rail-settings"));
  press("down");
  eq(focused(), "rail-settings", "bottom of the rail: stays (doesn't drop into the music bar or the page)");
});

test("a long rail scrolls to show the focused item", () => {
  mount(shell(home(2), { libs: 12, remote: 6 }));
  focus(el("rail-home"));
  for (let i = 0; i < 30; i++) move("down");
  eq(focused(), "rail-settings");
  ok(onScreen("rail-settings"), "Settings is on screen");
  for (let i = 0; i < 30; i++) move("up");
  eq(focused(), "rail-home");
  ok(onScreen("rail-home"), "Home is on screen again");
});

test("Left from a detail page lands on the rail's current section", () => {
  mount(shell(detail, { active: "lib2" }));
  focus(el("play"));
  press("left");
  eq(focused(), "rail-lib2");
});

// ---- the page

test("Up from the first shelf doesn't jump into the rail", () => {
  mount(shell(home(3)));
  focus(el("r0-4"));
  press("up");
  eq(focused(), "r0-4");
});

test("Down/Up between shelves keep each shelf's place", () => {
  mount(shell(home(3)));
  focus(el("r0-4"));
  press("down");
  eq(focused(), "r1-4", "straight down");
  press("right", "right");
  eq(focused(), "r1-6");
  press("up");
  eq(focused(), "r0-4", "back to where row 0 was");
  press("down");
  eq(focused(), "r1-6", "back to where row 1 was");
});

test("Right at the end of a shelf stays (doesn't drop into the next one)", () => {
  mount(shell(home(2, 4)));
  focus(el("r0-3"));
  press("right");
  eq(focused(), "r0-3");
});

test("Right along a long shelf scrolls it and stays in it", () => {
  mount(shell(home(2, 20)));
  focus(el("r0-0"));
  for (let i = 0; i < 19; i++) move("right");
  eq(focused(), "r0-19");
  ok(onScreen("r0-19"), "the last poster is on screen");
  for (let i = 0; i < 19; i++) move("left");
  eq(focused(), "r0-0");
  ok(onScreen("r0-0"), "the first poster is on screen again");
});

test("Down through many shelves keeps the focus on screen; Up comes back", () => {
  mount(shell(home(8)));
  focus(el("r0-2"));
  for (let i = 1; i < 8; i++) {
    move("down");
    eq(focused(), `r${i}-2`, `down #${i}`);
    ok(onScreen(focused()), `r${i}-2 on screen`);
  }
  for (let i = 6; i >= 0; i--) {
    move("up");
    eq(focused(), `r${i}-2`, `up to row ${i}`);
    ok(onScreen(focused()), `r${i}-2 on screen`);
  }
});

test("Library: Down into a short last row; Up through genres to the sort chips", () => {
  mount(shell(library(10), { active: "lib1" }));
  focus(el("item-6"));  // 7 per row: the end of row 0
  press("down");
  eq(focused(), "item-9", "the nearest in the short row below");
  focus(el("item-2"));
  press("up");
  ok(focused().startsWith("genre-"), `genres: ${focused()}`);
  press("up");
  ok(focused().startsWith("sort-"), `sort: ${focused()}`);
  press("down", "down");
  ok(focused().startsWith("item-"), `back on the grid: ${focused()}`);
});

test("Detail: buttons → seasons → episodes and back", () => {
  mount(shell(detail, { active: "lib1" }));
  focus(el("watched"));
  press("down");
  ok(focused().startsWith("season-"), `seasons: ${focused()}`);
  press("down");
  eq(focused(), "ep-0");
  press("down", "down");
  eq(focused(), "ep-2");
  press("up", "up", "up");
  ok(focused().startsWith("season-"), `seasons again: ${focused()}`);
  press("up");
  ok(["play", "watched"].includes(focused()), `buttons again: ${focused()}`);
});

// ---- the music bar

test("Music bar: Down from the last shelf reaches it, Up leaves it, Left from the page doesn't jump into it", () => {
  mount(shell(home(2, 6), { np: true }));
  focus(el("r1-5"));
  press("down");
  ok(focused().startsWith("np-"), `in the bar: ${focused()}`);
  press("up");
  ok(focused().startsWith("r1-"), `back on the shelf: ${focused()}`);
  focus(el("r1-5"));
  press("left");
  eq(focused(), "r1-4");
  press("right");
  eq(focused(), "r1-5");
});

test("Music bar: Down onto a shelf behind it scrolls the shelf above it", () => {
  mount(shell(home(4), { np: true }));
  focus(el("r0-1"));
  press("down", "down");
  eq(focused(), "r2-1");
  const bar = document.querySelector(".now-playing")!.getBoundingClientRect();
  ok(el("r2-1").getBoundingClientRect().bottom <= bar.top, "the poster is above the bar");
});

test("Music bar: Left/Right stay in it", () => {
  mount(shell(home(2), { np: true }));
  focus(el("np-play"));
  press("right", "right", "right");
  eq(focused(), "np-stop");
  press("left");
  eq(focused(), "np-next");
});

test("Music bar: Left from its first button reaches the rail", () => {
  mount(shell(home(2), { np: true }));
  focus(el("np-prev"));
  press("left");
  ok(focused().startsWith("rail-"), `rail: ${focused()}`);
});

// ---- lost focus, traps, screens arriving

test("with nothing focused, an arrow focuses the page, not the rail", () => {
  mount(shell(settings, { active: "settings" }));
  press("down");
  eq(focused(), "convert");
});

test("the focused poster disappearing (list re-rendered): an arrow picks up on the page", () => {
  mount(shell(library(10), { active: "lib1" }));
  focus(el("item-3"));
  el("item-3").remove();
  press("right");
  ok(focused().startsWith("item-") || focused().startsWith("sort-") || focused().startsWith("genre-"), `on the page: ${focused()}`);
});

test("a [data-trap] layer keeps the focus inside", () => {
  mount(shell(home(2)) + `<div class="menu" data-trap><div class="menu-list" data-scroll>` +
    [0, 1, 2].map((i) => `<button class="menu-item" data-fid="m${i}">Item ${i}</button>`).join("") + `</div></div>`);
  focus(el("m0"));
  press("left", "up");
  eq(focused(), "m0");
  press("down", "down", "down");
  eq(focused(), "m2");
});

test("focusId restores a remembered element", () => {
  mount(shell(home(3)));
  ok(focusId("r2-5"), "found");
  eq(focused(), "r2-5");
});


test("a screen whose content arrives late (Home's shelves) still gets the focus", async () => {
  mount(shell(`<div class="home"><div class="hero"></div></div>`));
  settleFocus(null, main);
  await wait(300);
  main().firstElementChild!.insertAdjacentHTML("beforeend", shelf("r0", 8));
  await wait(400);
  eq(focused(), "r0-0");
});

test("coming back to a screen restores the focus once that element has loaded", async () => {
  mount(shell(`<div class="home"><div class="hero"></div>${shelf("r0", 8)}</div>`));
  settleFocus("r1-4", main);
  await wait(500);
  main().firstElementChild!.insertAdjacentHTML("beforeend", shelf("r1", 8));
  await wait(300);
  eq(focused(), "r1-4");
});

test("settling doesn't take the focus back from the user", async () => {
  mount(shell(`<div class="home"><div class="hero"></div></div>`));
  settleFocus(null, main);
  await wait(200);
  focus(el("rail-lib1"));
  main().firstElementChild!.insertAdjacentHTML("beforeend", shelf("r0", 8));
  await wait(2000);
  eq(focused(), "rail-lib1");
});
