// Thin client for the BAMS server API (server/bams/app.py). Same origin in production;
// the Vite dev server proxies /api to 127.0.0.1:8484.

export class ApiError extends Error {
  /** `data`: the server's whole answer ({detail, code_required, must_change_password…}) */
  constructor(public status: number, message: string, public data?: Record<string, unknown> | null) {
    super(message);
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  let r: Response;
  try {
    r = await fetch(path, {
      method,
      headers: body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Can't reach the BAMS server.");
  }
  if (r.status === 204) return undefined as T;
  const data = await r.json().catch(() => null);
  // signed out (expired, or by an admin): the AuthProvider shows the sign-in screen
  if (r.status === 401 && !path.startsWith("/api/auth/")) window.dispatchEvent(new Event(SIGNED_OUT));
  if (!r.ok) {
    const d = data?.detail;
    const msg = typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x.msg).join("; ") : `HTTP ${r.status}`;
    throw new ApiError(r.status, msg, data);
  }
  return data as T;
}

/** Fired on window when the server says this browser isn't signed in. */
export const SIGNED_OUT = "bams:signed-out";

/** Window event: libraries were added, renamed, removed or reordered (the sidebar reloads its list). */
export const LIBRARIES_CHANGED = "bams:libraries";

export const api = {
  get: <T>(p: string) => call<T>("GET", p),
  post: <T>(p: string, b?: unknown) => call<T>("POST", p, b ?? {}),
  put: <T>(p: string, b: unknown) => call<T>("PUT", p, b),
  patch: <T>(p: string, b: unknown) => call<T>("PATCH", p, b),
  del: <T>(p: string) => call<T>("DELETE", p),
};

// ---- shapes returned by the server

export type TmdbStatus = { configured: boolean; kind: "token" | "apikey" | null; last4: string | null; verified_at: string | null };

export type RootStatus = { path: string; exists: boolean; readable: boolean; os_write_access: boolean | null };

export type ServerLibrary = {
  id: number;
  name: string;
  type: "movie" | "show" | "music";
  scan_interval_hours: number;
  last_scan_at: number | null;
  last_scan_status: string | null;
  roots: RootStatus[];
  counts: Record<string, number>;
  files: { total: number; available: number; bytes: number; unrecognized: number; guessed?: number };
};

export type ScanState = {
  /** the scan being run: its step ("Reading file details"), how far (done of total, bytes) and for how long (s) */
  running: {
    library_id: number; trigger: string; started_at: number; step: string; step_elapsed: number;
    done: number | null; total: number | null; bytes_done: number | null; bytes_total: number | null;
  } | null;
  queued: { library_id: number; trigger: string }[];
};

export type ServerStatus = {
  version: string;
  data_dir: string | null;
  /** paths for admins; for others just whether it's there (true) or not (null) */
  ffprobe: string | boolean | null;
  ffmpeg: string | boolean | null;
  /** the H.264 encoder video transcodes use (null: none works, or no FFmpeg) */
  video_encoder: { id: string; name: string; hardware: boolean; hw_decode: boolean } | null;
  /** video conversions running now (HLS sessions + plain streams) and how many are allowed */
  transcodes: { running: number; limit: number };
  tmdb_configured: boolean;
  scans: ScanState;
};

/** What this server is called in apps' server lists (GET /api/settings → server_name; GET /api/hello → name). */
export type ServerName = { name: string; default: string; custom: boolean };

export type BrowseResult = { path: string | null; parent: string | null; dirs: { name: string; path: string }[] };

/** Each account's own display preferences (server: auth.PREFS). */
/** A row of Home in the user's order: "continue", "recent", "lib:<id>", "top_rated", "genre:<name>"
 *  (older saves have one "genres" entry for all of them). */
export type HomeRowPref = { id: string; show: boolean };
/** GET /api/genres: every show/movie genre, most titles first. */
export type Genre = { name: string; count: number };
export type Prefs = { home_hero: boolean; home_rows: HomeRowPref[] };
export type User = {
  id: number; name: string; is_admin: boolean; created_at?: number; last_login_at?: number | null; prefs?: Prefs;
  /** an admin asked them to set a new password: until they do, the app shows only that */
  must_change_password?: boolean;
  /** two-step sign-in (a code from an authenticator app) is on */
  two_factor?: boolean;
};
/** Admin settings: when a title counts as watched (% of its length) and as started (seconds in). */
export type WatchSettings = { watched_percent: number; resume_after: number };
export type AuthState = { user: User | null; setup: boolean; setup_here: boolean };

/** This user's state of a movie/episode. position 0 = from the start (or finished). */
export type Progress = { position: number; duration: number | null; watched: boolean };

export type ItemKind = "show" | "movie" | "season" | "episode" | "artist" | "album" | "track";
export const MUSIC_KINDS: ItemKind[] = ["artist", "album", "track"];

export type ItemSummary = {
  id: number;
  kind: ItemKind;
  library_id: number;
  title: string;
  year: number | null;
  poster: string | null;
  backdrop: string | null;
  overview: string | null;
  genres: string[];
  rating: number | null;
  runtime: number | null;
  match_status: "pending" | "matched" | "unmatched" | "manual";
  added_at: number;
  child_count: number | null;
  season_number?: number;
  episode_number?: number;
  still?: string | null;
  air_date?: string | null;
  // albums and tracks
  parent_id?: number | null;
  /** an album's artist, a track's album */
  parent_title?: string | null;
  /** seconds */
  duration?: number | null;
  // tracks
  track_number?: number | null;
  disc_number?: number | null;
  /** the performer, when it isn't the album artist */
  artist?: string | null;
  /** client side: the server this item came from (null = the first one; web servers.tsx, TV api.ts) when a
   *  page shows several servers' items together (Home, Search) */
  rid?: number | null;
  // watch state of the signed-in user
  progress?: Progress;
  /** shows/seasons: how many episodes, and how many of them aren't watched */
  episodes?: number;
  unwatched?: number;
};

/** Continue Watching: stopped part-way ("resume") or the next episode of a show ("next"). */
export type ContinueItem = ItemSummary & {
  reason: "resume" | "next";
  show?: { id: number; title: string; poster: string | null; backdrop: string | null };
  season_id?: number;  // episodes: their season (the card's episode line opens it)
  /** when the activity it comes from happened (newer servers): merging several servers' rows */
  last_watched_at?: number;
};

export type AudioTrack = { index: number; label: string; language: string | null; codec: string | null;
  channels: number | null; default: boolean };

/** A subtitle track: embedded ("e{n}") or a file next to the video ("x{n}"). Image tracks have no url: they
 *  can only be burned into a converted video (index = which subtitle stream). */
/** id: "e{n}" embedded, "x{n}" a sidecar file, "x{n}-{k}" stream k of a VobSub .idx/.sub sidecar. Picture
 *  tracks (image) have no url: they're burned in by sending the id as `burn`. */
export type SubtitleTrack = { id: string; index: number; source: "embedded" | "file"; language: string | null;
  label: string; forced: boolean; sdh: boolean; image: boolean; codec: string | null; url: string | null };

export type Probe = {
  container: string | null;
  duration: number | null;
  bitrate: number | null;
  video: {
    codec: string; profile: string | null; resolution: string | null; width: number; height: number;
    hdr: string | null; bit_depth: number;
    /** Dolby Vision profile (5 = no HDR10 base layer); absent on files probed before it was recorded */
    dv_profile?: number | null;
  } | null;
  audio: { codec: string; channels: number | null; language: string | null; title: string | null }[];
  subtitles: { codec: string; language: string | null; title: string | null; forced: boolean; image: boolean }[];
};

export type PlayMethod = "direct_play" | "direct_stream" | "transcode";

export type FileInfo = {
  id: number;
  path: string;
  root: string;
  size: number;
  available: boolean;
  probe: Probe | null;
  release: Record<string, string> | null;
  playback: {
    method: PlayMethod;
    /** "file": original bytes, seek with Range. "remux": video copied + audio converted to AAC; seek with ?t=.
     *  "transcode": video -> H.264 + audio -> AAC (music: audio -> AAC); seek with ?t= (starts exactly there) */
    mode: "file" | "remux" | "transcode";
    url: string;
    /** video: the H.264 transcode of this file, for browsers that can't decode its video (null: no FFmpeg) */
    transcode_url?: string | null;
    /** video: POST here to start an HLS conversion ({height?}) -> {id, playlist}; null without FFmpeg */
    hls_url?: string | null;
    source: "ffprobe" | "filename";
    /** music: the file's container, e.g. "FLAC", "MP4" */
    container?: string | null;
    /** music converted on the fly: what it's converted to (Settings → Music); null when it plays as-is */
    output?: "aac" | "flac" | null;
    video_codec: string | null;
    audio_codec: string | null;
    audio_ok: boolean;
    duration: number | null;
  };
  stream_url: string;
  /** video files */
  audio_tracks?: AudioTrack[];
  /** video files, on a movie's/episode's own page */
  subtitles?: SubtitleTrack[];
};

export type ItemDetail = ItemSummary & {
  parent_id: number | null;
  tagline: string | null;
  parsed_title: string | null;
  ids: { tmdb: number | null; imdb: string | null; tvdb: number | null; musicbrainz: string | null };
  /** Music identification details (MusicBrainz, Wikipedia, photo credit); {} otherwise. */
  extra: MusicExtra;
  match_score: number | null;
  ancestors: ItemSummary[];
  children: ItemSummary[];
  files: FileInfo[];
  /** episodes: the next one in the show (null at the end) */
  next_id?: number | null;
};

/** What a file is, entered by hand (PUT /api/files/:id/identify). No episodes = an extra in that season. */
export type Identification = {
  title: string; year?: number | null; season?: number | null; episodes?: number[]; episode_title?: string | null;
  edition?: string | null; tmdb_id?: number | null;
  skip?: boolean;  // {skip: true}: the admin said not to place the file (no other fields then)
};
/** A file the scanner couldn't place (hint says why), one placed by a best guess (guessed: auto fill, to review),
 *  or one identified by hand (manual). */
export type UnrecognizedFile = FileInfo & {
  hint: string | null; manual: Identification | null; guessed?: boolean;
  library_id: number; library_name: string; library_type: "movie" | "show" | "music";
  guess: { title?: string | null; year?: number | null; season?: number | null; episodes?: number[] | null; episode_title?: string | null };
};
/** What's already in a library, for the identify form's suggestions (GET /api/libraries/:id/names). */
export type LibraryNames = {
  title: string; year: number | null;
  seasons?: { season: number; episodes: { n: number | null; title: string }[] }[];
}[];

export type MusicExtra = {
  type?: string | null;
  secondary_types?: string[];
  country?: string | null;
  date?: string | null;
  disambiguation?: string | null;
  life_span?: { begin?: string | null; end?: string | null; ended?: boolean } | null;
  musicbrainz_url?: string;
  wikipedia?: { url: string | null; title: string } | null;
  image_credit?: { author: string | null; license: string | null; url: string | null } | null;
};

/** A MusicBrainz search hit (Fix match): a release for albums, an artist for artists. */
export type MbResult = {
  mbid: string;
  title: string;
  artist?: string;
  date?: string | null;
  country?: string | null;
  track_count?: number | null;
  format?: string | null;
  type?: string | null;
  status?: string | null;
  disambiguation?: string | null;
  sort_name?: string;
  years?: string | null;
};

/** One playable track, as /api/items/{id}/tracks returns them (an artist's, an album's, or one track). */
export type QueueTrack = {
  id: number;
  title: string;
  artist: string;
  album: string;
  album_id: number;
  artist_id: number;
  album_artist: string;
  poster: string | null;
  track_number: number | null;
  disc_number: number | null;
  duration: number | null;
  file_id: number;
  /** CUE-sheet tracks: the stretch of the file this track is (seconds; end null = to the end of the file).
   *  null for ordinary one-track files. */
  start: number | null;
  end: number | null;
  available: boolean;
  playback: FileInfo["playback"];
};

/** A playlist imported from a .m3u/.m3u8/.pls file in a music library. */
export type PlaylistSummary = {
  id: number;
  library_id: number;
  name: string;
  /** the playlist file, relative to its library folder */
  path: string;
  track_count: number;
  duration: number | null;
  /** entries that matched nothing in the library (streams, files elsewhere) */
  missing: number;
  /** up to 4 album covers, in playlist order */
  covers: string[];
  updated_at: number;
};

export type Playlist = PlaylistSummary & { library_name: string; tracks: QueueTrack[] };

export type TmdbResult ={ tmdb_id: number; title: string; year: number | null; overview: string | null; poster_path: string | null };

// ---- other BAMS servers this browser is connected to (kept in the browser: servers.tsx)

/** One of the other server's libraries: `name` is what this account calls it (own_name = the server's own). */
export type RemoteLibrary = { id: number; type: "movie" | "show" | "music"; name: string; own_name: string; show: boolean };
export type RemoteServer = {
  id: number; name: string; url: string;
  /** the account signed in to there, and whether it's an admin there */
  account: string; is_admin: boolean;
  /** false: the other server no longer accepts the sign-in (sign in again) */
  signed_in: boolean;
  /** answered just now; when not, `libraries` are the ones it had last time */
  online: boolean; error: string | null;
  libraries: RemoteLibrary[];
};

// ---- Settings -> Security (server: security.py, netflow.py)

export type IpEntry = { cidr: string; note: string };
export type IpLists = { mode: "allow_all" | "allowlist"; allow: IpEntry[]; block: IpEntry[] };
export type NetflowStatus = {
  folder: string; default_folder: string; custom: boolean; max_bytes: number;
  bytes: number; files: number; oldest: number | null; dropped: number;
};
export type SecuritySettings = { lockout_threshold: number; ip: IpLists; your_ip: string; netflow: NetflowStatus };
export type AccountLock = {
  id: number; name: string; is_admin: boolean; last_login_at: number | null; failures: number;
  locked: boolean; locked_at: number | null; locked_by: string | null; wait_until: number | null;
};
export type AuthLogEntry = {
  id: number; at: number; event: "sign-in" | "lock" | "unlock" | "2fa"; result: "ok" | "failed" | "admin";
  name: string | null; user_id: number | null; ip: string | null; reason: string | null; user_agent: string | null;
};
export type FlowEntry = {
  time: number; duration_ms: number; client: string | null; client_port: number | null; server: string | null;
  scheme: string | null; http: string | null; method: string | null; path: string | null; query: string | null;
  status: number | null; bytes_in: number; bytes_out: number; user: string | null; user_agent: string | null;
  action: "allow" | "block";
};
