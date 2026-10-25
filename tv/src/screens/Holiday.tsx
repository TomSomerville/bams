import { useEffect, useMemo, useState } from "react";
import { api, ridOf, sources, type Holidays, type ShownItem } from "../api";
import { askAll, holidayOrder, holidayPath, holidayTitle, keyOf, listedLook, type Tagged } from "../../../web/src/everywhere";
import { useFocusOnReady, useNav } from "../App";
import { Poster } from "../Cards";
import Icon from "../Icon";
import { startQueue, type VideoEntry } from "../random";

// The web's holiday page (web/src/pages/HolidayPage.tsx), a Home holiday row's "See all": every movie and episode
// about the upcoming / recent holiday on every server on this TV, by title. Which holiday it is: the first server's.
// Chips pick movies or episodes; under Episodes, Shuffle plays every episode about it (this server's) in random order,
// kept nowhere: no progress, not in Continue Watching (random.tsx `untracked`).

const KINDS = { all: "All", movie: "Movies", episode: "Episodes" } as const;
type Kind = keyof typeof KINDS;

type Item = Tagged<ShownItem>;

export default function HolidayScreen({ which }: { which: "next" | "recent" }) {
  const nav = useNav();
  const [holidays, setHolidays] = useState<Holidays | null>(null);
  const [lists, setLists] = useState<Map<number | null, Item[]>>(new Map());
  const [done, setDone] = useState(false);
  const [kind, setKind] = useState<Kind>("all");
  const [shuffle, setShuffle] = useState<"busy" | "failed" | null>(null);

  useEffect(() => {
    let alive = true;
    api.get<Holidays>("/api/holidays").then((h) => { if (alive) setHolidays(h); }).catch(() => {});
    void askAll<ShownItem>(sources(), holidayPath(which), (rid, list) => {
      if (alive) setLists((m) => new Map(m).set(rid, list));
    }).then(() => { if (alive) setDone(true); });
    return () => { alive = false; };
  }, [which]);

  const items = useMemo(
    () => holidayOrder(sources().filter((s) => lists.has(s.rid)).map((s) => lists.get(s.rid)!)), [lists]);
  useFocusOnReady(done || items.length > 0);
  const h = holidays?.[which];
  const kinds = (Object.keys(KINDS) as Kind[]).filter((k) => k === "all" || items.some((i) => i.kind === k));
  const shown = items.filter((i) => kind === "all" || i.kind === kind);
  const canShuffle = kind === "episode" && items.some((i) => i.kind === "episode" && i.rid === null);

  const play = async () => {
    if (shuffle === "busy") return;
    setShuffle("busy");
    try {
      const r = await api.get<{ items: VideoEntry[] }>(`/api/holidays/${which}/random?kind=episode`);
      if (!r.items.length) return setShuffle(null);
      startQueue(r.items, undefined, { untracked: true });
      setShuffle(null);
      nav.push({ name: "player", id: r.items[0].id, resume: false, shuffle: true });
    } catch {
      setShuffle("failed");
    }
  };

  return (
    <div className="page">
      <div className="page-head">
        <h1>{h ? holidayTitle(which, h) : which === "next" ? "Upcoming Holiday" : "Recent Holiday"}</h1>
        {shown.length > 0 && <span className="muted big">{shown.length} {shown.length === 1 ? "title" : "titles"}</span>}
      </div>
      {kinds.includes("episode") && (
        <div className="chips genres" data-row>
          {kinds.map((k) => (
            <button key={k} className={`chip ${kind === k ? "on" : ""}`} data-fid={`hol-kind-${k}`} onClick={() => setKind(k)}>
              {KINDS[k]}</button>
          ))}
          {canShuffle && (
            <button className="chip" data-fid="hol-shuffle" onClick={() => void play()}>
              <Icon name="shuffle" size={26} /> {shuffle === "failed" ? "Try again" : shuffle === "busy" ? "Loading…" : "Shuffle"}
            </button>
          )}
        </div>
      )}
      {!items.length && !done && <div className="spinner" />}
      {!items.length && done && (
        <p className="muted big">Nothing on your servers is about {h?.name ?? "this holiday"}. An admin can add titles to
          a holiday on their page in BAMS on a computer.</p>
      )}
      <div className="grid">
        {shown.map((it, i) => (
          <Poster key={keyOf(it)} item={it} rid={ridOf(it.rid)} fid={`hol-${keyOf(it)}`} look={listedLook(it)}
            autoFocus={i === 0} onPress={() => nav.push({ name: "detail", id: it.id, rid: ridOf(it.rid) })} />
        ))}
      </div>
    </div>
  );
}
