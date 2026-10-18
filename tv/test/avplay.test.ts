// The Samsung player engine (src/engine.ts AvplayEngine) against a fake `webapis.avplay`. The TV has one player:
// a load that was overtaken (the viewer left during a slow start and picked another video) must leave it alone.
import { AvplayEngine } from "../src/engine";
import { eq, ok, test, wait } from "./harness";

function fakeAvplay() {
  const calls: string[] = [];
  const prepares: { done: () => void; fail: (e: unknown) => void }[] = [];
  let state = "NONE";
  window.webapis = {
    avplay: {
      open: (url: string) => { calls.push(`open ${url}`); state = "IDLE"; },
      close: () => { calls.push("close"); state = "NONE"; },
      stop: () => void calls.push("stop"),
      setDisplayRect: () => undefined,
      setDisplayMethod: () => undefined,
      setListener: () => undefined,
      prepareAsync: (done: () => void, fail: (e: unknown) => void) => void prepares.push({ done, fail }),
      seekTo: (ms: number, done: () => void) => { calls.push(`seek ${ms}`); done(); },
      play: () => void calls.push("play"),
      pause: () => void calls.push("pause"),
      getState: () => state,
    },
  };
  return { calls, prepares };
}

const events = { onTime: () => undefined, onEnd: () => undefined, onError: () => undefined, onBuffering: () => undefined };

test("AVPlay: a start overtaken by the next video's leaves the player to it", async () => {
  const { calls, prepares } = fakeAvplay();
  try {
    const first = new AvplayEngine(events);
    const a = first.load("episode", 600).catch((e: Error) => e.message);
    first.destroy();  // the viewer went back...
    const second = new AvplayEngine(events);
    const b = second.load("movie", 0);  // ...and started a film
    prepares[0].done();  // the episode's prepare finishes late
    prepares[1].done();
    eq(await a, "superseded", "the overtaken load");
    await b;
    await wait(0);
    eq(calls.filter((c) => c.startsWith("seek")).length, 0, "seeks (the episode's resume point on the film)");
    eq(calls.filter((c) => c === "play").length, 1, "plays");
    ok(calls.indexOf("open movie") < calls.lastIndexOf("play"), "the film plays");
    second.destroy();
  } finally {
    delete window.webapis;
  }
});

test("AVPlay: a second load on the same player (another sound track) overtakes the first", async () => {
  const { calls, prepares } = fakeAvplay();
  try {
    const e = new AvplayEngine(events);
    const a = e.load("track 1", 300).catch((err: Error) => err.message);
    const b = e.load("track 2", 300);
    prepares[0].done();
    prepares[1].done();
    eq(await a, "superseded", "the first load");
    await b;
    eq(calls.filter((c) => c === "play").length, 1, "plays");
    eq(calls.filter((c) => c.startsWith("seek")).length, 1, "seeks");
    e.destroy();
  } finally {
    delete window.webapis;
  }
});
