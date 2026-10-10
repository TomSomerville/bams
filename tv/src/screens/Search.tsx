import { useEffect, useRef, useState } from "react";
import { api, type ItemSummary } from "../api";
import { useFocusOnReady, useNav } from "../App";
import { Poster } from "../Cards";

/** Search shows and movies by title (the TV's on-screen keyboard opens on OK). */
export default function Search() {
  const nav = useNav();
  const [q, setQ] = useState(() => sessionStorage.getItem("bams.q") || "");
  const [hits, setHits] = useState<ItemSummary[] | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    sessionStorage.setItem("bams.q", q);
    clearTimeout(timer.current);
    if (!q.trim()) return setHits(null);
    timer.current = setTimeout(() => {
      api.get<ItemSummary[]>(`/api/items?kind=show,movie&sort=title&limit=120&q=${encodeURIComponent(q.trim())}`)
        .then(setHits).catch(() => setHits([]));
    }, 350);
  }, [q]);

  useFocusOnReady(true);

  return (
    <div className="page">
      <div className="page-head"><h1>Search</h1></div>
      <input className="text-input wide-input" data-fid="q" data-autofocus placeholder="Title…" value={q}
        onChange={(e) => setQ(e.target.value)} />
      {hits && !hits.length && <p className="muted big">Nothing called “{q}”.</p>}
      <div className="grid">
        {hits?.map((it) => (
          <Poster key={it.id} item={it} fid={`hit-${it.id}`} onPress={() => nav.push({ name: "detail", id: it.id })} />
        ))}
      </div>
    </div>
  );
}
