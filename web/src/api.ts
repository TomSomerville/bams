// Thin client for the BAMS server API (server/bams/app.py). Same origin in production;
// the Vite dev server proxies /api to 127.0.0.1:8484.

export class ApiError extends Error {
  constructor(public status: number, message: string) {
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
  if (!r.ok) {
    const d = data?.detail;
    const msg = typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x.msg).join("; ") : `HTTP ${r.status}`;
    throw new ApiError(r.status, msg);
  }
  return data as T;
}

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
  files: { total: number; available: number; bytes: number; unrecognized: number };
};

export type ScanState = {
  running: { library_id: number; trigger: string; started_at: number; step: string } | null;
  queued: { library_id: number; trigger: string }[];
};

export type ServerStatus = {
  version: string;
  data_dir: string;
  ffprobe: string | null;
  ffmpeg: string | null;
  /** the H.264 encoder video transcodes use (null: none works, or no FFmpeg) */
  video_encoder: { id: string; name: string; hardware: boolean; hw_decode: boolean } | null;
  /** video conversions running now (HLS sessions + plain streams) and how many are allowed */
  transcodes: { running: number; limit: number };
  tmdb_configured: boolean;
  scans: ScanState;
};

export type BrowseResult = { path: string | null; parent: string | null; dirs: { name: string; path: string }[] };

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
};

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
    video_codec: string | null;
    audio_codec: string | null;
    audio_ok: boolean;
    duration: number | null;
  };
  stream_url: string;
  download_url: string;
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
};

export type UnrecognizedFile = FileInfo & { hint: string };

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
  available: boolean;
  playback: FileInfo["playback"];
  download_url: string;
};

export type TmdbResult ={ tmdb_id: number; title: string; year: number | null; overview: string | null; poster_path: string | null };
