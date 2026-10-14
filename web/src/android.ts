// The BAMS Android app (android/): the web UI runs in its WebView, and the app adds downloads (original files,
// to watch and listen with no connection). The app injects `window.bamsAndroid` (a WebMessageListener, only
// for the servers it was given); in a browser it's missing and none of this shows.
//
// Shared with the app's own pages (android/web: Downloads, Servers), which are built from this folder and run
// even with no server: keep it free of React, the router and server-only imports.

/** A server as the app knows it: the address this page reached it at and, for another server, its token. */
export type AppServer = { url: string; name: string; token: string | null };

export type Volume = { id: string; label: string; free: number; total: number; removable: boolean };

export type AppInfo = {
  version: string;
  /** where new downloads go (a Volume id) */
  location: string;
  volumes: Volume[];
  wifiOnly: boolean;
  /** bytes the downloads take */
  used: number;
  /** what this phone decodes, in BAMS's probe names ("AAC", "AC3", "H.264", "HEVC"…) */
  codecs: { audio: string[]; video: string[] };
};

/** One download as the app tracks it: a title, a season, a show, an album, an artist or a playlist. */
export type DownloadState = {
  state: "none" | "queued" | "downloading" | "paused" | "done" | "failed";
  /** 0..1 */
  progress: number;
  bytes: number;
  error?: string | null;
  /** part of another download (an episode of a downloaded season): it can't be removed on its own */
  within?: string | null;
};

/** Fired on window when downloads changed (queued, progress, done, removed): buttons ask again. */
export const DOWNLOADS_CHANGED = "bams:downloads";

type Port = { postMessage(m: string): void; addEventListener(t: "message", f: (e: { data: string }) => void): void };

const port = (window as unknown as { bamsAndroid?: Port }).bamsAndroid ?? null;

/** In the Android app (it can download), or in a browser. */
export const inApp = port !== null;

let next = 1;
const waiting = new Map<number, { ok: (v: unknown) => void; fail: (e: Error) => void }>();

port?.addEventListener("message", (e) => {
  let m: { reply?: number; ok?: boolean; data?: unknown; error?: string; event?: string };
  try {
    m = JSON.parse(e.data);
  } catch {
    return;
  }
  if (m.reply !== undefined) {
    const w = waiting.get(m.reply);
    waiting.delete(m.reply);
    if (m.ok) w?.ok(m.data);
    else w?.fail(new Error(m.error || "The app couldn't do that."));
  } else if (m.event) {
    window.dispatchEvent(new CustomEvent(`bams:${m.event}`, { detail: m.data }));
  }
});

/** Ask the app something ({type, ...args}); rejects outside the app. */
export function app<T>(type: string, args: Record<string, unknown> = {}): Promise<T> {
  if (!port) return Promise.reject(new Error("Only the BAMS Android app can do that."));
  const id = next++;
  return new Promise<T>((ok, fail) => {
    waiting.set(id, { ok: ok as (v: unknown) => void, fail });
    port.postMessage(JSON.stringify({ id, type, ...args }));
  });
}

/** "item:5" / "playlist:3" / "user_playlist:2": what the app keys a download by, on its server. */
export const downloadKey = (kind: "item" | "playlist" | "user_playlist", id: number) => `${kind}:${id}`;

export const appApi = {
  info: () => app<AppInfo>("info"),
  /** queue a download: the app asks `server` for the manifest at `path` (/api/items/5/download…) and fetches it */
  download: (server: AppServer, key: string, path: string, title: string) =>
    app<void>("download", { server, key, path, title }),
  status: (server: AppServer, keys: string[]) => app<Record<string, DownloadState>>("status", { server, keys }),
  remove: (server: AppServer, key: string) => app<void>("remove", { server, key }),
  setLocation: (volume: string) => app<AppInfo>("setLocation", { volume }),
  setWifiOnly: (on: boolean) => app<AppInfo>("setWifiOnly", { on }),
  /** the app's own Downloads screen (works with no server) */
  openDownloads: () => app<void>("openDownloads"),
  /** the app's server list (add another server, another address of this one) */
  openServers: () => app<void>("openServers"),
};

/** Audio codecs of a file this phone can't play offline (the server converts them when streaming). */
export function unplayableAudio(info: AppInfo | null, codecs: (string | null | undefined)[]): string[] {
  if (!info) return [];
  const ok = info.codecs.audio.map((c) => c.toLowerCase());
  const known = codecs.filter((c): c is string => !!c);
  return known.length && !known.some((c) => ok.includes(c.toLowerCase())) ? known : [];
}
