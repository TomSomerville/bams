// The Fire TV side of the page (src/firetv.ts, the ExoPlayer engine, plan.ts with a device's decoders), driven by a
// fake `window.BamsAndroid` standing in for the Android app's bridge (firetv/ Bridge.kt).
import type { FileInfo } from "../src/api";
import { ExoEngine } from "../src/engine";
import type { FireInfo, FirePlayerEvent } from "../src/firetv";
import { convertHeight, plan } from "../src/plan";
import { isBack } from "../src/tizen";
import { eq, mount, ok, test } from "./harness";

type Call = [string, ...unknown[]];

/** A bridge that records what the page asks of it. `caps` as Caps.kt would report a 1080p stick. */
function fakeBridge(info: Partial<FireInfo> = {}) {
  const calls: Call[] = [];
  const full: FireInfo = {
    model: "AFTSSS", name: "Living Room Fire TV", version: "0.0.0", ip: "192.168.1.50",
    caps: { video: { "H.264": { w: 1920, h: 1088 }, HEVC: { w: 1920, h: 1088 } }, audio: ["PCM", "AAC", "MP3", "AC3", "EAC3"],
      h264HighBit: false, dvProfile5: false },
    ...info,
  };
  window.BamsAndroid = {
    info: () => JSON.stringify(full),
    exit: () => void calls.push(["exit"]),
    showKeyboard: (x, y) => void calls.push(["showKeyboard", x, y]),
    load: (...a) => void calls.push(["load", ...a]),
    play: () => void calls.push(["play"]),
    pause: () => void calls.push(["pause"]),
    seek: (ms) => void calls.push(["seek", ms]),
    stop: () => void calls.push(["stop"]),
    selectAudio: (n) => { calls.push(["selectAudio", n]); return n < 2; },
  };
  return calls;
}

async function withBridge(fn: (calls: Call[]) => void | Promise<void>, info?: Partial<FireInfo>) {
  const calls = fakeBridge(info);
  try {
    await fn(calls);
  } finally {
    delete window.BamsAndroid;
  }
}

const player = (event: FirePlayerEvent) => window.bamsHost!({ type: "player", event });

/** Keydowns that reach window (where App.tsx listens), while `fn` runs. */
function keysDuring(fn: () => void): KeyboardEvent[] {
  const seen: KeyboardEvent[] = [];
  const on = (e: KeyboardEvent) => void seen.push(e);
  window.addEventListener("keydown", on);
  try {
    fn();
  } finally {
    window.removeEventListener("keydown", on);
  }
  return seen;
}

test("Fire TV: Back and the media keys reach the app with the TV's key codes, from the focused element", () => withBridge(() => {
  mount(`<button data-fid="a">A</button>`);
  const a = document.querySelector<HTMLElement>("[data-fid=a]")!;
  a.focus();
  const seen = keysDuring(() => {
    window.bamsHost!({ type: "key", code: 10009 });
    window.bamsHost!({ type: "key", code: 10252 });
  });
  eq(seen.length, 2, "keydowns");
  eq(seen[0].keyCode, 10009, "Back's code");
  ok(isBack(seen[0]), "the app reads it as Back");
  eq(seen[0].target, a, "target");
  eq(seen[1].keyCode, 10252, "play/pause's code");
}));

test("Fire TV: OK on a button is an Enter keydown; OK on a text box opens the keyboard instead", () => withBridge((calls) => {
  mount(`<button data-fid="b">B</button><input data-fid="q" style="position: fixed; left: 480px; top: 270px; width: 960px; height: 54px">`);
  document.querySelector<HTMLElement>("[data-fid=b]")!.focus();
  const onButton = keysDuring(() => window.bamsHost!({ type: "key", code: 13 }));
  eq(onButton.length, 1, "keydowns on the button");
  eq(onButton[0].keyCode, 13, "Enter's code");
  document.querySelector<HTMLElement>("[data-fid=q]")!.focus();
  const onInput = keysDuring(() => window.bamsHost!({ type: "key", code: 13 }));
  eq(onInput.length, 0, "keydowns on the text box");
  // the middle of the box, as fractions of the window (the test browser's isn't exactly 1920x1080)
  eq(JSON.stringify(calls), JSON.stringify([["showKeyboard", 960 / innerWidth, 297 / innerHeight]]), "bridge calls");
}));

