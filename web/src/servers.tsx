// Other BAMS servers this browser is connected to. The web app is a client: besides the server it was loaded from,
// it can show any number of other BAMS servers, each signed in with an account *there*. The list lives in this
// browser (localStorage), like the TV app keeps its own: each device has its own servers.
//
// The browser talks to each server directly, the way the TV app does (server: devices.py): a session token from
// POST /api/auth/token sent as `Authorization: Bearer`, and media (images, video, music, subtitles) through the
// server's ticket paths (/api/t/<ticket>/...), which <img>/<video> can load without headers. Links in a server's
// JSON ("/api/images/...", "/api/files/7/stream") are made absolute here as they arrive (`rewrite`): media links
// as ticket URLs, the rest as plain URLs of that server.
//
// Pages under /r/<rid>/... (library, title, playlist, play) show another server: they're the same page
// components; inside a RemoteScope, useApi() and useScope().call go to that server, useScope().to() keeps links
// under /r/<rid>, and useScope().media() makes a hand-built media path loadable.

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Outlet, useParams } from "react-router-dom";
import { api, ApiError, type RemoteServer } from "./api";
import { askAll, type Source, type Tagged } from "./everywhere";

/** Window event: a server was added, signed in again, removed, renamed/hidden a library, or signed out. */
export const REMOTES_CHANGED = "bams:remotes";

const STORE = "bams.servers";
const MEDIA = ["/api/files/", "/api/hls/", "/api/images/"];  // what a ticket opens (server: devices.MEDIA_PREFIXES)
const TICKET_REFRESH = 6 * 3600 * 1000;  // tickets last 24 h on the server; ask again well before that
const LIST_TIMEOUT = 4000;  // an offline server mustn't hold the sidebar up for long

type Stored = {
  id: number;
  /** base address that answered, e.g. http://192.168.1.2:8484 */
  url: string;
  name: string;
  account: string;
  is_admin: boolean;
  /** session token there; null = it stopped accepting it (sign in again) */
  token: string | null;
  /** its libraries when last seen */
  libraries: { id: number; name: string; type: "movie" | "show" | "music" }[];
  /** this browser's names and choices per library id */
  prefs: Record<string, { name?: string; show?: boolean }>;
};

