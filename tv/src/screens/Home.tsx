import { useEffect, useState } from "react";
import { api, media, type ContinueItem, type ItemSummary, type User } from "../api";
import type { Genre, HomeRowPref } from "../../../web/src/api";
import { homeRows, rowGenre } from "../../../web/src/homeRows";
import { useFocusOnReady, useNav } from "../App";
import { Poster, Shelf, Wide } from "../Cards";
import { metaLine, progressOf, sxe } from "../format";

// The same rows as the web's Home (web/src/pages/Home.tsx), in the order and with the rows each person chose in
// Settings → Home page (saved on the server, `home_rows`), from the same endpoints. Music rows are left out: the
// TV app plays video only.
const ROW_SIZE = 30;
const TOP_RATING = 7;  // web Home's TOP_RATING: Top Rated picks at random from titles rated at least this

type Row = { id: string; title: string; kind: "continue" | "items"; path?: string; min?: number };

export default function Home() {
  const nav = useNav();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [cont, setCont] = useState<ContinueItem[]>([]);
  const [hero, setHero] = useState<ItemSummary | null>(null);
  const [showHero, setShowHero] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    // prefs fresh from the server each time: they may have been changed on the web since the app started
    Promise.all([
      api.get<{ user: (User & { prefs?: { home_hero: boolean; home_rows: HomeRowPref[] } }) | null }>("/api/auth/state"),
      api.get<Genre[]>("/api/genres"),
      api.get<ContinueItem[]>("/api/continue"),
    ]).then(([st, genres, c]) => {
      const prefs = st.user?.prefs ?? { home_hero: true, home_rows: [] };
      const libs = nav.libraries;
      const out: Row[] = [];
      for (const r of homeRows(prefs.home_rows, libs, genres).filter((x) => x.show)) {
        const g = rowGenre(r.id);
        if (r.id === "continue") out.push({ id: r.id, title: r.label, kind: "continue" });
        else if (r.id === "recent") out.push({ id: r.id, title: r.label, kind: "items", path: `/api/items?kind=show,movie&sort=added&limit=${ROW_SIZE}` });
        else if (r.id === "top_rated") out.push({ id: r.id, title: r.label, kind: "items", min: 4, path: `/api/items?sort=random&min_rating=${TOP_RATING}&limit=${ROW_SIZE}` });
        else if (g !== null) out.push({ id: r.id, title: g, kind: "items", path: `/api/items?sort=random&genre=${encodeURIComponent(g)}&limit=${ROW_SIZE}` });
        else {
          const l = libs.find((x) => `lib:${x.id}` === r.id);
          if (l && l.type !== "music") out.push({ id: r.id, title: r.label, kind: "items", path: `/api/libraries/${l.id}/items?sort=recent&limit=${ROW_SIZE}` });
        }
      }
      setShowHero(prefs.home_hero);
      setCont(c);
      setHero(c[0] ?? null);
      setRows(out);
    }).catch((e) => setErr((e as Error).message));
  }, [nav.libraries]);

  useFocusOnReady(rows !== null);

  if (err) return <div className="page"><p className="error big">{err}</p></div>;
  if (!rows) return <div className="page"><div className="spinner" /></div>;

  const heroArt = hero && ((hero as ContinueItem).show?.backdrop || hero.backdrop);
  return (
    <div className={`home ${showHero ? "" : "no-hero"}`}>
      {showHero && (
        <div className="hero">
          {heroArt && <img className="hero-art" src={media(heroArt) ?? undefined} alt="" />}
          <div className="hero-shade" />
          {hero && (
            <div className="hero-text">
              <h1>{(hero as ContinueItem).show?.title ?? hero.title}</h1>
              {hero.kind === "episode" && <div className="hero-ep">{sxe(hero)} · {hero.title}</div>}
              <div className="meta">{metaLine(hero)}</div>
              {hero.overview && <p className="overview clamp3">{hero.overview}</p>}
            </div>
          )}
        </div>
      )}
      {rows.map((r) => r.kind === "continue"
        ? cont.length > 0 && (
          <Shelf key={r.id} title={r.title}>
            {cont.map((c) => (
              <Wide key={c.id} fid={`cont-${c.id}`} img={c.still || c.backdrop || c.show?.backdrop}
                title={c.show ? c.show.title : c.title}
                sub={c.kind === "episode" ? `${sxe(c)} · ${c.title}${c.reason === "next" ? " · Next" : ""}` : null}
                progress={progressOf(c)} onFocus={() => setHero(c)}
                onPress={() => nav.push({ name: "player", id: c.id, resume: true })} />
            ))}
          </Shelf>
        )
        : <ItemsShelf key={r.id} row={r} onFocus={setHero} onPress={(it) => nav.push({ name: "detail", id: it.id })} />)}
      {!cont.length && rows.every((r) => r.kind === "continue") && (
        <p className="muted big pad">Nothing here yet. Add a library in BAMS on your computer (Settings → Libraries).</p>
      )}
    </div>
  );
}

/** A row whose titles the server picks (newest, random, a genre): loaded on its own, hidden while empty. */
function ItemsShelf({ row, onFocus, onPress }: { row: Row; onFocus: (i: ItemSummary) => void; onPress: (i: ItemSummary) => void }) {
  const [items, setItems] = useState<ItemSummary[] | null>(null);
  useEffect(() => {
    api.get<ItemSummary[]>(row.path!).then(setItems).catch(() => setItems([]));
  }, [row.path]);
  if (!items || items.length < (row.min ?? 1)) return null;
  return (
    <Shelf title={row.title}>
      {items.map((it) => (
        <Poster key={it.id} item={it} fid={`${row.id}-${it.id}`} onFocus={() => onFocus(it)} onPress={() => onPress(it)} />
      ))}
    </Shelf>
  );
}
