import { useEffect, useState } from "react";
import { api, media, type ContinueItem, type ItemSummary } from "../api";
import { useFocusOnReady, useNav } from "../App";
import { Poster, Shelf, Wide } from "../Cards";
import { metaLine, progressOf, sxe } from "../format";

type Row = { id: string; title: string; items: ItemSummary[] };

/** Home: a big picture of whatever has the focus, then Continue Watching, Recently added, and each library. */
export default function Home() {
  const nav = useNav();
  const [cont, setCont] = useState<ContinueItem[] | null>(null);
  const [rows, setRows] = useState<Row[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [hero, setHero] = useState<ItemSummary | null>(null);

  useEffect(() => {
    const libs = nav.libraries.filter((l) => l.type !== "music");
    Promise.all([
      api.get<ContinueItem[]>("/api/continue?limit=30"),
      api.get<ItemSummary[]>("/api/items?kind=show,movie&sort=added&limit=40"),
      ...libs.map((l) => api.get<ItemSummary[]>(`/api/libraries/${l.id}/items?sort=added&limit=40`)),
    ]).then(([c, recent, ...perLib]) => {
      setCont(c as ContinueItem[]);
      const rs: Row[] = [{ id: "recent", title: "Recently added", items: recent as ItemSummary[] }];
      libs.forEach((l, i) => rs.push({ id: `lib${l.id}`, title: l.name, items: perLib[i] as ItemSummary[] }));
      setRows(rs.filter((r) => r.items.length));
      setHero((c as ContinueItem[])[0] ?? (recent as ItemSummary[])[0] ?? null);
    }).catch((e) => setErr((e as Error).message));
  }, [nav.libraries]);

  const ready = rows !== null;
  useFocusOnReady(ready);

  if (err) return <div className="page"><p className="error big">{err}</p></div>;
  if (!ready) return <div className="page"><div className="spinner" /></div>;
  const empty = !cont?.length && !rows.length;

  const heroArt = hero && ("show" in hero && (hero as ContinueItem).show?.backdrop) || hero?.backdrop;
  return (
    <div className="home">
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
      {empty && <p className="muted big pad">Nothing here yet. Add a library in BAMS on your computer (Settings → Libraries).</p>}
      {!!cont?.length && (
        <Shelf title="Continue watching">
          {cont.map((c) => (
            <Wide key={c.id} fid={`cont-${c.id}`} img={c.still || c.backdrop || c.show?.backdrop}
              title={c.show ? c.show.title : c.title}
              sub={c.kind === "episode" ? `${sxe(c)} · ${c.title}${c.reason === "next" ? " · Next" : ""}` : null}
              progress={progressOf(c)} onFocus={() => setHero(c)}
              onPress={() => nav.push({ name: "player", id: c.id, resume: true })} />
          ))}
        </Shelf>
      )}
      {rows.map((r) => (
        <Shelf key={r.id} title={r.title}>
          {r.items.map((it) => (
            <Poster key={it.id} item={it} fid={`${r.id}-${it.id}`} onFocus={() => setHero(it)}
              onPress={() => nav.push({ name: "detail", id: it.id })} />
          ))}
        </Shelf>
      ))}
    </div>
  );
}
