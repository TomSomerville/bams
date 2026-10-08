import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { ContinueItem, ItemSummary, ServerLibrary } from "../api";
import { Backdrop } from "../components/Art";
import { AlbumCard, ContinueCard, PosterCard } from "../components/Cards";
import Icon from "../components/Icon";
import Row from "../components/Row";
import { fmtRuntime, seasonsLabel } from "../format";
import { useApi } from "../useApi";

function Hero({ items }: { items: ItemSummary[] }) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (items.length < 2) return;
    const t = setInterval(() => setI((n) => (n + 1) % items.length), 9000);
    return () => clearInterval(t);
  }, [items.length]);
  const item = items[i % items.length];
  return (
    <section className="hero">
      {items.map((f, k) => (
        <div key={f.id} className={`hero-bg ${k === i ? "on" : ""}`}>
          <Backdrop src={f.backdrop} poster={f.poster} title={f.title} className="hero-img" />
        </div>
      ))}
      <div className="hero-shade" />
      <div className="hero-body">
        <div className="hero-kicker">{item.kind === "show" ? "Series" : "Movie"} · Recently added</div>
        <h1 className="hero-title">{item.title}</h1>
        <div className="meta">
          {item.rating ? <span className="score">★ {item.rating.toFixed(1)}</span> : null}
          {item.year && <span>{item.year}</span>}
          <span>{item.kind === "show" ? seasonsLabel(item) : fmtRuntime(item.runtime)}</span>
          {item.genres.slice(0, 2).map((g) => <span key={g} className="tag">{g}</span>)}
        </div>
        {item.overview && <p className="hero-overview">{item.overview}</p>}
        <div className="actions">
          <Link to={`/title/${item.id}`} className="btn primary"><Icon name="play" /> Watch</Link>
          <Link to={`/title/${item.id}`} className="btn ghost"><Icon name="info" /> More info</Link>
        </div>
      </div>
      {items.length > 1 && (
        <div className="hero-dots">
          {items.map((f, k) => (
            <button key={f.id} className={k === i ? "on" : ""} onClick={() => setI(k)} aria-label={`Show ${f.title}`} />
          ))}
        </div>
      )}
    </section>
  );
}

export default function Home() {
  const { data: libs, error } = useApi<ServerLibrary[]>("/api/libraries");
  const { data: items } = useApi<ItemSummary[]>("/api/items?sort=added&limit=500");
  const hasMusic = !!libs?.some((l) => l.type === "music");
  const { data: albums } = useApi<ItemSummary[]>(hasMusic ? "/api/items?kind=album&sort=added&limit=300" : null);
  const { data: resume } = useApi<ContinueItem[]>("/api/continue");

  const recent = items?.slice(0, 20) ?? [];
  const hero = useMemo(() => (items ?? []).filter((i) => i.backdrop || i.poster).slice(0, 6), [items]);
  const topGenres = useMemo(() => {
    const n = new Map<string, number>();
    for (const i of items ?? []) for (const g of i.genres) n.set(g, (n.get(g) ?? 0) + 1);
    return [...n.entries()].filter(([, c]) => c >= 2).sort((a, b) => b[1] - a[1]).slice(0, 4).map(([g]) => g);
  }, [items]);
  const rated = useMemo(() => (items ?? []).filter((i) => i.rating).sort((a, b) => b.rating! - a.rating!).slice(0, 20), [items]);

  if (error) return <div className="page"><p className="key-msg bad">{error}</p></div>;
  if (libs && !libs.length) {
    return (
      <div className="page empty-state">
        <img src="/brand/bams-icon.png" alt="" />
        <h1>Welcome to BAMS</h1>
        <p className="muted">Add a folder of TV shows, movies or music and BAMS will find, identify and organise them.</p>
        <Link to="/settings" className="btn primary"><Icon name="plus" /> Add a library</Link>
      </div>
    );
  }
  if (items && !items.length && (!hasMusic || (albums && !albums.length))) {
    return (
      <div className="page empty-state">
        <h1>Nothing here yet</h1>
        <p className="muted">Your libraries haven't found any media yet. Scans run in the background; check their status in Settings.</p>
        <Link to="/settings" className="btn ghost">Open Settings</Link>
      </div>
    );
  }
  if (!items || !libs || (hasMusic && !albums)) return <div className="page muted">Loading…</div>;

  return (
    <div className={`home ${hero.length ? "" : "no-hero"}`}>
      {hero.length > 0 && <Hero items={hero} />}
      <div className="rows">
        {!!resume?.length && <Row title="Continue Watching">{resume.map((i) => <ContinueCard key={i.id} item={i} />)}</Row>}
        {recent.length > 0 && <Row title="Recently Added">{recent.map((i) => <PosterCard key={i.id} item={i} />)}</Row>}
        {libs.filter((l) => l.type === "music").map((l) => {
          const la = (albums ?? []).filter((a) => a.library_id === l.id).slice(0, 30);
          return la.length ? (
            <Row key={l.id} title={`${l.name}: recently added`} to={`/library/${l.id}`}>
              {la.map((a) => <AlbumCard key={a.id} item={a} />)}
            </Row>
          ) : null;
        })}
        {libs.filter((l) => l.type !== "music").map((l) => {
          const li = items.filter((i) => i.library_id === l.id).sort((a, b) => a.title.localeCompare(b.title));
          return li.length ? (
            <Row key={l.id} title={l.name} to={`/library/${l.id}`}>{li.map((i) => <PosterCard key={i.id} item={i} />)}</Row>
          ) : null;
        })}
        {rated.length >= 4 && <Row title="Top Rated">{rated.map((i) => <PosterCard key={i.id} item={i} />)}</Row>}
        {topGenres.map((g) => (
          <Row key={g} title={g}>{items.filter((i) => i.genres.includes(g)).map((i) => <PosterCard key={i.id} item={i} />)}</Row>
        ))}
      </div>
    </div>
  );
}