function load(): Stored[] {
  try {
    const v = JSON.parse(localStorage.getItem(STORE) || "[]");
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

function save(list: Stored[]) {
  try {
    localStorage.setItem(STORE, JSON.stringify(list));
  } catch { /* storage unavailable: this page only */ }
  window.dispatchEvent(new Event(REMOTES_CHANGED));
}

function update(id: number, f: (s: Stored) => Stored) {
  save(load().map((s) => (s.id === id ? f(s) : s)));
}

const find = (id: number | null) => (id === null ? null : load().find((s) => s.id === id) ?? null);

/** Which server a media URL belongs to (null = this one): the music bar links its track's album. */
export function ridOf(url: string | null | undefined): number | null {
  if (!url || !/^https?:\/\//.test(url)) return null;
  return load().find((s) => url.startsWith(`${s.url}/`))?.id ?? null;
}

/** "/title/5" as a page of server `rid`. */
export function scopeLink(rid: number | null, p: string): string {
  return rid === null ? p : `/r/${rid}${p}`;
}

// ---- talking to another server

const tickets = new Map<number, { prefix: string; at: number }>();

async function ensureTicket(s: Stored) {
  const t = tickets.get(s.id);
  if (t && Date.now() - t.at < TICKET_REFRESH) return;
  const r = await raw<{ prefix: string }>(s, "GET", "/api/media-ticket");
  tickets.set(s.id, { prefix: r.prefix, at: Date.now() });
}

/** A link from server `s` ("/api/...") as one this browser can use: media through a ticket, the rest plain. */
function absolute(s: Stored, p: string): string {
  if (!p.startsWith("/api/")) return p;
  const t = tickets.get(s.id);
  return t && MEDIA.some((m) => p.startsWith(m)) ? s.url + t.prefix + p.slice(4) : s.url + p;
}

function rewrite(s: Stored, data: unknown): unknown {
  if (typeof data === "string") return absolute(s, data);
  if (Array.isArray(data)) return data.map((x) => rewrite(s, x));
  if (data && typeof data === "object") {
    return Object.fromEntries(Object.entries(data).map(([k, v]) => [k, rewrite(s, v)]));
  }
  return data;
}

async function raw<T>(s: Stored, method: string, path: string, body?: unknown,
                      opts: { keepalive?: boolean; timeout?: number } = {}): Promise<T> {
  if (!s.token) throw new ApiError(403, `You're signed out of ${s.name}. Sign in again in Settings → Other BAMS servers.`);
  const url = /^https?:\/\//.test(path) ? path : s.url + path;
  const ctl = opts.timeout ? new AbortController() : null;
  const timer = ctl ? window.setTimeout(() => ctl.abort(), opts.timeout) : 0;
  let r: Response;
  try {
    r = await fetch(url, {
      method, keepalive: opts.keepalive, signal: ctl?.signal,
      headers: { authorization: `Bearer ${s.token}`, ...(body === undefined ? {} : { "content-type": "application/json" }) },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, `Can't reach ${s.name} (${s.url}) right now.`);
  } finally {
    window.clearTimeout(timer);
  }
  if (r.status === 401) {
    // its sign-in ended there (signed out, password changed): never this server's sign-in screen
    update(s.id, (x) => (x.token === s.token ? { ...x, token: null } : x));
    throw new ApiError(403, `You're signed out of ${s.name}. Sign in again in Settings → Other BAMS servers.`);
  }
  if (r.status === 204) return undefined as T;
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    const d = data?.detail;
    throw new ApiError(r.status, typeof d === "string" ? d : `HTTP ${r.status}`);
  }
  return data as T;
}

/** api.get/post/... on another server: its links come back usable from here (`rewrite`). */
async function remoteCall<T>(rid: number, method: string, path: string, body?: unknown, keepalive = false): Promise<T> {
  const s = find(rid);
  if (!s) throw new ApiError(404, "That server isn't connected any more.");
  await ensureTicket(s);
  return rewrite(s, await raw<T>(s, method, path, body, { keepalive })) as T;
}

export type Call = typeof api & {
  /** like fetch with keepalive (reports while a page closes); errors are the caller's to ignore */
  send: (method: string, path: string, body?: unknown, keepalive?: boolean) => Promise<unknown>;
};

const localCall: Call = {
  ...api,
  send: (method, path, body, keepalive) => fetch(path, {
    method, keepalive, headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  }),
};

const calls = new Map<number, Call>();  // one per server, so hooks that depend on it don't refetch for nothing

/** api.get/post/... on server `rid` (null = this one). */
export function callFor(rid: number | null): Call {
  if (rid === null) return localCall;
  let c = calls.get(rid);
  if (!c) calls.set(rid, (c = makeCall(rid)));
  return c;
}

function makeCall(rid: number): Call {
  return {
    get: <T,>(p: string) => remoteCall<T>(rid, "GET", p),
    post: <T,>(p: string, b?: unknown) => remoteCall<T>(rid, "POST", p, b ?? {}),
    put: <T,>(p: string, b: unknown) => remoteCall<T>(rid, "PUT", p, b),
    patch: <T,>(p: string, b: unknown) => remoteCall<T>(rid, "PATCH", p, b),
    del: <T,>(p: string) => remoteCall<T>(rid, "DELETE", p),
    send: (method, p, b, keepalive) => remoteCall(rid, method, p, b, keepalive),
  };
}

// ---- connecting

const DEFAULT_PORT = 8484;

/** Addresses to try for what someone typed: "192.168.1.2", "media.example.com", "host:9000", "https://…". */
function candidates(address: string): string[] {
  const a = address.trim().replace(/\/+$/, "").replace(/\/api$/, "");
  if (!a) throw new ApiError(400, "Type the address of the other BAMS server.");
  if (/^https?:\/\//i.test(a)) return [a];
  if (/[\s/\\?#@]/.test(a)) throw new ApiError(400, "That doesn't look like a server address.");
  if (/:\d+$/.test(a)) return [`http://${a}`, `https://${a}`];
  return [`http://${a}:${DEFAULT_PORT}`, `https://${a}`, `http://${a}`];
}

async function hello(base: string): Promise<{ app: string; name: string } | null> {
  const ctl = new AbortController();
  const t = window.setTimeout(() => ctl.abort(), 5000);
  try {
    const r = await fetch(`${base}/api/hello`, { signal: ctl.signal });
    const d = r.ok ? await r.json() : null;
    return d?.app === "bams" ? d : null;
  } catch {
    return null;
  } finally {
    window.clearTimeout(t);
  }
}

function deviceName(): string {
  const ua = navigator.userAgent;
  const browser = /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome"
    : /Safari\//.test(ua) ? "Safari" : "Browser";
  return `${browser} · BAMS web on ${location.host}`.slice(0, 100);
}

/** Connect this browser to a server (or sign in to one already in the list again: its names and choices stay). */
export async function connectServer(address: string, name: string, password: string): Promise<void> {
  let base: string | null = null;
  let hi: { name: string } | null = null;
  for (const c of candidates(address)) {
    if ((hi = await hello(c))) { base = c; break; }
  }
  if (!base || !hi) {
    throw new ApiError(502, `No BAMS server answered at ${address.trim()}. Check the address (and the port, if it isn't `
      + `${DEFAULT_PORT}), that the server is running, and that this computer can reach it.`);
  }
  let r: Response;
  try {
    r = await fetch(`${base}/api/auth/token`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ name: name.trim(), password, device: deviceName() }),
    });
  } catch {
    throw new ApiError(0, `Couldn't reach ${hi.name} to sign in. Try again.`);
  }
  const data = await r.json().catch(() => null);
  if (r.status === 404) throw new ApiError(400, `${hi.name} runs an older BAMS that can't be connected to. Update it first.`);
  if (!r.ok) throw new ApiError(r.status, `${hi.name} said: ${typeof data?.detail === "string" ? data.detail : `HTTP ${r.status}`}`);
  const list = load();
  const old = list.find((s) => s.url === base);
  const entry: Stored = {
    id: old?.id ?? Math.max(0, ...list.map((s) => s.id)) + 1, url: base, name: String(hi.name || base).slice(0, 100),
    account: data.user.name, is_admin: !!data.user.is_admin, token: data.token,
    libraries: old?.libraries ?? [], prefs: old?.prefs ?? {},
  };
  if (old?.token && old.token !== data.token) void raw(old, "POST", "/api/auth/logout").catch(() => undefined);
  tickets.delete(entry.id);
  save(old ? list.map((s) => (s.id === old.id ? entry : s)) : [...list, entry]);
}

/** Forget a server here (and end this browser's session there, if it can be reached). */
export function removeServer(id: number) {
  const s = find(id);
  if (s?.token) void raw(s, "POST", "/api/auth/logout").catch(() => undefined);
  tickets.delete(id);
  save(load().filter((x) => x.id !== id));
}

/** Rename one of a server's libraries here ("" = its own name) and/or show/hide it in the sidebar. */
export function setLibrary(id: number, libraryId: number, change: { name?: string; show?: boolean }) {
  update(id, (s) => {
    const p = { ...(s.prefs[libraryId] ?? {}) };
    if (change.name !== undefined) {
      const n = change.name.split(/\s+/).filter(Boolean).join(" ").slice(0, 100);
      if (n) p.name = n;
      else delete p.name;
    }
    if (change.show !== undefined) p.show = change.show;
    return { ...s, prefs: { ...s.prefs, [libraryId]: p } };
  });
}

function describe(s: Stored, online: boolean, error: string | null): RemoteServer {
  return {
    id: s.id, name: s.name, url: s.url, account: s.account, is_admin: s.is_admin, signed_in: !!s.token, online, error,
    libraries: s.libraries.map((l) => ({
      id: l.id, type: l.type, own_name: l.name,
      name: s.prefs[l.id]?.name || l.name, show: s.prefs[l.id]?.show ?? true,
    })),
  };
}

// ---- React side

export type Scope = {
  rid: number | null;
  /** the other server (null on this one, or while the list loads) */
  remote: RemoteServer | null;
  /** api.get/post/... on this page's server */
  call: Call;
  /** a hand-built media path ("/api/files/3/remux") as a URL <video>/<img> can load from this page's server */
  media: (p: string) => string;
  /** "/title/5" as a page of this page's server */
  to: (p: string) => string;
  /** a library's name as it's called here (other servers' libraries can be renamed in this browser) */
  libName: (id: number, name: string) => string;
};

function makeScope(rid: number | null, remote: RemoteServer | null): Scope {
  return {
    rid, remote, call: callFor(rid),
    media: (p) => {
      const s = find(rid);
      return s ? absolute(s, p) : p;
    },
    to: (p) => scopeLink(rid, p),
    libName: (id, name) => remote?.libraries.find((l) => l.id === id)?.name ?? name,
  };
}

const LOCAL = makeScope(null, null);
const ScopeCtx = createContext<Scope>(LOCAL);

export function useScope(): Scope {
  return useContext(ScopeCtx);
}

type Remotes = { servers: RemoteServer[] | null; reload: () => void };
const RemotesCtx = createContext<Remotes>({ servers: null, reload: () => {} });

export function useRemotes(): Remotes {
  return useContext(RemotesCtx);
}

/** This browser's other servers, for the sidebar, Settings and the /r/<rid> pages: each one asked for its
 *  libraries now (an offline one shows what it had last time). */
export function RemotesProvider({ children }: { children: ReactNode }) {
  const [servers, setServers] = useState<RemoteServer[] | null>(null);
  const live = useRef<Record<number, string | null>>({});  // id -> null (answered) or why not

  const show = useCallback(() => {
    const state = live.current;
    setServers(load().map((s) => describe(s, s.token !== null && state[s.id] === null,
      !s.token ? "signed out" : state[s.id] === undefined ? null : state[s.id])));
  }, []);

  const reload = useCallback(() => {
    const list = load();
    show();
    Promise.all(list.map(async (s): Promise<[number, string | null]> => {
      if (!s.token) return [s.id, "signed out"];
      try {
        const libs = await raw<Stored["libraries"]>(s, "GET", "/api/libraries", undefined, { timeout: LIST_TIMEOUT });
        const slim = libs.map((l) => ({ id: l.id, name: l.name, type: l.type }));
        const name = (await hello(s.url))?.name || s.name;  // its admin may have renamed it since
        if (name !== s.name || JSON.stringify(slim) !== JSON.stringify(s.libraries)) {
          // quietly: saving fires REMOTES_CHANGED, which would ask every server again
          try {
            localStorage.setItem(STORE, JSON.stringify(load().map((x) => (x.id === s.id ? { ...x, name, libraries: slim } : x))));
          } catch { /* not kept */ }
        }
        return [s.id, null];
      } catch (e) {
        return [s.id, (e as ApiError).status === 403 ? "signed out" : "offline"];
      }
    })).then((r) => {
      live.current = Object.fromEntries(r);
      show();
    });
  }, [show]);

  useEffect(() => {
    reload();
    window.addEventListener(REMOTES_CHANGED, reload);
    return () => window.removeEventListener(REMOTES_CHANGED, reload);
  }, [reload]);
  const value = useMemo(() => ({ servers, reload }), [servers, reload]);
  return <RemotesCtx.Provider value={value}>{children}</RemotesCtx.Provider>;
}

/** The server an item is on: its own tag (Home and Search mix servers), else this page's. */
export function useItemServer(item: { rid?: number | null }): { rid: number | null; to: (p: string) => string } {
  const scope = useScope();
  const rid = item.rid !== undefined ? item.rid : scope.rid;
  return { rid, to: (p) => scopeLink(rid, p) };
}

/** Every server this browser shows, for Home and Search (everywhere.ts): this one first, then each other one
 *  that's signed in. */
export function useSources(): Source[] {
  const { servers } = useRemotes();
  const ids = (servers ?? []).filter((s) => s.signed_in).map((s) => s.id).join(",");
  return useMemo(() => [
    { rid: null, get: localCall.get },
    ...(ids ? ids.split(",").map(Number) : []).map((rid) => ({ rid, get: callFor(rid).get })),
  ], [ids]);
}

/** GET `path` from every source (null = nothing): one list per server, in the sources' order, filled in as each
 *  answers. `done` once all have answered (or given up). */
export function useEverywhere<T>(sources: Source[], path: string | null): { lists: Tagged<T>[][]; done: boolean } {
  const [got, setGot] = useState<Map<number | null, Tagged<T>[]>>(new Map());
  const [done, setDone] = useState(false);
  useEffect(() => {
    setGot(new Map());
    setDone(false);
    if (!path) return;
    let alive = true;
    void askAll<T>(sources, path, (rid, list) => {
      if (alive) setGot((m) => new Map(m).set(rid, list));
    }).then(() => { if (alive) setDone(true); });
    return () => { alive = false; };
  }, [sources, path]);
  const lists = useMemo(() => sources.filter((s) => got.has(s.rid)).map((s) => got.get(s.rid)!), [sources, got]);
  return { lists, done };
}

/** Route element for /r/:rid/…: the pages below it show that server. */
export function RemoteScope() {
  const rid = Number(useParams().rid);
  const { servers } = useRemotes();
  const remote = servers?.find((s) => s.id === rid) ?? null;
  const scope = useMemo(() => makeScope(rid, remote), [rid, remote]);
  if (servers && !remote) {
    return <div className="page"><h1>Not connected</h1>
      <p className="muted">This browser isn't connected to that server any more. Connect it again in Settings.</p></div>;
  }
  return <ScopeCtx.Provider value={scope}><Outlet /></ScopeCtx.Provider>;
}
