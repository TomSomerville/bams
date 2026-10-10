// Package the built TV app (tv/dist) as a signed Tizen widget, and optionally install it on the TV.
//
//   npm run build && npm run package                 -> tv/build/BAMS.wgt
//   npm run package -- --install                     -> also installs it on the TV `sdb` is connected to
//   npm run package -- --install --run               -> and starts it
//   npm run package -- --release                     -> also dist/BAMS-SamsungTV-<version>.wgt (a release asset)
//
// Needs Tizen Studio's CLI (found in TIZEN_STUDIO, C:\tizen-studio, or ~/tizen-studio) and a signing profile
// made in its Certificate Manager with a Samsung certificate for this TV (TIZEN_PROFILE, default "BAMS").
// See tv/README.md.

import { execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const tv = resolve(here, "..");
const dist = join(tv, "dist");
const out = join(tv, "build");
const stage = join(out, "wgt");
const args = new Set(process.argv.slice(2));
const win = process.platform === "win32";
const APP_ID = "BAMSmedia1.BAMS";

function die(msg) {
  console.error(`\n${msg}\n`);
  process.exit(1);
}

function studio() {
  const dirs = [process.env.TIZEN_STUDIO, win ? "C:\\tizen-studio" : null, join(homedir(), "tizen-studio")].filter(Boolean);
  for (const d of dirs) {
    const cli = join(d, "tools", "ide", "bin", win ? "tizen.bat" : "tizen");
    if (existsSync(cli)) return { cli, sdb: join(d, "tools", win ? "sdb.exe" : "sdb") };
  }
  return null;
}

function run(cmd, argv, opts = {}) {
  console.log(`> ${[cmd, ...argv].join(" ")}`);
  // .bat files need a shell on Windows
  return execFileSync(cmd, argv, { stdio: opts.capture ? "pipe" : "inherit", encoding: "utf8", shell: win && cmd.endsWith(".bat") });
}

if (!existsSync(join(dist, "index.html"))) die("tv/dist is missing: run `npm run build` first.");
const version = JSON.parse(readFileSync(join(tv, "package.json"), "utf8")).version;

// stage: the built app + the manifest (with this version) + the icon
rmSync(stage, { recursive: true, force: true });
mkdirSync(stage, { recursive: true });
cpSync(dist, stage, { recursive: true });
writeFileSync(join(stage, "config.xml"), readFileSync(join(tv, "tizen", "config.xml"), "utf8").replace("@VERSION@", version));
cpSync(join(tv, "tizen", "icon.png"), join(stage, "icon.png"));

const t = studio();
if (!t) {
  die("Tizen Studio's CLI wasn't found (looked in TIZEN_STUDIO, C:\\tizen-studio, ~/tizen-studio).\n" +
    `The app is staged in ${stage}; install Tizen Studio (tv/README.md) and run this again to sign and package it.`);
}
const profile = process.env.TIZEN_PROFILE || "BAMS";
run(t.cli, ["package", "-t", "wgt", "-s", profile, "--", stage]);
const wgt = readdirSync(stage).find((f) => f.endsWith(".wgt"));
if (!wgt) die("Tizen didn't produce a .wgt (see its messages above: usually the signing profile's name or password).");
const final = join(out, "BAMS.wgt");
rmSync(final, { force: true });
renameSync(join(stage, wgt), final);
console.log(`\nPackaged: ${final}`);
if (args.has("--release")) {
  const rel = join(tv, "..", "dist", `BAMS-SamsungTV-${version}.wgt`);
  mkdirSync(dirname(rel), { recursive: true });
  cpSync(final, rel);
  console.log(`Release copy: ${rel}`);
}

if (args.has("--install")) {
  const devices = run(t.sdb, ["devices"], { capture: true });
  const line = devices.split(/\r?\n/).slice(1).find((l) => /\bdevice\b/.test(l));
  if (!line) die("No TV connected. On the PC: `sdb connect <TV address>` (Developer Mode must be on, with this PC's address).");
  const serial = line.trim().split(/\s+/)[0];
  const name = run(t.sdb, ["-s", serial, "capability"], { capture: true }).match(/device_name:(\S+)/)?.[1];
  run(t.cli, ["install", "-n", "BAMS.wgt", "-s", serial, "--", out]);
  if (args.has("--run")) run(t.cli, ["run", "-p", APP_ID, "-s", serial]);
  console.log(`\nInstalled on ${name ?? serial}.`);
}
