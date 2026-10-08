import { useRef, useState, type KeyboardEvent, type MouseEvent, type PointerEvent } from "react";

/** Drag-to-reorder for a list (the music queue, the sidebar's libraries): drag a row by its handle (mouse or
 *  touch), or focus the handle and use the arrow keys. `listRef`'s children must be the rows, in order.
 *
 *  While dragging, the rows stay put (moving the DOM node would lose the pointer capture); `rowClass` marks the
 *  lifted row and draws a line where it will land: before the other row now at its new place, or after the last. */
export function useReorder<T extends HTMLElement>(count: number, onMove: (from: number, to: number) => void,
  scroller?: string) {
  const listRef = useRef<T>(null);
  const [drag, setDrag] = useState<{ from: number; to: number } | null>(null);

  const others = drag ? Array.from({ length: count }, (_, i) => i).filter((i) => i !== drag.from) : [];
  const moved = drag && drag.to !== drag.from;
  const dropBefore = moved && drag.to < others.length ? others[drag.to] : null;
  const dropAfter = moved && drag.to >= others.length ? others[others.length - 1] : null;

  const handle = (i: number) => ({
    onPointerDown: (e: PointerEvent<HTMLElement>) => {
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      e.currentTarget.setPointerCapture(e.pointerId);
      setDrag({ from: i, to: i });
    },
    onPointerMove: (e: PointerEvent<HTMLElement>) => {
      const list = listRef.current;
      if (!drag || !list) return;
      // the new place: how many of the other rows are above the pointer
      const rows = [...list.children].filter((_, k) => k !== drag.from);
      const to = rows.filter((r) => { const b = r.getBoundingClientRect(); return b.top + b.height / 2 < e.clientY; }).length;
      if (to !== drag.to) setDrag({ ...drag, to });
      const box = scroller ? list.closest(scroller) : null; // scroll a panel near its edges
      if (box) {
        const r = box.getBoundingClientRect();
        if (e.clientY < r.top + 40) box.scrollTop -= 12;
        if (e.clientY > r.bottom - 40) box.scrollTop += 12;
      }
    },
    onPointerUp: () => {
      if (drag && drag.to !== drag.from) onMove(drag.from, drag.to);
      setDrag(null);
    },
    onPointerCancel: () => setDrag(null),
    onClick: (e: MouseEvent<HTMLElement>) => { e.preventDefault(); e.stopPropagation(); }, // a handle, not a link
    onKeyDown: (e: KeyboardEvent<HTMLElement>) => {
      if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
      e.preventDefault();
      const to = i + (e.key === "ArrowUp" ? -1 : 1);
      if (to >= 0 && to < count) onMove(i, to);
    },
    title: "Drag to reorder (or arrow keys)",
  });

  const rowClass = (i: number) =>
    [drag?.from === i && "lifted", dropBefore === i && "drop-before", dropAfter === i && "drop-after"].filter(Boolean).join(" ");

  return { listRef, dragging: !!drag, handle, rowClass };
}
