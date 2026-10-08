import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type ItemDetail, type MbResult } from "../api";
import Icon from "./Icon";

/** Search MusicBrainz and pin an album (to a release) or an artist. */
export default function MusicFixMatch({ item, onClose }: { item: ItemDetail; onClose: (changed: boolean) => void }) {
  const isAlbum = item.kind === "album";
  const [q, setQ] = useState(item.parsed_title || item.title);
  const [artist, setArtist] = useState(isAlbum ? item.ancestors[0]?.title ?? "" : "");
  const [results, setResults] = useState<MbResult[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const navigate = useNavigate();

  const search = async () => {
    setBusy("search");
    setErr(null);
    try {
      const params = new URLSearchParams({ kind: isAlbum ? "album" : "artist", q });
      if (isAlbum && artist.trim()) params.set("artist", artist.trim());
      setResults(await api.get<MbResult[]>(`/api/musicbrainz/search?${params}`));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const pick = async (r: MbResult) => {
    setBusy(r.mbid);
    setErr(null);
    try {
      const d = await api.post<ItemDetail>(`/api/items/${item.id}/music-match`, { mbid: r.mbid });
      onClose(true);
      // merged into another copy of the same release: that album is this one now
      if (d.id !== item.id) navigate(`/title/${d.id}`, { replace: true });
    } catch (e) {
      setErr((e as Error).message);
      setBusy(null);
    }
  };

  useEffect(() => {
    search();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const details = (r: MbResult) => isAlbum
    ? [r.artist, r.date?.slice(0, 4), r.type, r.track_count ? `${r.track_count} tracks` : null, r.format, r.country]
    : [r.type, r.country, r.years, r.disambiguation];

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose(false)}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Fix match">
        <div className="modal-head">
          <h3>Fix match: {isAlbum ? "album" : "artist"}</h3>
          <button className="icon-btn" onClick={() => onClose(false)} aria-label="Close"><Icon name="close" size={20} /></button>
        </div>
        <form className="picker-path" onSubmit={(e) => { e.preventDefault(); search(); }}>
          <input value={q} onChange={(e) => setQ(e.target.value)} aria-label={isAlbum ? "Album title" : "Artist name"}
            placeholder={isAlbum ? "Album title" : "Artist name"} />
          {isAlbum && <input value={artist} onChange={(e) => setArtist(e.target.value)} aria-label="Artist" placeholder="Artist" />}
          <button className="btn ghost small" disabled={!q.trim() || busy !== null}>Search</button>
        </form>
        {err && <p className="key-msg bad">{err}</p>}
        <ul className="picker-list match-list">
          {busy === "search" && <li className="muted picker-empty">Searching MusicBrainz…</li>}
          {results?.map((r) => (
            <li key={r.mbid}>
              <button onClick={() => pick(r)} disabled={busy !== null}>
                <span className="match-text">
                  <strong>{r.title}</strong>
                  {item.ids.musicbrainz === r.mbid && <span className="tag">current</span>}
                  <span className="muted">{details(r).filter(Boolean).join(" · ")}</span>
                  {isAlbum && r.disambiguation && <span className="muted match-overview">{r.disambiguation}</span>}
                </span>
                {busy === r.mbid && <span className="muted">Matching…</span>}
              </button>
            </li>
          ))}
          {results && !results.length && (
            <li className="muted picker-empty">
              Nothing on MusicBrainz. Try another spelling{isAlbum ? ", or clear the artist" : ""}. Anyone can add
              missing music at musicbrainz.org.
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}
