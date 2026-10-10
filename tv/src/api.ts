// The BAMS server, seen from the TV: its address, this TV's session token (Authorization: Bearer), and media URLs.
// The TV's video player and <img> tags can't send headers, so media goes through a ticket path
// (/api/t/<ticket>/...) that the server hands out (GET /api/media-ticket). Server side: server/bams/devices.py.

export type { ItemSummary, ItemDetail, ContinueItem, FileInfo, AudioTrack, SubtitleTrack, Probe, User }
  from "../../web/src/api";
import type { User } from "../../web/src/api";

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
