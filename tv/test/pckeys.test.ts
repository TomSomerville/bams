// PC keyboards and USB remotes (src/pckeys.ts): each key the screens don't know becomes the Samsung code they do, or
// an action; letters typed outside a text box open Search, but not in the player or a menu, and not as shortcuts.
import { press, translate } from "../src/pckeys";
import { storageKey } from "../src/platform";
import { KEY } from "../src/tizen";
import { eq, mount, test } from "./harness";

const key = (k: string, mods: KeyboardEventInit = {}) => translate(new KeyboardEvent("keydown", { key: k, ...mods }));
const code = (t: ReturnType<typeof translate>) => (t && "code" in t ? t.code : null);

test("PC keys: Back, media and Media Center remote keys become the remote's codes", () => {
  mount(`<button data-fid="a">a</button>`);
  eq(code(key("BrowserBack")), KEY.BACK, "BrowserBack");
  eq(code(key("GoBack")), KEY.BACK, "GoBack");
  eq(code(key("MediaPlayPause")), KEY.PLAY_PAUSE, "MediaPlayPause");
  eq(code(key("MediaStop")), KEY.STOP, "MediaStop");
  eq(code(key("MediaTrackNext")), KEY.NEXT, "MediaTrackNext");
  eq(code(key("MediaRewind")), KEY.RW, "MediaRewind");
  eq(code(key("p", { ctrlKey: true })), KEY.PAUSE, "Ctrl+P (Media Center pause)");
  eq(code(key("P", { ctrlKey: true, shiftKey: true })), KEY.PLAY, "Ctrl+Shift+P (play)");
  eq(code(key("f", { ctrlKey: true })), KEY.NEXT, "Ctrl+F (skip)");
  eq(key("x", { ctrlKey: true }), null, "Ctrl+X is left alone");
  eq(key("ArrowLeft"), null, "arrows are the page's own");
  eq(key("Escape"), null, "Escape is Back already (isBack)");
});

test("PC keys: Home, the Menu key and the Search key are actions", () => {
  mount(`<button data-fid="a">a</button>`);
  eq(JSON.stringify(key("BrowserHome")), JSON.stringify({ action: "home" }), "Home");
  eq(JSON.stringify(key("ContextMenu")), JSON.stringify({ action: "menu" }), "Menu");
  eq(JSON.stringify(key("BrowserSearch")), JSON.stringify({ search: "" }), "Search");
});

test("type-to-search: a letter outside a text box opens Search, but not in a text box, menu or the player", () => {
  const root = mount(`<button data-fid="a">a</button><input data-fid="q">`);
  root.querySelector<HTMLElement>('[data-fid="a"]')!.focus();
  eq(JSON.stringify(key("b")), JSON.stringify({ search: "b" }), "a letter on a button");
  eq(JSON.stringify(key("7")), JSON.stringify({ search: "7" }), "a digit");
  eq(key("b", { altKey: true }), null, "Alt+B is a shortcut");
  eq(key(" "), null, "Space outside the player is the button's own");
  root.querySelector<HTMLElement>('[data-fid="q"]')!.focus();
  eq(key("b"), null, "typing in a text box");
  eq(code(key("MediaPlayPause")), KEY.PLAY_PAUSE, "media keys still work while typing");
  mount(`<div class="menu" data-trap><button data-fid="m">m</button></div>`);
  document.querySelector<HTMLElement>('[data-fid="m"]')!.focus();
  eq(key("b"), null, "in a menu");
  mount(`<div class="player"><button data-fid="p">p</button></div>`);
  document.querySelector<HTMLElement>('[data-fid="p"]')!.focus();
  eq(key("b"), null, "in the player");
  eq(code(key(" ")), KEY.PLAY_PAUSE, "Space in the player pauses");
});

test("press(): a keydown with the remote's code on the focused element, bubbling to the app", () => {
  mount(`<button data-fid="a">a</button>`);
  const el = document.querySelector<HTMLElement>('[data-fid="a"]')!;
  el.focus();
  let got: { code: number; target: EventTarget | null } | null = null;
  const on = (e: KeyboardEvent) => { got = { code: e.keyCode, target: e.target }; };
  window.addEventListener("keydown", on);
  press(KEY.BACK);
  window.removeEventListener("keydown", on);
  eq(got!.code, KEY.BACK, "code");
  eq(got!.target, el, "from the focused element");
  eq(code(translate(new KeyboardEvent("keydown"))), null, "our own presses (no key) aren't translated again");
});

test("storage: the TV apps and development keep their keys (theatre mode alone prefixes them)", () => {
  eq(storageKey("bams.token"), "bams.token", "not served from /theatre/ here");
});
