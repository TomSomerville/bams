import { useEffect, useRef, useState } from "react";
import { listName } from "../../web/src/homeRows";
import { apiFor } from "./api";
import { useNav } from "./App";
import { setKeyHandler } from "./keys";
import { focus } from "./nav";
import { isBack } from "./tizen";

/** What the signed-in person calls their watch list (prefs.watchlist_name on the TV's first server, like Home's rows). */
export function useListName(): string {
  return listName(useNav().user?.prefs?.watchlist_name);
}

/** Puts an item on the watch list or takes it off, on the item's own server (`rid`). */
export async function setListed(id: number, rid: number | undefined, on: boolean): Promise<void> {
  const api = apiFor(rid);
  await (on ? api.put(`/api/watchlist/${id}`, {}) : api.del(`/api/watchlist/${id}`));
}

/** Over a screen after holding OK on something that can go on the watch list (an episode, a watch list entry): put
 *  it on or take it off, or not. Back closes it too. `onDone(on)` once the server has done it. */
export function ListMenu({ id, rid, on, title, sub, onClose, onDone }: {
  id: number; rid?: number; on: boolean; title: string; sub?: string | null; onClose: () => void; onDone: (on: boolean) => void;
}) {
  const name = useListName();
  const ref = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    setTimeout(() => focus(ref.current?.querySelector("button")));
    setKeyHandler((e) => {
      if (!isBack(e)) return false;
      close.current();
      return true;
    });
    return () => setKeyHandler(null);
  }, []);
  const go = async () => {
    if (busy) return;
    setBusy(true);
    setErr(null);
    try {
      await setListed(id, rid, !on);
      onDone(!on);
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  };
  return (
    <div className="hold-menu" data-trap ref={ref}>
      <div className="hold-box">
        <h2>{title}</h2>
        {sub && <div className="hold-ep">{sub}</div>}
        {err && <p className="error">{err}</p>}
        <div className="button-row">
          <button className="btn primary" onClick={() => void go()}>
            {busy ? "Saving…" : on ? `Remove from ${name}` : `Add to ${name}`}
          </button>
          <button className="btn" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}
