// The Android app's Downloads pages: what's on the phone, from the app's catalog (Store.kt `library`). Each download
// carries its server's manifest (GET /api/items/{id}/download): the items as the API shows them, music's queue, the
// files. Here they're merged per server into one library, with pictures served by the app (/dl/<server>/images/…).

import type { ItemDetail, ItemSummary, PlaylistSummary, QueueTrack, UserPlaylistSummary } from "../api";
import type { DownloadState } from "../android";

type ManifestFile = { id: number; name: string; size: number; items: number[]; audio: string[] };
type Manifest = {
  root: { kind: string; id: number; title: string };
  items: ItemDetail[];
  tracks: QueueTrack[];
  files: ManifestFile[];
  playlist?: PlaylistSummary | UserPlaylistSummary;
};
export type RootRow = {
  key: string; sid: string; kind: RootKind; id: number; title: string; added: number;
  status: DownloadState; manifest: Manifest | null;
};
type FileRow = { state: "queued" | "downloading" | "done" | "failed" | "missing"; size: number; got: number; audio: string[] };
type Saved = { position: number; duration: number | null; at: number };
export type Raw = {
  roots: RootRow[];
  files: Record<string, FileRow>;
  servers: { id: string; name: string; shown: boolean }[];
  used: number;
  progress: Record<string, Record<string, Saved>>;
};

/** what a download is: a title/season/show/song/album/artist, an imported playlist, or one of your own */
export type RootKind = "item" | "playlist" | "user_playlist";

export type Item = ItemDetail & { sid: string };
export type Track = QueueTrack & { sid: string };
/** A downloaded playlist: an imported one, or one of yours (`own`, with its description). `ref` is its page's
 *  part of the address: "playlist:3" or "user_playlist:3". */
export type Playlist = {
  sid: string; ref: string; own: boolean; id: number; name: string; description: string; covers: string[];
  duration: number | null; tracks: Track[];
};

export type Library = {
  servers: Map<string, string>;  // id -> name
  items: Map<string, Item>;      // "<sid>:<id>" -> the item
  tracks: Map<string, Track>;
  playlists: Playlist[];
  roots: RootRow[];
  /** "<sid>:<item id>" -> its file's state (movies, episodes, tracks) */
  fileOf: Map<string, FileRow & { key: string }>;
  used: number;
};

export const ik = (sid: string, id: number) => `${sid}:${id}`;

/** A server's picture link as the app serves it from the phone. */
export function img(sid: string, url: string | null | undefined): string | null {
  return url && url.startsWith("/api/images/") ? `/dl/${sid}/images/${url.slice("/api/images/".length)}` : url ?? null;
}

function pictures<T extends ItemSummary>(sid: string, i: T): T {
  return { ...i, poster: img(sid, i.poster), backdrop: img(sid, i.backdrop), still: img(sid, i.still ?? null) };
}

export function build(raw: Raw): Library {
  const items = new Map<string, Item>();
  const tracks = new Map<string, Track>();
  const fileOf = new Map<string, FileRow & { key: string }>();
  const playlists: Playlist[] = [];
  // oldest first: a later download's copy of an item (newer metadata) wins
  for (const r of [...raw.roots].sort((a, b) => a.added - b.added)) {
    const m = r.manifest;
    if (!m) continue;
    for (const d of m.items) {
      const k = ik(r.sid, d.id);
      const prev = items.get(k);
      items.set(k, {
        ...pictures(r.sid, d), sid: r.sid,
        ancestors: d.ancestors.map((a) => pictures(r.sid, a)),
        children: d.children.map((c) => pictures(r.sid, c)),
        // a show downloaded twice (one season, then another) has every child either copy knew
        ...(prev ? { children: mergeChildren(prev.children, d.children.map((c) => pictures(r.sid, c))) } : {}),
      });
    }
    for (const t of m.tracks) tracks.set(ik(r.sid, t.id), { ...t, poster: img(r.sid, t.poster), sid: r.sid });
    for (const f of m.files) {
      const row = raw.files[`${r.sid}|${f.id}`];
      if (row) for (const i of f.items) fileOf.set(ik(r.sid, i), { ...row, key: `${r.sid}|${f.id}` });
    }
    if (r.kind !== "item" && m.playlist) {
      const pl = m.playlist;
      playlists.push({
        sid: r.sid, ref: `${r.kind}:${r.id}`, own: r.kind === "user_playlist", id: pl.id, name: pl.name,
        description: "description" in pl ? pl.description : "", duration: pl.duration,
        covers: pl.covers.map((c) => img(r.sid, c)!),
        tracks: m.tracks.map((t) => ({ ...t, poster: img(r.sid, t.poster), sid: r.sid })),
      });
    }
  }
  // what was watched on the phone since: newer than what the server said when it was downloaded
  for (const [sid, byItem] of Object.entries(raw.progress)) {
    for (const [id, p] of Object.entries(byItem)) {
      const it = items.get(ik(sid, Number(id)));
      if (!it) continue;
      const dur = p.duration ?? it.progress?.duration ?? null;
      it.progress = { position: p.position, duration: dur, watched: !!dur && p.position >= dur * 0.9 };
    }
  }
  return {
    servers: new Map(raw.servers.map((s) => [s.id, s.name])),
    items, tracks, playlists, roots: raw.roots, fileOf, used: raw.used,
  };
}

