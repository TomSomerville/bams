import { useCallback, useEffect, useRef, useState } from "react";
import { api, type BrowseResult } from "../api";
import Icon from "./Icon";

/** Browse folders on the BAMS server (not this browser's computer) and pick one. */
export default function FolderPicker({ onPick, onClose }: { onPick: (path: string) => void; onClose: () => void }) {
  const [res, setRes] = useState<BrowseResult | null>(null);
  const [typed, setTyped] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const dialog = useRef<HTMLDivElement>(null);

  const go = useCallback(async (path: string | null) => {
    setLoading(true);
    setErr(null);
    try {
      const r = await api.get<BrowseResult>(`/api/fs/browse${path ? `?path=${encodeURIComponent(path)}` : ""}`);
      setRes(r);
      setTyped(r.path ?? "");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    go(null);
    dialog.current?.focus();
  }, [go]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Choose a folder" tabIndex={-1} ref={dialog}>
        <div className="modal-head">
          <h3>Choose a folder on the server</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="close" size={20} /></button>
        </div>
        <form className="picker-path" onSubmit={(e) => { e.preventDefault(); if (typed.trim()) go(typed.trim()); }}>
          <button type="button" className="btn ghost small" onClick={() => go(res?.parent ?? null)}
            disabled={loading || !res?.path} title="Up one level">
            <Icon name="chevronLeft" size={16} /> Up
          </button>
          <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Type or paste a path, e.g. D:\Media, \\NAS\Videos or /mnt/media"
            aria-label="Folder path" spellCheck={false} />
          <button type="submit" className="btn ghost small" disabled={!typed.trim() || loading}>Go</button>
        </form>
        {err && <p className="key-msg bad">{err}</p>}
        <ul className="picker-list">
          {res?.dirs.map((d) => (
            <li key={d.path}>
              <button onClick={() => go(d.path)}><Icon name="folder" size={18} /> {d.name}</button>
            </li>
          ))}
          {res && !res.dirs.length && <li className="muted picker-empty">No subfolders here.</li>}
        </ul>
        <div className="modal-foot">
          <span className="muted picker-current">{res?.path ?? "Pick a drive or folder"}</span>
          <button className="btn ghost small" onClick={onClose}>Cancel</button>
          <button className="btn primary small" disabled={!res?.path} onClick={() => res?.path && onPick(res.path)}>
            Use this folder
          </button>
        </div>
      </div>
    </div>
  );
}
