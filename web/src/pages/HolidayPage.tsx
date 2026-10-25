import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import type { Holidays, ShownItem } from "../api";
import { ListedCard } from "../components/Cards";
import Icon from "../components/Icon";
import { useVideoQueue } from "../random";
import { holidayOrder, holidayPath, holidayTitle, keyOf } from "../everywhere";
import { useEverywhere, useSources } from "../servers";
import { useApi } from "../useApi";

// "See all" of a Home holiday row (/holiday/next, /holiday/recent): every movie and episode about that holiday, from
// every server this browser shows, by title (an episode under its show). Which holiday it is comes from this server.

const KINDS = { all: "All", movie: "Movies", episode: "Episodes" } as const;
type Kind = keyof typeof KINDS;

export default function HolidayPage() {
  const which = useParams().which === "recent" ? "recent" : "next";
  const { data: holidays, error } = useApi<Holidays>("/api/holidays");
  const sources = useSources();
  const { lists, done } = useEverywhere<ShownItem>(sources, holidayPath(which));
  const [kind, setKind] = useState<Kind>("all");
  const all = useMemo(() => holidayOrder(lists), [lists]);
  const kinds = (Object.keys(KINDS) as Kind[]).filter((k) => k === "all" || all.some((i) => i.kind === k));
  const shown = all.filter((i) => kind === "all" || i.kind === kind);
  const h = holidays?.[which];
  // Shuffle (Episodes): every episode about the holiday, in random order, as the video queue (random.tsx), so they
  // play one after another. The queue is one server's: this one's.
  const { playRandom } = useVideoQueue();
  const [shuffling, setShuffling] = useState(false);
  const [shuffleFailed, setShuffleFailed] = useState(false);
  const shuffle = () => {
    setShuffling(true);
    setShuffleFailed(false);
    // untracked: random holiday viewing stays out of Continue Watching and keeps no progress
    playRandom(`/api/holidays/${which}/random?kind=episode`, null, { untracked: true }).catch(() => setShuffleFailed(true))
      .finally(() => setShuffling(false));
  };

  if (error) return <div className="page"><p className="key-msg bad">{error}</p></div>;
  return (
    <div className="page">
      <div className="page-head">
        <h1>{h ? holidayTitle(which, h) : ""}</h1>
        {done && <span className="count">{shown.length} {shown.length === 1 ? "title" : "titles"}</span>}
      </div>
      {(kinds.length > 2 || kinds.includes("episode")) && (
        <div className="chips">
          {kinds.map((k) => (
            <button key={k} className={`chip ${kind === k ? "on" : ""}`} onClick={() => setKind(k)}>{KINDS[k]}</button>
          ))}
          {kind === "episode" && all.some((i) => i.kind === "episode" && i.rid === null) && (
            <button className="chip shuffle-chip" onClick={shuffle} disabled={shuffling}
              title={shuffleFailed ? "Couldn't load the episodes" : "Play every episode about this holiday, in random order"}>
              <Icon name="shuffle" size={14} /> {shuffleFailed ? "Try again" : "Shuffle"}</button>
          )}
        </div>
      )}
      {done && !all.length && h && (
        <p className="muted">Nothing on your servers is about {h.name}. Movies and episodes count when their title or
          description mentions it (or TMDB's keywords do); an admin can add one by hand on its page.</p>
      )}
      {!done && !all.length && <p className="muted">Loading…</p>}
      <div className="grid">
        {shown.map((i) => <ListedCard key={keyOf(i)} item={i} />)}
      </div>
    </div>
  );
}
