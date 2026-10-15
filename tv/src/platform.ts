// Which device this page runs on, decided in one place:
// - "tizen": the Samsung TV app (window.tizen);
// - "firetv": the Fire TV app (firetv/, window.BamsAndroid);
// - "theatre": theatre mode, the page served by a BAMS server at /theatre/ to a PC at a TV (a kiosk browser);
// - "dev": anything else, i.e. a browser on the Vite dev server.
// Theatre and dev are both PCs: PC keys, the mouse and any screen size (pc()). Samsung and Fire TV code paths stay
// as they were.
//
// Served by a BAMS server, the page shares the browser's storage with the web UI on the same origin, and both use
// some of the same keys ("bams.servers", "bams.videoQueue") in different shapes. So in theatre mode every key gets a
// "bams.theatre." prefix (storage below). The TVs keep their keys: renaming them would sign every TV out.

export type Platform = "tizen" | "firetv" | "theatre" | "dev";

/** Asked each time (cheap): the Fire TV's bridge and the tests' fakes can appear after the page loaded. */
export function platform(): Platform {
  const w = window as unknown as { tizen?: unknown; BamsAndroid?: unknown };
  if (typeof w.tizen !== "undefined") return "tizen";
  if (typeof w.BamsAndroid !== "undefined") return "firetv";
  if (/^https?:$/.test(location.protocol) && location.pathname.startsWith("/theatre/")) return "theatre";
  return "dev";
}

/** Theatre mode: the page came from a BAMS server, which is then its first server. */
export const theatre = () => platform() === "theatre";

/** A PC (theatre mode, or developing in a browser): PC keys, the mouse, any window size. */
export const pc = () => platform() === "theatre" || platform() === "dev";

/** The word for this device in texts ("Link this TV", "this PC"). */
export const deviceWord = () => (pc() ? "PC" : "TV");

/** "bams.x" as this page stores it ("bams.theatre.x" in theatre mode). */
export function storageKey(k: string): string {
  return theatre() ? k.replace(/^bams\./, "bams.theatre.") : k;
}

function store(kind: "localStorage" | "sessionStorage") {
  const s = () => window[kind];
  return {
    get(k: string): string | null {
      try {
        return s().getItem(storageKey(k));
      } catch {
        return null;
      }
    },
    set(k: string, v: string) {
      try {
        s().setItem(storageKey(k), v);
      } catch { /* storage unavailable: this session only */ }
    },
    remove(k: string) {
      try {
        s().removeItem(storageKey(k));
      } catch { /* storage unavailable */ }
    },
  };
}

/** localStorage / sessionStorage with this page's keys (see storageKey). */
export const local = store("localStorage");
export const session = store("sessionStorage");