function mergeChildren(a: ItemSummary[], b: ItemSummary[]): ItemSummary[] {
  const seen = new Map(a.map((c) => [c.id, c]));
  for (const c of b) seen.set(c.id, c);
  return [...seen.values()];
}

/** On the phone and playable (its file is all here). */
export const here = (lib: Library, sid: string, id: number) => lib.fileOf.get(ik(sid, id))?.state === "done";

/** Movies / shows / artists / albums that have something on the phone (or on its way). */
export function shelves(lib: Library) {
  const movies: Item[] = [], shows = new Map<string, Item>(), artists = new Map<string, Item>(), albums = new Map<string, Item>();
  for (const it of lib.items.values()) {
    if (!lib.fileOf.has(ik(it.sid, it.id))) continue;
    if (it.kind === "movie") movies.push(it);
    if (it.kind === "episode") {
      const show = it.ancestors.find((a) => a.kind === "show");
      const s = show && lib.items.get(ik(it.sid, show.id));
      if (s) shows.set(ik(s.sid, s.id), s);
    }
  }
  for (const t of lib.tracks.values()) {
    if (!lib.fileOf.has(ik(t.sid, t.id))) continue;
    const al = lib.items.get(ik(t.sid, t.album_id));
    const ar = lib.items.get(ik(t.sid, t.artist_id));
    if (al) albums.set(ik(al.sid, al.id), al);
    if (ar) artists.set(ik(ar.sid, ar.id), ar);
  }
  const byTitle = (a: Item, b: Item) => a.title.localeCompare(b.title);
  return {
    movies: movies.sort(byTitle), shows: [...shows.values()].sort(byTitle),
    artists: [...artists.values()].sort(byTitle), albums: [...albums.values()].sort(byTitle),
  };
}

/** A show's downloaded episodes, by season then number. */
export function episodesOf(lib: Library, show: Item): Item[] {
  return [...lib.items.values()]
    .filter((e) => e.sid === show.sid && e.kind === "episode" && e.ancestors.some((a) => a.id === show.id) && lib.fileOf.has(ik(e.sid, e.id)))
    .sort((a, b) => (a.season_number ?? 0) - (b.season_number ?? 0) || (a.episode_number ?? 0) - (b.episode_number ?? 0));
}

/** Downloaded tracks of an album or an artist, in play order. */
export function tracksOf(lib: Library, it: Item): Track[] {
  const order = (t: Track) => [lib.items.get(ik(t.sid, t.album_id))?.year ?? 0, t.album, t.disc_number ?? 1, t.track_number ?? 0] as const;
  return [...lib.tracks.values()]
    .filter((t) => t.sid === it.sid && (t.album_id === it.id || t.artist_id === it.id) && lib.fileOf.has(ik(t.sid, t.id)))
    .sort((a, b) => {
      const x = order(a), y = order(b);
      return x[0] - y[0] || String(x[1]).localeCompare(String(y[1])) || x[2] - y[2] || x[3] - y[3];
    });
}

/** The download that is this item (it can be removed from here), if any. */
export const rootOf = (lib: Library, sid: string, kind: RootKind, id: number) =>
  lib.roots.find((r) => r.sid === sid && r.kind === kind && r.id === id) ?? null;
