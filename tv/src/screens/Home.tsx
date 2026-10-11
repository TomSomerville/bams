import { useEffect, useMemo, useRef, useState } from "react";
import { api, apiFor, mediaFor, ridOf, sources, type ContinueItem, type ItemSummary, type User, type WatchlistItem } from "../api";
import type { Genre, HomeRowPref } from "../../../web/src/api";
import {
  askAll, heroItems, heroPath, homeSpecs, keyOf, listedLook, mergeGenres, mergeRow, type HomeRowSpec, type Tagged,
} from "../../../web/src/everywhere";
import { useFocusOnReady, useNav } from "../App";
import { ListMenu } from "../ListMenu";
import { Poster, Shelf, Square, Wide } from "../Cards";
import { metaLine, progressOf, sxe } from "../format";
import { setKeyHandler } from "../keys";
import { focus, focusFirst, focusId } from "../nav";
import { isBack } from "../tizen";

// The web's Home (web/src/pages/Home.tsx), row for row: the rows each person chose in Settings → Home page (saved
// on their first server, `home_rows`), Continue Watching, Recently Added, Top Rated and each genre combined from
// every server on this TV, and each library's own row. What each row asks and how it's merged:
// web/src/everywhere.ts, shared by both.

const HERO_EVERY = 9000;  // the web banner's pace

type Item = Tagged<ItemSummary>;

/** Ask every source (or, for a library's own row, only the first server) for a row, merging answers as they come. */
function useRow(spec: HomeRowSpec): Item[] | null {
  const [lists, setLists] = useState<Map<number | null, Item[]> | null>(null);
  const p = spec.path;
  useEffect(() => {

    let alive = true;
    setLists(new Map());
    const srcs = spec.everywhere ? sources() : sources().filter((s) => s.rid === null);
    void askAll<ItemSummary>(srcs, p, (rid, list) => {
      if (alive) setLists((m) => new Map(m ?? []).set(rid, list));
    });
    return () => { alive = false; };
  }, [p, spec]);
  return useMemo(() => {
    if (!lists) return null;
    const ordered = sources().filter((s) => lists.has(s.rid)).map((s) => lists.get(s.rid)!);
    return mergeRow(spec, ordered);
  }, [lists, spec]);
}

export default function Home() {
  const nav = useNav();
  const [specs, setSpecs] = useState<HomeRowSpec[] | null>(null);
  const [showHero, setShowHero] = useState(true);
  const [focused, setFocused] = useState<Item | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [newest, setNewest] = useState<Item[][]>([]);
  const [heroAt, setHeroAt] = useState(0);

  useEffect(() => {
    // prefs fresh from the server each time: they may have been changed on the web since the app started
    const genreLists: Genre[][] = [];
    const newestLists: Item[][] = [];
    Promise.all([
      api.get<{ user: (User & { prefs?: { home_hero: boolean; home_rows: HomeRowPref[]; watchlist_name?: string } }) | null }>("/api/auth/state"),
      askAll<Genre>(sources(), "/api/genres", (_r, l) => { genreLists.push(l); }),
      askAll<ItemSummary>(sources(), heroPath, (_r, l) => { newestLists.push(l); }),
    ]).then(([st]) => {
      const prefs = st.user?.prefs ?? { home_hero: true, home_rows: [], watchlist_name: "" };
      setShowHero(prefs.home_hero);
      setNewest(newestLists);
      setSpecs(homeSpecs(prefs.home_rows, nav.libraries, mergeGenres(genreLists), prefs.watchlist_name));
    }).catch((e) => setErr((e as Error).message));
  }, [nav.libraries, nav.servers.length]);

  const banner = useMemo(() => heroItems(newest), [newest]);
  useEffect(() => {  // the banner turns over like the web's, until a card has the focus
    if (focused || banner.length < 2) return;
    const t = setInterval(() => setHeroAt((n) => (n + 1) % banner.length), HERO_EVERY);
    return () => clearInterval(t);
  }, [focused, banner.length]);

  useFocusOnReady(specs !== null);

  if (err) return <div className="page"><p className="error big">{err}</p></div>;
  if (!specs) return <div className="page"><div className="spinner" /></div>;

  const hero = focused ?? banner[heroAt % Math.max(1, banner.length)] ?? null;
  const show = hero && (hero as Tagged<ContinueItem>).show;
  const heroArt = hero && (show?.backdrop || hero.backdrop || hero.poster);
  return (
    <div className={`home ${showHero ? "" : "no-hero"}`}>
      {showHero && (
        <div className="hero">
          {heroArt && <img className="hero-art" src={mediaFor(ridOf(hero!.rid))(heroArt) ?? undefined} alt="" />}
          <div className="hero-shade" />
          {hero && (
            <div className="hero-text">
              <h1>{show?.title ?? hero.title}</h1>
              {hero.kind === "episode" && <div className="hero-ep">{sxe(hero)} · {hero.title}</div>}
              <div className="meta">{metaLine(hero)}</div>
              {hero.overview && <p className="overview clamp3">{hero.overview}</p>}
            </div>
          )}
        </div>
      )}
      {specs.map((s) => <HomeShelf key={s.id} spec={s} onFocus={setFocused} />)}
      {!specs.length && <p className="muted big pad">Nothing here yet. Add a library in BAMS on your computer (Settings → Libraries).</p>}
    </div>
  );
}

