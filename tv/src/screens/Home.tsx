import { useEffect, useMemo, useState } from "react";
import { api, mediaFor, ridOf, sources, type ContinueItem, type ItemSummary, type User } from "../api";
import type { Genre, HomeRowPref } from "../../../web/src/api";
import {
  askAll, heroItems, heroPath, homeSpecs, keyOf, mergeGenres, mergeRow, type HomeRowSpec, type Tagged,
} from "../../../web/src/everywhere";
import { useFocusOnReady, useNav } from "../App";
import { Poster, Shelf, Square, Wide } from "../Cards";
import { metaLine, progressOf, sxe } from "../format";

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
      api.get<{ user: (User & { prefs?: { home_hero: boolean; home_rows: HomeRowPref[] } }) | null }>("/api/auth/state"),
      askAll<Genre>(sources(), "/api/genres", (_r, l) => { genreLists.push(l); }),
      askAll<ItemSummary>(sources(), heroPath, (_r, l) => { newestLists.push(l); }),
    ]).then(([st]) => {
      const prefs = st.user?.prefs ?? { home_hero: true, home_rows: [] };
      setShowHero(prefs.home_hero);
      setNewest(newestLists);
      setSpecs(homeSpecs(prefs.home_rows, nav.libraries, mergeGenres(genreLists)));
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

/** One row of Home: the web's HomeRow, with the TV's cards. */
function HomeShelf({ spec, onFocus }: { spec: HomeRowSpec; onFocus: (i: Item) => void }) {
  const nav = useNav();
  const items = useRow(spec);
  if (!items || items.length < spec.min) return null;
  return (
    <Shelf title={spec.title}>
      {items.map((it) => {
        const rid = ridOf(it.rid);
        const fid = `${spec.id}-${keyOf(it)}`;
        if (spec.kind === "continue") {
          const c = it as Tagged<ContinueItem>;
          return (
            <Wide key={keyOf(c)} fid={fid} rid={rid} img={c.still || c.backdrop || c.show?.backdrop}
              title={c.show ? c.show.title : c.title}
              sub={c.kind === "episode" ? `${sxe(c)} · ${c.title}${c.reason === "next" ? " · Next" : ""}` : null}
              progress={progressOf(c)} onFocus={() => onFocus(c)}
              onPress={() => nav.push({ name: "player", id: c.id, rid, resume: true })} />
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
  );
}
