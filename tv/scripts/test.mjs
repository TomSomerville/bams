// The TV app's tests (tv/test/*.test.ts): built into one page and run in a headless Chrome / Edge at the TV's
// 1920x1080, because spatial navigation needs a real layout (positions, sizes, scrolling).
//
//   npm test                 -> builds tv/build/test, runs it, prints each test, exits 1 on a failure
//
// The browser: CHROME_PATH if set, else Chrome / Edge / Chromium where they usually are (Windows, Linux).

import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { build } from "vite";

const here = dirname(fileURLToPath(import.meta.url));
const tv = resolve(here, "..");
const out = join(tv, "build", "test");

function browser() {
  const pf = process.env.PROGRAMFILES ?? "C:\\Program Files";
  const pf86 = process.env["PROGRAMFILES(X86)"] ?? "C:\\Program Files (x86)";
  const tries = [
    process.env.CHROME_PATH,
    join(pf, "Google", "Chrome", "Application", "chrome.exe"),
    join(pf86, "Google", "Chrome", "Application", "chrome.exe"),
    join(pf86, "Microsoft", "Edge", "Application", "msedge.exe"),
    join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/microsoft-edge",
  ];
  return tries.find((p) => p && existsSync(p)) ?? null;
}

// a page that loads from file:// (classic script, like the app's own build in vite.config.ts)
await build({
  configFile: false,
  root: join(tv, "test"),
  base: "./",
  logLevel: "warn",
  plugins: [{
    name: "classic-script",
    enforce: "post",
    transformIndexHtml: (html) => html.replace(/<script type="module" crossorigin/g, "<script defer")
      .replace(/<link rel="modulepreload"[^>]*>/g, "").replace(/ crossorigin/g, ""),
  }],
  build: {
    outDir: out, emptyOutDir: true, target: "es2019", modulePreload: false, cssCodeSplit: false, assetsInlineLimit: 0,
    rollupOptions: { output: { format: "iife" } },
  },
});

const exe = browser();
if (!exe) {
  console.error("No Chrome, Edge or Chromium found: set CHROME_PATH.");
  process.exit(1);
}
const profile = mkdtempSync(join(tmpdir(), "bams-tv-test-"));
let dom;
try {
  dom = execFileSync(exe, [
    "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", `--user-data-dir=${profile}`,
    "--window-size=1920,1080", "--hide-scrollbars", "--force-device-scale-factor=1",
    "--virtual-time-budget=60000",  // timers run on virtual time: the page's waits don't slow the run
    "--dump-dom", pathToFileURL(join(out, "index.html")).href,
  ], { encoding: "utf8", maxBuffer: 64 * 1024 * 1024, stdio: ["ignore", "pipe", "ignore"] });
} finally {
  rmSync(profile, { recursive: true, force: true });
}

const m = /<pre id="results"[^>]*>([\s\S]*?)<\/pre>/.exec(dom);
if (!m) {
  console.error("The test page didn't finish (no results).");
  process.exit(1);
}
const unescape = (s) => s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, "\"").replace(/&#39;/g, "'").replace(/&amp;/g, "&");
const results = JSON.parse(unescape(m[1]));
let failed = 0;
for (const r of results) {
  if (r.ok) console.log(`  ok    ${r.name}`);
  else {
    failed++;
    console.log(`  FAIL  ${r.name}\n          ${r.error}`);
  }
}
console.log(`\n${results.length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
