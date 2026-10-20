import { useEffect, useMemo, useState } from "react";
import { api, ridOf, sources, type Holidays, type ShownItem } from "../api";
import { askAll, holidayOrder, holidayPath, holidayTitle, keyOf, listedLook, type Tagged } from "../../../web/src/everywhere";
import { useFocusOnReady, useNav } from "../App";
import { Poster } from "../Cards";

// The web's holiday page (web/src/pages/HolidayPage.tsx), a Home holiday row's "See all": every movie and episode
// about the upcoming / recent holiday on every server on this TV, by title. Which holiday it is: the first server's.

type Item = Tagged<ShownItem>;

export default function HolidayScreen({ which }: { which: "next" | "recent" }) {
  const nav = useNav();
  const [holidays, setHolidays] = useState<Holidays | null>(null);
  const [lists, setLists] = useState<Map<number | null, Item[]>>(new Map());
  const [done, setDone] = useState(false);

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

  return (
    <div className="page">
      <div className="page-head">
        <h1>{h ? holidayTitle(which, h) : which === "next" ? "Upcoming Holiday" : "Recent Holiday"}</h1>
        {items.length > 0 && <span className="muted big">{items.length} {items.length === 1 ? "title" : "titles"}</span>}
      </div>
      {!items.length && !done && <div className="spinner" />}
      {!items.length && done && (
        <p className="muted big">Nothing on your servers is about {h?.name ?? "this holiday"}. An admin can add titles to
          a holiday on their page in BAMS on a computer.</p>
      )}
      <div className="grid">
        {items.map((it, i) => (
          <Poster key={keyOf(it)} item={it} rid={ridOf(it.rid)} fid={`hol-${keyOf(it)}`} look={listedLook(it)}
            autoFocus={i === 0} onPress={() => nav.push({ name: "detail", id: it.id, rid: ridOf(it.rid) })} />
        ))}
      </div>
    </div>
  );
}