test("Fire TV: the ExoPlayer engine waits for its own load's 'ready' and ignores events from the one before", () => withBridge(async (calls) => {
  const got: string[] = [];
  const e = new ExoEngine({
    onTime: (t) => void got.push(`time ${t}`),
    onEnd: () => void got.push("end"),
    onError: (m) => void got.push(`error ${m}`),
    onBuffering: (b) => void got.push(`buffering ${b}`),
  });
  void e.load("http://s/a.m3u8", 12.5, true);
  const second = e.load("http://s/b", 600, false);  // a reload before the first was ready
  const loads = calls.filter((c) => c[0] === "load");
  eq(JSON.stringify(loads[0]), JSON.stringify(["load", "http://s/a.m3u8", 12500, true, 1]), "first load");
  eq(JSON.stringify(loads[1]), JSON.stringify(["load", "http://s/b", 600000, false, 2]), "second load");
  let ready = false;
  void second.then(() => { ready = true; });
  player({ id: 1, type: "ready" });
  player({ id: 1, type: "error", message: "old" });
  player({ id: 1, type: "time", t: 3, d: 100, paused: false });
  await Promise.resolve();
  ok(!ready, "the first load's ready mustn't finish the second");
  player({ id: 2, type: "time", t: 601, d: 1300, paused: false });
  player({ id: 2, type: "ready" });
  await second;
  eq(e.time(), 601, "time");
  eq(e.duration(), 1300, "duration");
  ok(!e.paused(), "playing");
  player({ id: 2, type: "error", message: "DECODER_INIT_FAILED" });
  player({ id: 2, type: "ended" });
  eq(JSON.stringify(got.filter((g) => !g.startsWith("buffering"))), JSON.stringify(["time 601", "error DECODER_INIT_FAILED", "end"]), "events");
  ok(e.selectAudio(1) && !e.selectAudio(3), "audio tracks the device has / hasn't");
  e.destroy();
  ok(calls.some((c) => c[0] === "stop"), "destroy stops the player");
  player({ id: 2, type: "error", message: "after" });
  ok(!got.includes("error after"), "nothing after destroy");
}));

test("Fire TV: an error before 'ready' fails the load (the player then falls back to converting)", () => withBridge(async () => {
  const e = new ExoEngine({ onTime: () => undefined, onEnd: () => undefined, onError: () => undefined, onBuffering: () => undefined });
  const p = e.load("http://s/a", 0, false);
  player({ id: 1, type: "error", message: "ERROR_CODE_IO_BAD_HTTP_STATUS: 404" });
  let msg = "";
  await p.catch((err: Error) => { msg = err.message; });
  eq(msg, "ERROR_CODE_IO_BAD_HTTP_STATUS: 404", "rejection");
  e.destroy();
}));

/** A file as plan() sees it. */
function file(container: string, codec: string, w: number, h: number, audio: string): FileInfo {
  return { probe: { container, duration: 1300, bitrate: null, subtitles: [],
    video: { codec, profile: null, resolution: null, width: w, height: h, hdr: null, bit_depth: 8 },
    audio: [{ codec: audio, channels: 6, language: "eng", title: null }] } } as unknown as FileInfo;
}

test("Fire TV: what plays as-is follows the device's decoders (a 1080p stick, Dolby but no DTS)", () => withBridge(() => {
  eq(plan(file("MKV", "HEVC", 1920, 1080, "EAC3"), 0, null).mode, "direct", "1080p HEVC + EAC3");
  eq(plan(file("MKV", "HEVC", 3840, 2160, "EAC3"), 0, null).mode, "convert", "4K HEVC on a 1080p stick");
  eq(plan(file("MKV", "H.264", 1920, 1080, "DTS"), 0, null).mode, "remux", "DTS sound");
  eq(plan(file("WMV", "H.264", 1280, 720, "AAC"), 0, null).mode, "remux", "ASF file");
  eq(plan(file("MP4", "AV1", 1920, 1080, "AAC"), 0, null).mode, "convert", "AV1 without a decoder");
  eq(convertHeight(), 1088, "conversions no taller than the H.264 decoder takes");
}));

test("Fire TV: a 4K stick with an AV receiver plays 4K and DTS as-is", () => withBridge(() => {
  eq(plan(file("MKV", "HEVC", 3840, 2160, "DTS"), 0, null).mode, "direct", "4K HEVC + DTS");
  eq(plan(file("MKV", "AV1", 3840, 2160, "TrueHD"), 0, null).mode, "direct", "4K AV1 + TrueHD");
  eq(convertHeight(), 2160, "conversion size");
}, { caps: { video: { "H.264": { w: 4096, h: 2160 }, HEVC: { w: 4096, h: 2160 }, AV1: { w: 4096, h: 2160 } },
  audio: ["PCM", "AAC", "AC3", "EAC3", "DTS", "TrueHD"], h264HighBit: false, dvProfile5: true } }));

test("not a Fire TV: plan() keeps the browser's rules", () => {
  eq(plan(file("MKV", "HEVC", 1920, 1080, "AAC"), 0, null).mode, "convert", "HEVC in a browser");
  eq(convertHeight(), undefined, "conversion size");
});
