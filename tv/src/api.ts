// The BAMS server, seen from the TV: its address, this TV's session token (Authorization: Bearer), and media URLs.
// The TV's video player and <img> tags can't send headers, so media goes through a ticket path
// (/api/t/<ticket>/...) that the server hands out (GET /api/media-ticket). Server side: server/bams/devices.py.

export type { ItemSummary, ItemDetail, ContinueItem, WatchlistItem, FileInfo, AudioTrack, SubtitleTrack, Probe, User, QueueTrack,
  Playlist, PlaylistSummary, ServerLibrary, SubtitleSearch, SubtitleResult, UserPlaylist, UserPlaylistSummary }
  from "../../web/src/api";
import type { User } from "../../web/src/api";
import type { Source } from "../../web/src/everywhere";
import { local, theatre } from "./platform";

export class ApiError extends Error {
  /** `data`: the server's whole answer ({detail, code_required…}) */
  constructor(public status: number, message: string, public data?: Record<string, unknown> | null) {
    super(message);
  }
}

/** Fired on window when the server no longer accepts this TV's token (signed out from the web, password changed). */
export const SIGNED_OUT = "bams:signed-out";

const KEYS = { server: "bams.server", token: "bams.token", user: "bams.user" };

// theatre mode keeps its own keys, apart from the web UI's on the same origin (platform.ts)
const read = (k: string): string | null => local.get(k);

function write(k: string, v: string | null) {
  if (v === null) local.remove(k);
  else local.set(k, v);
}

// theatre mode: the server the page came from is its first server (platform.ts)
let server = theatre() ? location.origin : read(KEYS.server);
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
    const r = await fetch(`${base}/api/hello`, { signal: ctl.signal, credentials: "omit" });
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
      method, headers, keepalive: opts.keepalive, credentials: "omit",
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
    throw new ApiError(r.status, msg, data);
  }
  return data as T;
}

export const api = {
  get: <T>(p: string) => call<T>("GET", p),
  post: <T>(p: string, b?: unknown) => call<T>("POST", p, b ?? {}),
  put: <T>(p: string, b: unknown, keepalive = false) => call<T>("PUT", p, b, { keepalive }),
  patch: <T>(p: string, b: unknown) => call<T>("PATCH", p, b),
  del: <T>(p: string) => call<T>("DELETE", p),
  /** public endpoints (linking): no token sent */
  publicPost: <T>(p: string, b: unknown) => call<T>("POST", p, b, { auth: false }),
  text: async (p: string): Promise<string> => {
    const r = await fetch(server + p, { credentials: "omit", headers: token ? { authorization: `Bearer ${token}` } : {} });
    if (!r.ok) throw new ApiError(r.status, `HTTP ${r.status}`);
    return r.text();
  },
};

// Every request above omits cookies: in theatre mode the page shares its origin with the web UI, and the server
// would take the web UI's session cookie over this page's token (and a sign-out would end the web UI's session).

/** Theatre mode: who is signed in to the web UI in this browser (its cookie), or null. The one read that sends it. */
export async function webUser(): Promise<User | null> {
  if (!theatre()) return null;
  try {
    const r = await fetch("/api/auth/state", { credentials: "same-origin" });
    return r.ok ? ((await r.json()) as { user: User | null }).user : null;
  } catch {
    return null;
  }
}

/** Theatre mode: link this page to the account signed in to the web UI here, like entering the link code on the web:
 *  a code, approved with the web UI's cookie (same origin), then the token. */
export async function linkWithWebUser(device: string): Promise<{ token: string; user: User }> {
  const s = await api.publicPost<{ code: string; secret: string }>("/api/devices/link", { name: device });
  const ok = await fetch("/api/devices/approve", {
    method: "POST", credentials: "same-origin", headers: { "content-type": "application/json" },
    body: JSON.stringify({ code: s.code }),
  });
  if (!ok.ok) throw new ApiError(ok.status, "The web UI's sign-in wasn't accepted. Sign in with name and password.");
  const r = await api.publicPost<{ status: string; token?: string; user?: User }>("/api/devices/link/poll", { secret: s.secret });
  if (r.status !== "linked" || !r.token || !r.user) throw new ApiError(0, "Linking didn't finish. Try again.");
  return { token: r.token, user: r.user };
}

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
      method, keepalive: opts.keepalive, signal: ctl?.signal, credentials: "omit",
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
  patch: <T>(p: string, b: unknown) => Promise<T>;
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
      patch: (p, b) => go("PATCH", p, b),
      del: (p) => go("DELETE", p),
      text: async (p) => {
        const e = findExtra(rid);
        const r = await fetch(e.url + p, { credentials: "omit", headers: e.token ? { authorization: `Bearer ${e.token}` } : {} });
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

// ---- tickets after a server restart. A ticket is signed with a key that lives only in the server's process, so a
// server update or restart kills every ticket, while a TV or theatre PC that only slept keeps its page (and its old
// tickets) for hours. When media fails to load, or the page comes back from a sleep, ask every server again.

let lastRenew = 0;

/** Fresh media tickets from every server (at most every 20 s, however many pictures failed at once). */
export async function renewTickets(): Promise<void> {
  if (Date.now() - lastRenew < 20000) return;
  lastRenew = Date.now();
  extraTickets.clear();
  await Promise.all([
    token ? refreshTicket(true).catch(() => undefined) : undefined,
    ...extras().filter((e) => e.token).map((e) => ensureExtraTicket(e).catch(() => undefined)),
  ]);
}

/** A media URL made with an old ticket, made again with the current one ("…/api/t/<old>/images/x" → "…/api/t/<new>/images/x"). */
export function withFreshTicket(url: string): string | null {
  const m = /^(https?:\/\/[^/]+)\/api\/t\/[^/]+(\/.*)$/.exec(url);
  if (!m) return null;
  const [, base, rest] = m;
  if (base === server) return media(`/api${rest}`);
  const e = extras().find((x) => x.url === base);
  return e ? mediaFor(e.id)(`/api${rest}`) : null;
}

/** POST to a public endpoint of a server that isn't on the TV yet (linking it). */
export async function publicPostTo<T>(base: string, path: string, body: unknown): Promise<T> {
  let r: Response;
  try {
    r = await fetch(base + path, { method: "POST", credentials: "omit", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  } catch {
    throw new ApiError(0, `Can't reach the BAMS server at ${base.replace(/^https?:\/\//, "")}.`);
  }
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    const d = data?.detail;
    throw new ApiError(r.status, typeof d === "string" ? d : `HTTP ${r.status}`, data);
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
