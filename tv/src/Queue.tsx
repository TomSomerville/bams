// "Up next" on the TV: the music queue (NowPlaying) or Play Random's video queue (the player), over the screen.
// A remote can't drag, so each row has ▲ / ▼ (move it up or down) and × (take it out) beside it; OK on the row plays
// it. The one playing can't be taken out. Back closes the panel.

import { useEffect, useRef } from "react";
import Icon from "./Icon";
import { setKeyHandler } from "./keys";
import { focus } from "./nav";
import { isBack } from "./tizen";

export type QueueRow = { key: string; title: string; sub: string };

export function QueuePanel({ rows, at, onJump, onMove, onRemove, onClose }: {
  rows: QueueRow[]; at: number; onJump: (i: number) => void; onMove: (from: number, to: number) => void;
  onRemove: (i: number) => void; onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    setTimeout(() => focus(ref.current?.querySelector<HTMLElement>(`[data-fid="q-row-${at}"]`) ?? ref.current?.querySelector("button")));
    setKeyHandler((e) => {
      if (!isBack(e)) return false;
      close.current();
      return true;
    });
    return () => setKeyHandler(null);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // after a move or removal the focus follows the row (by its button's place), so ▲▲▲ keeps moving the same entry
  const moveTo = (from: number, to: number, which: "up" | "down") => {
    onMove(from, to);
    setTimeout(() => focus(ref.current?.querySelector<HTMLElement>(`[data-fid="q-${which}-${to}"]`)
      ?? ref.current?.querySelector<HTMLElement>(`[data-fid="q-row-${to}"]`)));
  };
  const remove = (i: number) => {
    onRemove(i);
    setTimeout(() => focus(ref.current?.querySelector<HTMLElement>(`[data-fid="q-del-${i}"]`)
      ?? ref.current?.querySelector<HTMLElement>(`[data-fid="q-row-${Math.max(0, i - 1)}"]`)));
  };

  return (
    <div className="hold-menu queue-menu" data-trap ref={ref}>
      <div className="hold-box queue-box">
        <h2>Up next</h2>
        <div className="queue-list">
          {rows.map((r, i) => (
            <div key={r.key} className={`queue-row ${i === at ? "on" : ""}`}>
              <button className="queue-item" data-fid={`q-row-${i}`} onClick={() => onJump(i)}>
                <span className="queue-title">{i === at && <Icon name="play" size={24} />} {r.title}</span>
                <span className="queue-sub">{r.sub}</span>
              </button>
              <button className="round small" data-fid={`q-up-${i}`} disabled={i === 0} aria-label="Move up"
                onClick={() => moveTo(i, i - 1, "up")}><Icon name="up" size={28} /></button>
              <button className="round small" data-fid={`q-down-${i}`} disabled={i === rows.length - 1} aria-label="Move down"
                onClick={() => moveTo(i, i + 1, "down")}><Icon name="down" size={28} /></button>
              <button className="round small" data-fid={`q-del-${i}`} disabled={i === at} aria-label="Remove"
                onClick={() => remove(i)}><Icon name="close" size={28} /></button>
            </div>
          ))}
        </div>
        <p className="muted">OK on a row plays it · ▲ ▼ move it · ✕ takes it out · Back closes</p>
      </div>
    </div>
  );
}
