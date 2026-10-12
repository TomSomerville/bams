import { useEffect, useState } from "react";
import { ApiError, type SubtitleResult, type SubtitleSearch, type SubtitleTrack } from "../api";
import type { Call } from "../servers";
import { defaultLanguage, languageName, OS_LANGUAGES } from "../subtitleLangs";
import Icon from "./Icon";

const LANG_KEY = "bams.osLang";

function savedLanguage(): string | null {
  try { return localStorage.getItem(LANG_KEY); } catch { return null; }  // private mode
}

/** "Check OpenSubtitles": search for the playing file, pick one; it becomes one of the file's subtitle tracks.
 *  If it doesn't fit, open this again and pick another (ones already fetched are just switched to). */
export default function FindSubtitles({ fileId, call, subLang, tracks, current, onUse, onRemoved, onClose }: {
  fileId: number; call: Call; subLang: string | null; tracks: SubtitleTrack[]; current: string | null;
  onUse: (t: SubtitleTrack, note: string | null) => void; onRemoved: (id: string) => void; onClose: () => void;
}) {
  const [lang, setLang] = useState(() => defaultLanguage(savedLanguage(), subLang));
  const [res, setRes] = useState<SubtitleSearch | null>(null);
  const [busy, setBusy] = useState<number | "search" | null>("search");
  const [err, setErr] = useState<string | null>(null);
  const downloaded = tracks.filter((t) => t.source === "download");

  useEffect(() => {
    let gone = false;
    setBusy("search");
    setErr(null);
    try { localStorage.setItem(LANG_KEY, lang); } catch { /* not remembered */ }
    call.get<SubtitleSearch>(`/api/files/${fileId}/opensubtitles?languages=${encodeURIComponent(lang)}`)
      .then((r) => { if (!gone) setRes(r); })
      .catch((e) => { if (!gone) { setRes(null); setErr((e as Error).message); } })
      .finally(() => { if (!gone) setBusy(null); });
    return () => { gone = true; };
  }, [fileId, lang]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const use = async (r: SubtitleResult) => {
    const have = r.track && tracks.find((t) => t.id === r.track);
    if (have) return onUse(have, null);
    setBusy(r.file_id);
    setErr(null);
    try {
      const d = await call.post<{ track: SubtitleTrack; remaining: number | null; message: string | null;
        saved?: string | null; save_error?: string | null }>(
        `/api/files/${fileId}/opensubtitles`,
        { file_id: r.file_id, language: r.language, release: r.release, hearing_impaired: r.hearing_impaired });
      const left = d.remaining != null ? `${d.remaining} OpenSubtitles download${d.remaining === 1 ? "" : "s"} left today` : null;
      const copy = d.saved ? `Saved next to the video as ${d.saved}` : d.save_error ? `Not saved next to the video: ${d.save_error}` : null;
      onUse(d.track, [copy, left].filter(Boolean).join(" · ") || null);
    } catch (e) {
      setErr(e instanceof ApiError && e.status === 429
        ? `${e.message} Subtitles already downloaded still work.` : (e as Error).message);
      setBusy(null);
    }
  };

  const remove = async (t: SubtitleTrack) => {
    setErr(null);
    try {
      await call.del(`/api/files/${fileId}/subtitles/${t.id}`);
      onRemoved(t.id);
      setRes((r) => r && { ...r, results: r.results.map((x) => x.track === t.id ? { ...x, track: null } : x) });
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const what = res?.what;
  const about = what && (what.kind === "episode"
    ? `${what.show ?? ""} · S${String(what.season ?? 0).padStart(2, "0")}${what.episode != null ? `E${String(what.episode).padStart(2, "0")}` : ""}`
    : `${what.title ?? ""}${what.year ? ` (${what.year})` : ""}`);
  return (
    <div className="modal-backdrop find-subs" onMouseDown={(e) => e.target === e.currentTarget && onClose()}
      onClick={(e) => e.stopPropagation()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Check OpenSubtitles">
        <div className="modal-head">
          <h3>OpenSubtitles{about ? <span className="muted"> · {about}</span> : null}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="close" size={20} /></button>
        </div>
        <div className="picker-path">
          <select className="text-input" value={lang} onChange={(e) => setLang(e.target.value)} aria-label="Language">
            {OS_LANGUAGES.map((c) => <option key={c} value={c}>{languageName(c)}</option>)}
          </select>
          {res && busy !== "search" && (
            <span className="muted find-subs-by">{res.results.length ? `${res.results.length} found` : "None found"}
              {res.by === "ids" ? " for this title" : res.by === "name" ? " by its name" : ""}</span>
          )}
        </div>
        {err && <p className="key-msg bad">{err}</p>}
        {downloaded.length > 0 && (
          <div className="find-subs-have">
            <div className="muted">Already on this video</div>
            {downloaded.map((t) => (
              <div key={t.id} className="find-subs-row">
                <span className={t.id === current ? "on" : ""}>{t.label}</span>
                <button className="btn ghost small" onClick={() => onUse(t, null)} disabled={t.id === current}>
                  {t.id === current ? "In use" : "Use"}</button>
                <button className="btn ghost small danger" onClick={() => remove(t)}>Remove</button>
              </div>
            ))}
          </div>
        )}
        <ul className="picker-list match-list find-subs-list">
          {busy === "search" && <li className="muted picker-empty">Searching OpenSubtitles…</li>}
          {busy !== "search" && res?.results.map((r) => (
            <li key={r.file_id}>
              <button onClick={() => use(r)} disabled={busy !== null}>
                <span className="match-text">
                  <strong>{r.release || "(no release name)"}</strong>
                  {r.hash_match && <span className="tag">made for this file</span>}
                  {r.track && <span className="tag">{r.track === current ? "in use" : "on this video"}</span>}
                  <span className="muted match-overview">
                    {[languageName(r.language), r.hearing_impaired ? "for the hard of hearing" : null,
                      `${r.downloads.toLocaleString()} downloads`, r.trusted ? "trusted uploader" : null,
                      r.ai ? "AI-translated" : null, r.machine ? "machine-translated" : null,
                      r.fps ? `${r.fps} fps` : null].filter(Boolean).join(" · ")}
                  </span>
                </span>
                {busy === r.file_id && <span className="muted">Downloading…</span>}
              </button>
            </li>
          ))}
          {busy !== "search" && res && !res.results.length && (
            <li className="muted picker-empty">OpenSubtitles has nothing for this in {languageName(lang)}. Try another
              language.</li>
          )}
        </ul>
        <p className="fine-print find-subs-foot">Pick one to show it now; if it doesn't fit (timing, wrong cut), come
          back and try another, or move it with the subtitle timing buttons. Each new one counts against the server's
          OpenSubtitles downloads for the day{res && !res.account ? " (5 without an OpenSubtitles account in Settings)" : ""}.
          Subtitles from <a href="https://www.opensubtitles.com" target="_blank" rel="noreferrer">OpenSubtitles.com</a>.</p>
      </div>
    </div>
  );
}
