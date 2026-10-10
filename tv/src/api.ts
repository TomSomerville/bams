// The BAMS server, seen from the TV: its address, this TV's session token (Authorization: Bearer), and media URLs.
// The TV's video player and <img> tags can't send headers, so media goes through a ticket path
// (/api/t/<ticket>/...) that the server hands out (GET /api/media-ticket). Server side: server/bams/devices.py.

export type { ItemSummary, ItemDetail, ContinueItem, FileInfo, AudioTrack, SubtitleTrack, Probe, User, QueueTrack,
  Playlist, PlaylistSummary, ServerLibrary }
  from "../../web/src/api";
import type { User } from "../../web/src/api";
import type { Source } from "../../web/src/everywhere";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** Fired on window when the server no longer accepts this TV's token (signed out from the web, password changed). */
export const SIGNED_OUT = "bams:signed-out";

const KEYS = { server: "bams.server", token: "bams.token", user: "bams.user" };

function read(k: string): string | null {
  try {
    return localStorage.getItem(k);
  } catch {
    return null;
  }
}

function write(k: string, v: string | null) {
  try {
    if (v === null) localStorage.removeItem(k);
    else localStorage.setItem(k, v);
  } catch { /* storage unavailable: this session only */ }
}

let server = read(KEYS.server);
let token = read(KEYS.token);
let ticket: { prefix: string; at: number } | null = null;

export const getServer = () => server;
export const getToken = () => token;
export function savedUser(): User | null {
  try {
    return JSON.parse(read(KEYS.user) || "null");
  } catch {
    return null;
  }
}

