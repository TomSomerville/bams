// Build the Fire TV app (an APK around the TV app's page in tv/dist) and optionally put it on a Fire TV.
//
//   cd tv && npm run build && npm run firetv                -> firetv/app/build/outputs/apk/debug/app-debug.apk
//   npm run firetv -- --install --device 192.168.1.50       -> also installs it on that Fire TV (adb over the network)
//   npm run firetv -- --install --run                       -> and starts it (on the device adb is already connected to)
//   npm run firetv -- --release                             -> signed release APK, also dist/BAMS-FireTV-<version>.apk
//
// Needs the Android SDK (ANDROID_HOME, or %LOCALAPPDATA%\Android\Sdk / ~/Android/Sdk) and JDK 17. The Fire TV needs
// ADB debugging on (firetv/README.md). FIRETV=<address> stands in for --device.

import { execFileSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "..");
const argv = process.argv.slice(2);
const args = new Set(argv);
const win = process.platform === "win32";
const APP = "media.bams.firetv";
const release = args.has("--release");
const device = (() => {
  const i = argv.indexOf("--device");
  return i >= 0 ? argv[i + 1] : process.env.FIRETV || null;
})();

function die(msg) {
  console.error(`\n${msg}\n`);
  process.exit(1);
}

function run(cmd, a, opts = {}) {
  console.log(`> ${[cmd, ...a].join(" ")}`);
  // .bat files need a shell on Windows
  return execFileSync(cmd, a, { cwd: opts.cwd, stdio: opts.capture ? "pipe" : "inherit", encoding: "utf8",
    shell: win && cmd.endsWith(".bat") });
}

function sdk() {
  const dirs = [process.env.ANDROID_HOME, process.env.ANDROID_SDK_ROOT,
    win ? join(process.env.LOCALAPPDATA ?? "", "Android", "Sdk") : join(homedir(), "Android", "Sdk")].filter(Boolean);
  return dirs.find((d) => existsSync(join(d, "platform-tools"))) ?? null;
}

if (!existsSync(join(repo, "tv", "dist", "index.html"))) die("tv/dist is missing: run `npm run build` in tv/ first.");
const sdkDir = sdk();
if (!sdkDir) die("The Android SDK wasn't found (ANDROID_HOME, or the default folder). See firetv/README.md.");
if (release && !existsSync(join(here, "keystore.properties"))) {
  die("A release build needs firetv/keystore.properties (the signing key). See firetv/README.md, \"Release builds\".");
}

process.env.ANDROID_HOME = sdkDir;  // Gradle finds the SDK through it (no local.properties needed)
run(join(here, win ? "gradlew.bat" : "gradlew"), [release ? "assembleRelease" : "assembleDebug", "--console=plain"], { cwd: here });
const apk = join(here, "app", "build", "outputs", "apk", release ? "release/app-release.apk" : "debug/app-debug.apk");
if (!existsSync(apk)) die(`The build didn't make ${apk}.`);
console.log(`\nAPK: ${apk}`);

if (release) {
  const version = JSON.parse(readFileSync(join(repo, "tv", "package.json"), "utf8")).version;
  mkdirSync(join(repo, "dist"), { recursive: true });
  const out = join(repo, "dist", `BAMS-FireTV-${version}.apk`);
  copyFileSync(apk, out);
  console.log(`Release asset: ${out}`);
}

if (args.has("--install") || args.has("--run")) {
  const adb = join(sdkDir, "platform-tools", win ? "adb.exe" : "adb");
  const target = device ? (device.includes(":") ? device : `${device}:5555`) : null;
  if (target) {
    // the Fire TV asks once, on screen, whether to allow this computer: accept it there, then run this again
    const said = run(adb, ["connect", target], { capture: true });
    console.log(said.trim());
    if (/failed|unable|refused/i.test(said)) die(`adb couldn't connect to ${target}: is ADB debugging on? (firetv/README.md)`);
  }
  const on = target ? ["-s", target] : [];
  if (args.has("--install")) {
    try {
      run(adb, [...on, "install", "-r", apk]);
    } catch {
      die("Installing failed. If it says INSTALL_FAILED_UPDATE_INCOMPATIBLE, the copy on the Fire TV was signed with " +
        `another key (debug vs release): remove it first with \`adb uninstall ${APP}\` (its sign-in is lost).`);
    }
  }
  if (args.has("--run")) run(adb, [...on, "shell", "am", "start", "-n", `${APP}/.MainActivity`]);
}
