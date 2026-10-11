import { useEffect, useMemo, useState } from "react";
import { ridOf, sources, type WatchlistItem } from "../api";
import { askAll, keyOf, listedLook, listedOrder, WATCHLIST_PATH, type Tagged } from "../../../web/src/everywhere";
import { useFocusOnReady, useNav } from "../App";
import { Poster } from "../Cards";
import { ListMenu, useListName } from "../ListMenu";
import { focusFirst, focusId } from "../nav";

// The web's watch list page (web/src/pages/Watchlist.tsx): one list of every server on this TV, each server keeping
// its own part of it per account. OK opens an entry; holding OK offers to take it off.

type Item = Tagged<WatchlistItem>;

export default function Watchlist() {
  const nav = useNav();
  const name = useListName();
  const [lists, setLists] = useState<Map<number | null, Item[]>>(new Map());
  const [done, setDone] = useState(false);
  const [removed, setRemoved] = useState<Set<string>>(new Set());
  const [menu, setMenu] = useState<{ item: Item; fid: string } | null>(null);

  useEffect(() => {
    let alive = true;
    setLists(new Map());
    setDone(false);
    void askAll<WatchlistItem>(sources(), WATCHLIST_PATH, (rid, list) => {
      if (alive) setLists((m) => new Map(m).set(rid, list));
    }).then(() => { if (alive) setDone(true); });
    return () => { alive = false; };
  }, [nav.servers.length]);

  const items = useMemo(() => {
    const ordered = sources().filter((s) => lists.has(s.rid)).map((s) => lists.get(s.rid)!);
    return listedOrder(ordered).filter((i) => !removed.has(keyOf(i)));
  }, [lists, removed]);

  useFocusOnReady(done || items.length > 0);

  const fidOf = (i: Item) => `wl-${keyOf(i)}`;
  const closeMenu = () => {
    const back = menu?.fid;
    setMenu(null);
    setTimeout(() => focusId(back));
  };
  const takenOff = (it: Item) => {
    const i = items.findIndex((x) => keyOf(x) === keyOf(it));
    const next = items[i + 1] ?? items[i - 1];  // the focus goes to the poster beside it
    setRemoved((s) => new Set(s).add(keyOf(it)));
    setMenu(null);
    setTimeout(() => {
      if (!(next && focusId(fidOf(next)))) focusFirst(document.querySelector("main") ?? document);
    });
  };

  return (
    <div className="page">
      <div className="page-head">
        <h1>{name}</h1>
        {items.length > 0 && <span className="muted big">{items.length} {items.length === 1 ? "title" : "titles"}</span>}
      </div>
      {!items.length && !done && <div className="spinner" />}
      {!items.length && done && (
        <p className="muted big">
          Nothing on {name} yet. Add movies, shows and seasons with the {name} button on their page, or hold OK on an
          episode. Titles from every server go on this one list, and it's the same on every device.
        </p>
      )}
      <div className="grid">
        {items.map((it, i) => {
          const look = listedLook(it);
          return (
            <Poster key={keyOf(it)} item={it} rid={ridOf(it.rid)} fid={fidOf(it)} look={look} autoFocus={i === 0}
              onPress={() => nav.push({ name: "detail", id: it.id, rid: ridOf(it.rid) })}
              onHold={() => setMenu({ item: it, fid: fidOf(it) })} />
          );
        })}
      </div>
      {menu && (() => {
        const look = listedLook(menu.item);
        return <ListMenu id={menu.item.id} rid={ridOf(menu.item.rid)} on title={look.title} sub={look.sub}
          onClose={closeMenu} onDone={() => takenOff(menu.item)} />;
      })()}
    </div>
  );
}
