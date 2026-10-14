import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { UserPlaylistSummary } from "../api";
import { plural } from "../format";
import { useScope } from "../servers";
import Icon from "./Icon";

// Your own playlists (server: user_playlists.py; private to your account, on each server): the dialogs to make
// one, rename it, and add songs, albums or artists to one. They talk to the page's server (useScope), so another
// BAMS server's music goes into that server's playlists.

/** Name and description of a new playlist, or of one being edited. */
export function PlaylistForm({ initial, busy, submit, children }: {
  initial?: { name: string; description: string }; busy: boolean; children?: ReactNode;
  submit: (name: string, description: string) => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const go = (e: FormEvent) => {
    e.preventDefault();
    if (name.trim()) submit(name.trim(), description.trim());
  };
  return (
    <form className="playlist-form" onSubmit={go}>
      <input className="text-input" placeholder="Playlist name" value={name} maxLength={100} autoFocus
        onChange={(e) => setName(e.target.value)} aria-label="Playlist name" />
      <textarea className="text-input" placeholder="A few words about it (optional)" value={description} maxLength={500}
        rows={2} onChange={(e) => setDescription(e.target.value)} aria-label="Description" />
      <div className="playlist-form-foot">
        {children}
        <button className="btn small primary" disabled={!name.trim() || busy}>{initial ? "Save" : "Create playlist"}</button>
      </div>
    </form>
  );
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal playlist-modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="close" size={20} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

/** "New playlist": make an empty one (or one holding `items`), then open it (`created`). */
export function NewPlaylistDialog({ items = [], onClose, created }: {
  items?: number[]; onClose: () => void; created: (p: UserPlaylistSummary) => void;
}) {
  const { call } = useScope();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const submit = (name: string, description: string) => {
    setBusy(true);
    setErr(null);
    call.post<UserPlaylistSummary>("/api/user-playlists", { name, description, items })
      .then(created).catch((e) => { setErr(e.message); setBusy(false); });
  };
  return (
    <Modal title="New playlist" onClose={onClose}>
      <PlaylistForm busy={busy} submit={submit} />
      {err && <p className="key-msg bad">{err}</p>}
    </Modal>
  );
}

/** Rename a playlist or change its description. */
export function EditPlaylistDialog({ playlist, onClose, saved }: {
  playlist: UserPlaylistSummary; onClose: () => void; saved: () => void;
}) {
  const { call } = useScope();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const submit = (name: string, description: string) => {
    setBusy(true);
    call.patch(`/api/user-playlists/${playlist.id}`, { name, description })
      .then(saved).catch((e) => { setErr(e.message); setBusy(false); });
  };
  return (
    <Modal title="Edit playlist" onClose={onClose}>
      <PlaylistForm initial={playlist} busy={busy} submit={submit} />
      {err && <p className="key-msg bad">{err}</p>}
    </Modal>
  );
}

type Added = { added: number; skipped: number } & UserPlaylistSummary;

/** Add a song, an album or an artist (`items`: their ids) to one of your playlists, or to a new one. */
export function AddToPlaylistDialog({ items, title, onClose }: { items: number[]; title: string; onClose: () => void }) {
  const { call, to } = useScope();
  const [lists, setLists] = useState<UserPlaylistSummary[] | null>(null);
  const [making, setMaking] = useState(false);
  const [busy, setBusy] = useState<number | "new" | null>(null);
  const [done, setDone] = useState<Added | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    call.get<UserPlaylistSummary[]>("/api/user-playlists").then((l) => { setLists(l); setMaking(!l.length); })
      .catch((e) => setErr(e.message));
  }, [call]);

  const add = (p: UserPlaylistSummary) => {
    setBusy(p.id);
    setErr(null);
    call.post<Added>(`/api/user-playlists/${p.id}/items`, { items }).then(setDone)
      .catch((e) => setErr(e.message)).finally(() => setBusy(null));
  };
  const create = (name: string, description: string) => {
    setBusy("new");
    setErr(null);
    call.post<UserPlaylistSummary>("/api/user-playlists", { name, description, items })
      .then((p) => setDone({ ...p, added: p.track_count, skipped: 0 }))
      .catch((e) => setErr(e.message)).finally(() => setBusy(null));
  };

  if (done) {
    return (
      <Modal title="Added" onClose={onClose}>
        <p className="playlist-done">
          {done.added ? <>{plural(done.added, "song")} added to <strong>{done.name}</strong>.</>
            : <>Nothing new: <strong>{done.name}</strong> has {done.skipped === 1 ? "it" : "them"} already.</>}
          {done.added > 0 && done.skipped > 0 && <> {plural(done.skipped, "song")} {done.skipped === 1 ? "was" : "were"} in it already.</>}
        </p>
        <div className="modal-foot">
          <Link className="btn small ghost" to={to(`/my-playlist/${done.id}`)} onClick={onClose}>Open playlist</Link>
          <button className="btn small primary" onClick={onClose}>Done</button>
        </div>
      </Modal>
    );
  }
  return (
    <Modal title={`Add “${title}” to a playlist`} onClose={onClose}>
      {making ? (
        <PlaylistForm busy={busy === "new"} submit={create}>
          {!!lists?.length && <button type="button" className="btn small ghost" onClick={() => setMaking(false)}>Back</button>}
        </PlaylistForm>
      ) : (
        <ul className="picker-list">
          <li><button onClick={() => setMaking(true)}><Icon name="plus" size={18} /> <strong>New playlist…</strong></button></li>
          {lists?.map((p) => (
            <li key={p.id}>
              <button onClick={() => add(p)} disabled={busy !== null}>
                <Icon name="list" size={18} />
                <span className="match-text"><strong>{p.name}</strong><span className="muted">{plural(p.track_count, "song")}</span></span>
                {busy === p.id && <span className="muted">Adding…</span>}
              </button>
            </li>
          ))}
          {!lists && !err && <li className="muted picker-empty">Loading your playlists…</li>}
        </ul>
      )}
      {err && <p className="key-msg bad">{err}</p>}
    </Modal>
  );
}

/** The "Add to playlist" button: a ghost button (album/artist pages) or a small icon (song rows). */
export function AddToPlaylist({ items, title, small }: { items: number[]; title: string; small?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      {small ? (
        <button className="icon-btn subtle add-to-playlist" onClick={(e) => { e.stopPropagation(); setOpen(true); }}
          title="Add to playlist" aria-label={`Add ${title} to a playlist`}><Icon name="listPlus" size={16} /></button>
      ) : (
        <button className="btn ghost" onClick={() => setOpen(true)}><Icon name="listPlus" /> Add to playlist</button>
      )}
      {open && <AddToPlaylistDialog items={items} title={title} onClose={() => setOpen(false)} />}
    </>
  );
}
