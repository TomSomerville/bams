import { useEffect, useState } from "react";
import type { HolidayTag } from "../api";
import { useScope } from "../servers";
import Icon from "./Icon";

/** Admins: which holidays a movie or episode belongs to (Upcoming / Recent Holiday rows and filters). Each holiday is
 *  automatic (by the title's words and TMDB keywords), or set by hand: always in, or never. */
export default function HolidayTags({ itemId, title, onClose }: { itemId: number; title: string; onClose: () => void }) {
  const { call } = useScope();
  const [tags, setTags] = useState<HolidayTag[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    call.get<HolidayTag[]>(`/api/items/${itemId}/holidays`).then(setTags).catch((e) => setErr((e as Error).message));
  }, [call, itemId]);

  const set = async (h: HolidayTag, tagged: boolean | null) => {
    setErr(null);
    try {
      setTags(await call.put<HolidayTag[]>(`/api/items/${itemId}/holidays/${h.id}`, { tagged }));
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Holidays">
        <div className="modal-head">
          <h3>Holidays · {title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="close" size={20} /></button>
        </div>
        <p className="muted">BAMS puts a title in a holiday when its title or description mentions it (or, for movies,
          TMDB's keywords do). Set it by hand when it's wrong.</p>
        {err && <p className="key-msg bad">{err}</p>}
        {!tags && !err && <p className="muted">Loading…</p>}
        <ul className="holiday-tags">
          {tags?.map((h) => (
            <li key={h.id} className={h.on ? "on" : ""}>
              <span className="holiday-name">{h.name}</span>
              <span className="muted holiday-state">{h.tagged === null ? (h.on ? "in (automatic)" : "") : h.on ? "in (by hand)" : "out (by hand)"}</span>
              <span className="segmented small">
                <button className={h.tagged === null ? "on" : ""} onClick={() => void set(h, null)}>Auto</button>
                <button className={h.tagged === true ? "on" : ""} onClick={() => void set(h, true)}>In</button>
                <button className={h.tagged === false ? "on" : ""} onClick={() => void set(h, false)}>Out</button>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
