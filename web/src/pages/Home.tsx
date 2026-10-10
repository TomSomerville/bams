import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { ContinueItem, Genre, ItemSummary, ServerLibrary } from "../api";
import { Backdrop } from "../components/Art";
import { AlbumCard, ContinueCard, PosterCard } from "../components/Cards";
import Icon from "../components/Icon";
import Row from "../components/Row";
import { heroItems, heroPath, homeSpecs, keyOf, mergeGenres, mergeRow, type HomeRowSpec, type Tagged } from "../everywhere";
import { fmtRuntime, seasonsLabel } from "../format";
import { useAuth } from "../auth";
import { scopeLink, useEverywhere, useSources } from "../servers";
import { useApi } from "../useApi";

// Home combines every server this browser shows (its own and the others in Settings → Other BAMS servers): the
// rows, what each asks and how answers merge are in everywhere.ts, shared with the TV app's Home.

function Hero({ items }: { items: Tagged<ItemSummary>[] }) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (items.length < 2) return;
    const t = setInterval(() => setI((n) => (n + 1) % items.length), 9000);
    return () => clearInterval(t);
  }, [items.length]);
  const item = items[i % items.length];
  const page = scopeLink(item.rid, `/title/${item.id}`);
  return (
    <section className="hero">
      {items.map((f, k) => (
        <div key={keyOf(f)} className={`hero-bg ${k === i ? "on" : ""}`}>
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
          <Link to={page} className="btn primary"><Icon name="play" /> Watch</Link>
          <Link to={page} className="btn ghost"><Icon name="info" /> More info</Link>
        </div>
      </div>
      {items.length > 1 && (
        <div className="hero-dots">
          {items.map((f, k) => (
            <button key={keyOf(f)} className={k === i ? "on" : ""} onClick={() => setI(k)} aria-label={`Show ${f.title}`} />
          ))}
        </div>
      )}
    </section>
  );
}

/** One Home row: asked of every server (or only this one, for a library's own row), merged as answers arrive. */
function HomeRow({ spec }: { spec: HomeRowSpec }) {
  const all = useSources();
  const sources = useMemo(() => (spec.everywhere ? all : all.filter((s) => s.rid === null)), [all, spec.everywhere]);
  const { lists } = useEverywhere<ItemSummary>(sources, spec.path);
  const items = useMemo(() => mergeRow(spec, lists), [spec, lists]);
  if (items.length < spec.min) return null;
  const to = spec.library !== undefined ? `/library/${spec.library}` : undefined;
  if (spec.kind === "continue") {
    return <Row title={spec.title}>{items.map((i) => <ContinueCard key={keyOf(i)} item={i as Tagged<ContinueItem>} />)}</Row>;
  }
  if (spec.kind === "albums") return <Row title={spec.title} to={to}>{items.map((a) => <AlbumCard key={keyOf(a)} item={a} />)}</Row>;
  return <Row title={spec.title} to={to}>{items.map((i) => <PosterCard key={keyOf(i)} item={i} />)}</Row>;
}

export default function Home() {
  const sources = useSources();
  const { data: libs, error } = useApi<ServerLibrary[]>("/api/libraries");
  const { lists: genreLists, done: genresDone } = useEverywhere<Genre>(sources, "/api/genres");
  const { lists: newest, done: newestDone } = useEverywhere<ItemSummary>(sources, heroPath);
  const { prefs } = useAuth();

  const genres = useMemo(() => mergeGenres(genreLists), [genreLists]);
  const hero = useMemo(() => (prefs.home_hero ? heroItems(newest) : []), [newest, prefs.home_hero]);
  const specs = useMemo(() => (libs ? homeSpecs(prefs.home_rows, libs, genres) : null), [libs, prefs.home_rows, genres]);

  if (error) return <div className="page"><p className="key-msg bad">{error}</p></div>;
  if (libs && !libs.length && sources.length === 1) {
    return (
      <div className="page empty-state">
        <img src="/brand/bams-icon.png" alt="" />
        <h1>Welcome to BAMS</h1>
        <p className="muted">Add a folder of TV shows, movies or music and BAMS will find, identify and organise them.</p>
        <Link to="/settings" className="btn primary"><Icon name="plus" /> Add a library</Link>
      </div>
    );
  }
  // wait for every server's genres (or its giving up), so the rows don't jump about as genres arrive
  if (!specs || !genresDone || !newestDone) return <div className="page muted">Loading…</div>;

  return (
    <div className={`home ${hero.length ? "" : "no-hero"}`}>
      {hero.length > 0 && <Hero items={hero} />}
      <div className="rows">
        {specs.map((s) => <HomeRow key={s.id} spec={s} />)}
      </div>
    </div>
  );
}