/** One row of Home: the web's HomeRow, with the TV's cards. Holding OK on a Continue Watching card offers to take it
 *  out of the row (ContinueMenu), like a long press on the web; on a watch list entry, to take it off the list. */
function HomeShelf({ spec, onFocus }: { spec: HomeRowSpec; onFocus: (i: Item) => void }) {
  const nav = useNav();
  const row = useRow(spec);
  const [removed, setRemoved] = useState<Set<string>>(new Set());
  const [menu, setMenu] = useState<{ item: Tagged<ContinueItem>; fid: string } | null>(null);
  const [listMenu, setListMenu] = useState<{ item: Tagged<WatchlistItem>; fid: string } | null>(null);
  const items = useMemo(() => row?.filter((i) => !removed.has(keyOf(i))) ?? null, [row, removed]);
  if (!items || items.length < spec.min) return null;
  const fidOf = (i: Item) => `${spec.id}-${keyOf(i)}`;

  const closeMenu = () => {
    const back = menu?.fid ?? listMenu?.fid;
    setMenu(null);
    setListMenu(null);
    setTimeout(() => focusId(back));
  };
  const removedOne = (c: Item) => {
    const i = items.findIndex((x) => keyOf(x) === keyOf(c));
    const next = items[i + 1] ?? items[i - 1];  // the focus goes to the card beside it
    setRemoved((s) => new Set(s).add(keyOf(c)));
    setMenu(null);
    setListMenu(null);
    setTimeout(() => {
      if (!(next && focusId(fidOf(next)))) focusFirst(document.querySelector("main") ?? document);
    });
  };

  return (
    <>
      <Shelf title={spec.title}>
        {items.map((it) => {
          const rid = ridOf(it.rid);
          const fid = fidOf(it);
          if (spec.kind === "continue") {
            const c = it as Tagged<ContinueItem>;
            return (
              <Wide key={keyOf(c)} fid={fid} rid={rid} img={c.still || c.backdrop || c.show?.backdrop}
                title={c.show ? c.show.title : c.title}
                sub={c.kind === "episode" ? `${sxe(c)} · ${c.title}${c.reason === "next" ? " · Next" : ""}` : null}
                progress={progressOf(c)} onFocus={() => onFocus(c)}
                onPress={() => nav.push({ name: "player", id: c.id, rid, resume: true })}
                onHold={() => setMenu({ item: c, fid })} />
            );
          }
          if (spec.kind === "watchlist") {
            const w = it as Tagged<WatchlistItem>;
            return (
              <Poster key={keyOf(w)} item={w} rid={rid} fid={fid} look={listedLook(w)} onFocus={() => onFocus(w)}
                onPress={() => nav.push({ name: "detail", id: w.id, rid })}
                onHold={() => setListMenu({ item: w, fid })} />
            );
          }
          if (spec.kind === "albums") {
            return (
              <Square key={keyOf(it)} fid={fid} rid={rid} img={it.poster} title={it.title}
                sub={[it.parent_title, it.year].filter(Boolean).join(" · ")} onFocus={() => onFocus(it)}
                onPress={() => nav.push({ name: "detail", id: it.id, rid })} />
            );
          }
          return (
            <Poster key={keyOf(it)} item={it} rid={rid} fid={fid} onFocus={() => onFocus(it)}
              onPress={() => nav.push({ name: "detail", id: it.id, rid })} />
          );
        })}
      </Shelf>
      {menu && <ContinueMenu item={menu.item} onClose={closeMenu} onRemoved={() => removedOne(menu.item)} />}
      {listMenu && (
        <ListMenu id={listMenu.item.id} rid={ridOf(listMenu.item.rid)} on title={listedLook(listMenu.item).title}
          sub={listedLook(listMenu.item).sub} onClose={closeMenu} onDone={() => removedOne(listMenu.item)} />
      )}
    </>
  );
}

/** Over Home after holding OK on a Continue Watching card: take it out of the row (the movie, or the episode's whole
 *  show; it comes back once it's watched again), or not. Back closes it too. */
function ContinueMenu({ item, onClose, onRemoved }: {
  item: Tagged<ContinueItem>; onClose: () => void; onRemoved: () => void;
}) {
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
  const remove = async () => {
    if (busy) return;
    setBusy(true);
    setErr(null);
    try {
      await apiFor(ridOf(item.rid)).del(`/api/continue/${item.id}`);
      onRemoved();
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  };
  return (
    <div className="hold-menu" data-trap ref={ref}>
      <div className="hold-box">
        <h2>{item.show ? item.show.title : item.title}</h2>
        {item.kind === "episode" && <div className="hold-ep">{sxe(item)} · {item.title}</div>}
        <p className="muted">
          {item.show ? "The show" : "The film"} leaves Continue Watching until you watch it again.
        </p>
        {err && <p className="error">{err}</p>}
        <div className="button-row">
          <button className="btn primary" onClick={() => void remove()}>
            {busy ? "Removing…" : "Remove from Continue Watching"}
          </button>
          <button className="btn" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}
