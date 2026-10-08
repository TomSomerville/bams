import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { continueWatching, featured, fmtRuntime, items, movies, recentlyAdded, seasonsLabel, shows } from "../data";
import { Backdrop } from "../components/Art";
import { ContinueCard, PlayBadge, PosterCard } from "../components/Cards";
import Icon from "../components/Icon";
import Row from "../components/Row";

function Hero() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((n) => (n + 1) % featured.length), 9000);
    return () => clearInterval(t);
  }, []);
  const item = featured[i];
  return (
    <section className="hero">
      {featured.map((f, k) => (
        <div key={f.id} className={`hero-bg ${k === i ? "on" : ""}`}>
          <Backdrop item={f} className="hero-img" />
        </div>
      ))}
      <div className="hero-shade" />
      <div className="hero-body">
        <div className="hero-kicker">{item.type === "show" ? "Series" : "Movie"} · Recently added</div>
        <h1 className="hero-title">{item.title}</h1>
        <div className="meta">
          <span className="score">★ {item.score.toFixed(1)}</span>
          <span>{item.year}</span>
          <span className="rating-box">{item.rating}</span>
          <span>{item.type === "show" ? seasonsLabel(item) : fmtRuntime(item.runtime)}</span>
          <span className="tag">{item.media.resolution}{item.media.hdr ? ` ${item.media.hdr}` : ""}</span>
        </div>
        <p className="hero-overview">{item.overview}</p>
        <div className="actions">
          <Link to={`/play/${item.id}`} className="btn primary"><Icon name="play" /> Play</Link>
          <Link to={`/title/${item.id}`} className="btn ghost"><Icon name="info" /> More info</Link>
        </div>
      </div>
      <div className="hero-dots">
        {featured.map((f, k) => (
          <button key={f.id} className={k === i ? "on" : ""} onClick={() => setI(k)} aria-label={`Show ${f.title}`} />
        ))}
      </div>
    </section>
  );
}

export default function Home() {
  const fourK = items.filter((i) => i.media.resolution === "4K");
  return (
    <div className="home">
      <Hero />
      <div className="rows">
        <Row title="Continue Watching">
          {continueWatching.map((c) => <ContinueCard key={c.item.id} entry={c} />)}
        </Row>
        <Row title="Recently Added">
          {recentlyAdded.slice(0, 12).map((i) => <PosterCard key={i.id} item={i} />)}
        </Row>
        <Row title="Movies" to="/movies">
          {movies.map((i) => <PosterCard key={i.id} item={i} />)}
        </Row>
        <Row title="TV Shows" to="/tv">
          {shows.map((i) => <PosterCard key={i.id} item={i} />)}
        </Row>
        <Row title="4K & HDR">
          {fourK.map((i) => <PosterCard key={i.id} item={i} />)}
        </Row>
        <section className="row dev-note">
          <h2>Prototype notes</h2>
          <p>
            All titles are fictional and their art is generated locally. Each title page shows how BAMS would play the
            file in a browser: <PlayBadge item={items.find((i) => i.media.container === "MP4")!} />{" "}
            <PlayBadge item={items.find((i) => i.media.container === "MKV" && i.media.video === "H.264")!} />{" "}
            <PlayBadge item={items.find((i) => i.media.video === "HEVC")!} />
          </p>
        </section>
      </div>
    </div>
  );
}