/** "192.168.1.20", "192.168.1.20:8484" or a full URL -> "http://192.168.1.20:8484". */
export function normalizeServer(input: string): string | null {
  let s = input.trim().replace(/\/+$/, "");
  if (!s) return null;
  if (!/^https?:\/\//i.test(s)) s = `http://${s}`;
  try {
    const u = new URL(s);
    if (!u.port && u.protocol === "http:") u.port = "8484";
    return `${u.protocol}//${u.host}`;
  } catch {
    return null;
  }
}

export function setServer(url: string | null) {
  server = url;
  write(KEYS.server, url);
}

export function setSession(t: string | null, user: User | null = null) {
  token = t;
  ticket = null;
  write(KEYS.token, t);
  write(KEYS.user, user ? JSON.stringify(user) : null);
}

export type Hello = { app: string; version: string; name: string };

/** Is there a BAMS server at `base`? Its hello, or null (nothing there, not BAMS, or too slow). */
export async function hello(base: string, timeoutMs = 2500): Promise<Hello | null> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const r = await fetch(`${base}/api/hello`, { signal: ctl.signal });
    const d = r.ok ? await r.json() : null;
    return d && d.app === "bams" ? d : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

async function call<T>(method: string, path: string, body?: unknown, opts: { auth?: boolean; keepalive?: boolean } = {}): Promise<T> {
  if (!server) throw new ApiError(0, "No server chosen.");
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["content-type"] = "application/json";
  if (token && opts.auth !== false) headers.authorization = `Bearer ${token}`;
  let r: Response;
  try {
    r = await fetch(server + path, {
      method, headers, keepalive: opts.keepalive,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, `Can't reach the BAMS server at ${server.replace(/^https?:\/\//, "")}.`);
  }
  if (r.status === 204) return undefined as T;
  const data = await r.json().catch(() => null);
  if (r.status === 401 && token && opts.auth !== false && !path.startsWith("/api/auth/token")) {
    window.dispatchEvent(new Event(SIGNED_OUT));
  }
  if (!r.ok) {
    const d = data?.detail;
    const msg = typeof d === "string" ? d : Array.isArray(d) ? d.map((x: { msg: string }) => x.msg).join("; ") : `HTTP ${r.status}`;
    throw new ApiError(r.status, msg);
  }
  return data as T;
}

export const api = {
  get: <T>(p: string) => call<T>("GET", p),
  post: <T>(p: string, b?: unknown) => call<T>("POST", p, b ?? {}),
  put: <T>(p: string, b: unknown, keepalive = false) => call<T>("PUT", p, b, { keepalive }),
  del: <T>(p: string) => call<T>("DELETE", p),
  /** public endpoints (linking): no token sent */
  publicPost: <T>(p: string, b: unknown) => call<T>("POST", p, b, { auth: false }),
  text: async (p: string): Promise<string> => {
    const r = await fetch(server + p, { headers: token ? { authorization: `Bearer ${token}` } : {} });
    if (!r.ok) throw new ApiError(r.status, `HTTP ${r.status}`);
    return r.text();
  },
};

const TICKET_REFRESH = 6 * 3600 * 1000;  // the server's last 24 h; ask again well before that

/** Get (or refresh) the media ticket. Call before showing pictures or playing. */
export async function refreshTicket(force = false): Promise<void> {
  if (!force && ticket && Date.now() - ticket.at < TICKET_REFRESH) return;
  const t = await api.get<{ prefix: string }>("/api/media-ticket");
  ticket = { prefix: t.prefix, at: Date.now() };
}

/** A media URL the server gave ("/api/images/...", "/api/files/3/stream", "/api/hls/...") as one the player and
 *  <img> can load by themselves. */
export function media(path: string | null | undefined): string | null {
  if (!path || !server) return null;
  if (!ticket || !path.startsWith("/api/")) return server + path;
  return server + ticket.prefix + path.slice(4);
}

// ---- more servers. Besides the server it was set up with (above), this TV can show any number of other BAMS
// servers, each linked to an account there. The list is this TV's own (localStorage): another TV, or a browser,
// keeps its own. The TV talks to each directly, exactly as to the first: bearer token, media through its tickets.

export type ExtraLibrary = { id: number; name: string; type: "movie" | "show" | "music" };
export type Extra = {
  id: number;
  url: string;
  name: string;
  user: User | null;
  /** null: that server stopped accepting it (link again) */
  token: string | null;
  /** its libraries when last seen */
  libraries: ExtraLibrary[];
  /** which of them this TV shows (library id -> false = hidden) */
  hidden: Record<string, boolean>;
};

const EXTRAS = "bams.servers";
const extraTickets = new Map<number, { prefix: string; at: number }>();

export function extras(): Extra[] {
  try {
    const v = JSON.parse(read(EXTRAS) || "[]");
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

function saveExtras(list: Extra[]) {
  write(EXTRAS, JSON.stringify(list));
}

export function updateExtra(id: number, f: (e: Extra) => Extra) {
  saveExtras(extras().map((e) => (e.id === id ? f(e) : e)));
}

/** Add a server (or link one already in the list again: its choices stay). */
export function addExtra(url: string, name: string, token: string, user: User | null) {
  const list = extras();
  const old = list.find((e) => e.url === url);
  if (old?.token && old.token !== token) void fetchAt(old, "POST", "/api/auth/logout").catch(() => undefined);
  extraTickets.delete(old?.id ?? -1);
  const e: Extra = { id: old?.id ?? Math.max(0, ...list.map((x) => x.id)) + 1, url, name, user, token,
    libraries: old?.libraries ?? [], hidden: old?.hidden ?? {} };
  saveExtras(old ? list.map((x) => (x.id === old.id ? e : x)) : [...list, e]);
}

/** Forget a server on this TV (and sign the TV out there, if it can be reached). */
export function removeExtra(id: number) {
  const e = extras().find((x) => x.id === id);
  if (e?.token) void fetchAt(e, "POST", "/api/auth/logout").catch(() => undefined);
  extraTickets.delete(id);
  saveExtras(extras().filter((x) => x.id !== id));
}

/** A request to another server with its token. Its 401 marks it signed out here; it never signs the TV out of its
 *  first server. */
async function fetchAt<T>(e: Extra, method: string, path: string, body?: unknown, opts: { keepalive?: boolean; timeout?: number } = {}): Promise<T> {
  if (!e.token) throw new ApiError(403, `This TV is signed out of ${e.name}. Link it again in Settings.`);
  const ctl = opts.timeout ? new AbortController() : null;
  const timer = ctl ? setTimeout(() => ctl.abort(), opts.timeout) : null;
  let r: Response;
  try {
    r = await fetch(e.url + path, {
      method, keepalive: opts.keepalive, signal: ctl?.signal,
      headers: { authorization: `Bearer ${e.token}`, ...(body === undefined ? {} : { "content-type": "application/json" }) },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, `Can't reach ${e.name} (${e.url.replace(/^https?:\/\//, "")}).`);
  } finally {
    if (timer) clearTimeout(timer);
  }
  if (r.status === 401) {
    updateExtra(e.id, (x) => (x.token === e.token ? { ...x, token: null } : x));
    throw new ApiError(403, `This TV is signed out of ${e.name}. Link it again in Settings.`);
  }
  if (r.status === 204) return undefined as T;
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    const d = data?.detail;
    throw new ApiError(r.status, typeof d === "string" ? d : `HTTP ${r.status}`);
  }
  return data as T;
}

const findExtra = (rid: number) => {
  const e = extras().find((x) => x.id === rid);
  if (!e) throw new ApiError(404, "That server isn't on this TV any more.");
  return e;
};

async function ensureExtraTicket(e: Extra) {
  const t = extraTickets.get(e.id);
  if (t && Date.now() - t.at < TICKET_REFRESH) return;
  const r = await fetchAt<{ prefix: string }>(e, "GET", "/api/media-ticket");
  extraTickets.set(e.id, { prefix: r.prefix, at: Date.now() });
}

export type Api = {
  get: <T>(p: string) => Promise<T>;
  post: <T>(p: string, b?: unknown) => Promise<T>;
  put: <T>(p: string, b: unknown, keepalive?: boolean) => Promise<T>;
  del: <T>(p: string) => Promise<T>;
  text: (p: string) => Promise<string>;
};

const extraApis = new Map<number, Api>();

/** The API of server `rid` (undefined = the TV's first server). Media tickets are fetched along the way, so
 *  mediaFor(rid) works for anything a call returned. */
export function apiFor(rid: number | undefined): Api {
  if (rid === undefined) return api;
  let a = extraApis.get(rid);
  if (!a) {
    const go = async <T,>(method: string, p: string, b?: unknown, keepalive = false) => {
      const e = findExtra(rid);
      await ensureExtraTicket(e);
      return fetchAt<T>(e, method, p, b, { keepalive });
    };
    a = {
      get: (p) => go("GET", p),
      post: (p, b) => go("POST", p, b ?? {}),
      put: (p, b, keepalive) => go("PUT", p, b, keepalive),
      del: (p) => go("DELETE", p),
      text: async (p) => {
        const e = findExtra(rid);
        const r = await fetch(e.url + p, { headers: e.token ? { authorization: `Bearer ${e.token}` } : {} });
        if (!r.ok) throw new ApiError(r.status, `HTTP ${r.status}`);
        return r.text();
      },
    };
    extraApis.set(rid, a);
  }
  return a;
}

/** media() for server `rid` (undefined = the TV's first server). */
export function mediaFor(rid: number | undefined): (path: string | null | undefined) => string | null {
  if (rid === undefined) return media;
  return (path) => {
    const e = extras().find((x) => x.id === rid);
    if (!path || !e) return null;
    const t = extraTickets.get(rid);
    if (!t || !path.startsWith("/api/")) return e.url + path;
    return e.url + t.prefix + path.slice(4);
  };
}

/** Ask each other server for its libraries now (a few seconds at most for one that's offline). Returns, per id,
 *  null when it answered or why not; the libraries are kept for when it doesn't. */
export async function checkExtras(): Promise<Record<number, string | null>> {
  const out: Record<number, string | null> = {};
  await Promise.all(extras().map(async (e) => {
    if (!e.token) return void (out[e.id] = "signed out");
    try {
      await ensureExtraTicket(e);
      const libs = await fetchAt<ExtraLibrary[]>(e, "GET", "/api/libraries", undefined, { timeout: 4000 });
      const name = (await hello(e.url))?.name || e.name;  // its admin may have renamed it since
      updateExtra(e.id, (x) => ({ ...x, name, libraries: libs.map((l) => ({ id: l.id, name: l.name, type: l.type })) }));
      out[e.id] = null;
    } catch (er) {
      out[e.id] = (er as ApiError).status === 403 ? "signed out" : "offline";
    }
  }));
  return out;
}

/** POST to a public endpoint of a server that isn't on the TV yet (linking it). */
export async function publicPostTo<T>(base: string, path: string, body: unknown): Promise<T> {
  let r: Response;
  try {
    r = await fetch(base + path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  } catch {
    throw new ApiError(0, `Can't reach the BAMS server at ${base.replace(/^https?:\/\//, "")}.`);
  }
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    const d = data?.detail;
    throw new ApiError(r.status, typeof d === "string" ? d : `HTTP ${r.status}`);
  }
  return data as T;
}

/** Every server this TV shows, for Home and Search (web/src/everywhere.ts): its first server, then each other one
 *  that's linked. A Source's rid null is the first server (screens use undefined for it). */
export function sources(): Source[] {
  return [
    { rid: null, get: api.get },
    ...extras().filter((e) => e.token).map((e) => ({ rid: e.id, get: apiFor(e.id).get })),
  ];
}

/** null (a Source's first server) -> undefined (the screens' first server). */
export const ridOf = (rid: number | null | undefined): number | undefined => rid ?? undefined;
