// Holding OK (src/hold.ts): on a [data-hold] card a short press clicks it and a long press sends it "contextmenu",
// with a Samsung-style remote (key-ups, maybe repeats) and the Fire TV's (key-downs only, repeated while held).
import { HOLD_MS, okDown, okUp, resetHold } from "../src/hold";
import { eq, mount, ok, test, wait } from "./harness";

/** A card that can be held and a plain button, each counting its clicks and context menus. */
function cards() {
  mount(`<button data-fid="card" data-hold>card</button><button data-fid="plain">plain</button>`);
  const log: string[] = [];
  for (const id of ["card", "plain"]) {
    const el = document.querySelector<HTMLElement>(`[data-fid="${id}"]`)!;
    el.addEventListener("click", () => log.push(`${id}:click`));
    el.addEventListener("contextmenu", () => log.push(`${id}:hold`));
  }
  return { log, focus: (id: string) => document.querySelector<HTMLElement>(`[data-fid="${id}"]`)!.focus() };
}

const down = (repeat = false) => okDown(new KeyboardEvent("keydown", { keyCode: 13, repeat } as KeyboardEventInit));

test("Samsung remote: a short press on a card clicks it when OK is let go", async () => {
  resetHold(true);
  const { log, focus } = cards();
  focus("card");
  ok(down(), "the card's OK is taken care of by hold.ts");
  eq(log.join(), "", "nothing yet: it might be a hold");
  await wait(100);
  okUp();
  eq(log.join(), "card:click");
  await wait(HOLD_MS + 100);
  eq(log.join(), "card:click", "only once");
});

test("Samsung remote: holding OK on a card opens its menu, and the rest of the hold presses nothing", async () => {
  resetHold(true);
  const { log, focus } = cards();
  focus("card");
  down();
  await wait(HOLD_MS + 100);
  eq(log.join(), "card:hold");
  focus("plain");  // the menu's first button has the focus now
  ok(down(true), "a repeat of the held key is swallowed");
  eq(log.join(), "card:hold");
  okUp();
  ok(!down(), "after letting go, OK on a plain button is the app's usual press");
});

test("Fire TV (no key-ups): a press clicks the card a moment later", async () => {
  resetHold(false);
  const { log, focus } = cards();
  focus("card");
  down();
  await wait(HOLD_MS);
  eq(log.join(), "card:click");
});

test("Fire TV (no key-ups): held OK repeats, which makes it a hold; its later repeats press nothing", async () => {
  resetHold(false);
  const { log, focus } = cards();
  focus("card");
  down();
  for (let i = 0; i < 8; i++) {  // Android repeats a held key after 500 ms, then every 50 ms
    await wait(i === 0 ? 500 : 50);
    down();
  }
  await wait(200);
  eq(log.join(), "card:hold");
  focus("plain");
  ok(down(), "still held: swallowed");
  await wait(400);
  ok(!down(), "let go and pressed again: the app's usual press");
  eq(log.join(), "card:hold");
});

test("OK on something that can't be held is left to the app", () => {
  resetHold(true);
  const { focus } = cards();
  focus("plain");
  ok(!down(), "not taken");
  okUp();
});
