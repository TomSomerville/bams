// Your own playlists on the TV (server: user_playlists.py; private to your account, on each server), like the web's
// components/Playlists.tsx: over a screen, after holding OK on a song or pressing "Add to playlist" on an album or
// an artist. Names are typed with the TV's keyboard. Back closes a menu, as ListMenu's.

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { apiFor, type UserPlaylistSummary } from "./api";
import { setKeyHandler } from "./keys";
import { focus } from "./nav";
import { isBack } from "./tizen";

/** A menu over the screen: the focus starts on its first control; Back closes it. */
export function HoldMenu({ title, sub, onClose, children }: { title: string; sub?: string | null; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    setTimeout(() => focus(ref.current?.querySelector<HTMLElement>("[data-autofocus], button, input")));
    setKeyHandler((e) => {
      if (!isBack(e)) return false;
      close.current();
      return true;
    });
    return () => setKeyHandler(null);
  }, []);
  return (
    <div className="hold-menu" data-trap ref={ref}>
      <div className="hold-box">
        <h2>{title}</h2>
        {sub && <div className="hold-ep">{sub}</div>}
        {children}
      </div>
    </div>
  );
}

/** Name and description of a new playlist, or of one being edited. */
function PlaylistForm({ initial, busy, submit, onCancel }: {
  initial?: { name: string; description: string }; busy: boolean; onCancel: () => void;
  submit: (name: string, description: string) => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const go = (e?: FormEvent) => {
    e?.preventDefault();
    if (name.trim() && !busy) submit(name.trim(), description.trim());
  };
  return (
    <form className="playlist-form" onSubmit={go}>
      <input className="text-input" placeholder="Playlist name" value={name} maxLength={100} data-autofocus
        onChange={(e) => setName(e.target.value)} />
      <input className="text-input" placeholder="A few words about it (optional)" value={description} maxLength={500}
        onChange={(e) => setDescription(e.target.value)} />
      <div className="button-row">
        <button type="submit" className="btn primary" disabled={!name.trim() || busy}>
          {busy ? "Saving…" : initial ? "Save" : "Create playlist"}
        </button>
        <button type="button" className="btn" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

/** "New playlist": `created` gets the new one. */
export function NewPlaylistMenu({ rid, onClose, created }: { rid?: number; onClose: () => void; created: (p: UserPlaylistSummary) => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const submit = (name: string, description: string) => {
    setBusy(true);
    apiFor(rid).post<UserPlaylistSummary>("/api/user-playlists", { name, description }).then(created)
      .catch((e) => { setErr(e.message); setBusy(false); });
  };
  return (
    <HoldMenu title="New playlist" onClose={onClose}>
      <PlaylistForm busy={busy} submit={submit} onCancel={onClose} />
      {err && <p className="error">{err}</p>}
    </HoldMenu>
  );
}

/** Rename one of your playlists or change its description. */
export function EditPlaylistMenu({ playlist, rid, onClose, saved }: {
  playlist: UserPlaylistSummary; rid?: number; onClose: () => void; saved: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const submit = (name: string, description: string) => {
    setBusy(true);
    apiFor(rid).patch(`/api/user-playlists/${playlist.id}`, { name, description }).then(saved)
      .catch((e) => { setErr(e.message); setBusy(false); });
  };
  return (
    <HoldMenu title="Edit playlist" onClose={onClose}>
      <PlaylistForm initial={playlist} busy={busy} submit={submit} onCancel={onClose} />
      {err && <p className="error">{err}</p>}
    </HoldMenu>
  );
}

type Added = { added: number; skipped: number } & UserPlaylistSummary;

const songs = (n: number) => `${n} song${n === 1 ? "" : "s"}`;

/** Add a song, an album or an artist (`items`: their ids, on server `rid`) to one of your playlists, or a new one. */
export function AddToPlaylistMenu({ items, title, rid, onClose }: { items: number[]; title: string; rid?: number; onClose: () => void }) {
  const [lists, setLists] = useState<UserPlaylistSummary[] | null>(null);
  const [making, setMaking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<Added | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    apiFor(rid).get<UserPlaylistSummary[]>("/api/user-playlists").then((l) => { setLists(l); setMaking(!l.length); })
      .catch((e) => setErr(e.message));
  }, [rid]);
  // a new view in the same menu (the list, the form, the result): its first control gets the focus
  useEffect(() => {
    setTimeout(() => focus(box.current?.querySelector<HTMLElement>("[data-autofocus], button, input")));
  }, [lists, making, done]);

  const add = (p: UserPlaylistSummary) => {
    if (busy) return;
    setBusy(true);
    setErr(null);
    apiFor(rid).post<Added>(`/api/user-playlists/${p.id}/items`, { items }).then(setDone)
      .catch((e) => setErr(e.message)).finally(() => setBusy(false));
  };
  const create = (name: string, description: string) => {
    setBusy(true);
    setErr(null);
    apiFor(rid).post<UserPlaylistSummary>("/api/user-playlists", { name, description, items })
      .then((p) => setDone({ ...p, added: p.track_count, skipped: 0 }))
      .catch((e) => setErr(e.message)).finally(() => setBusy(false));
  };

  return (
    <HoldMenu title={done ? "Added" : "Add to a playlist"} sub={done ? null : title} onClose={onClose}>
      <div ref={box}>
        {done ? (
          <>
            <p>{done.added ? `${songs(done.added)} added to ${done.name}.` : `Nothing new: ${done.name} has ${done.skipped === 1 ? "it" : "them"} already.`}
              {done.added > 0 && done.skipped > 0 ? ` ${songs(done.skipped)} ${done.skipped === 1 ? "was" : "were"} in it already.` : ""}</p>
            <div className="button-row"><button className="btn primary" onClick={onClose}>OK</button></div>
          </>
        ) : making ? (
          <PlaylistForm busy={busy} submit={create} onCancel={lists?.length ? () => setMaking(false) : onClose} />
        ) : (
          <div className="pick-list">
            <button className="btn pick" onClick={() => setMaking(true)}>+ New playlist…</button>
            {lists?.map((p) => (
              <button key={p.id} className="btn pick" onClick={() => add(p)} disabled={busy}>
                {p.name} <small>{songs(p.track_count)}</small>
              </button>
            ))}
            {!lists && !err && <div className="spinner" />}
          </div>
        )}
        {err && <p className="error">{err}</p>}
      </div>
    </HoldMenu>
  );
}

/** Holding OK on a song in one of your playlists: move it up or down, take it out. */
export function PlaylistTrackMenu({ title, first, last, onMove, onRemove, onClose }: {
  title: string; first: boolean; last: boolean; onMove: (by: -1 | 1) => void; onRemove: () => void; onClose: () => void;
}) {
  return (
    <HoldMenu title={title} onClose={onClose}>
      <div className="button-row">
        {!first && <button className="btn" onClick={() => onMove(-1)}>Move up</button>}
        {!last && <button className="btn" onClick={() => onMove(1)}>Move down</button>}
        <button className="btn" onClick={onRemove}>Take out of the playlist</button>
        <button className="btn" onClick={onClose}>Cancel</button>
      </div>
    </HoldMenu>
  );
}
