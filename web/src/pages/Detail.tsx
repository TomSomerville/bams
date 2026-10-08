import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { byId, episodes, fmtRuntime, items, playMethod, seasonsLabel, sxe } from "../data";
import { Backdrop, Poster } from "../components/Art";
import { PlayBadge, PosterCard } from "../components/Cards";
import Icon from "../components/Icon";
import Row from "../components/Row";

export default function Detail() {
  const { id } = useParams();
  const item = byId(id ?? "");
  const [season, setSeason] = useState(1);
  const [watched, setWatched] = useState(false);
  if (!item) return <div className="page"><h1>Not found</h1></div>;

  const m = item.media;
  const similar = items.filter((i) => i.id !== item.id && i.genres.some((g) => item.genres.includes(g))).slice(0, 10);
  const eps = item.type === "show" ? episodes(item, season) : [];
  const method = playMethod(m);

  return (
    <div className="detail">
      <div className="detail-bg">
        <Backdrop item={item} className="detail-img" />
        <div className="detail-shade" />
      </div>

      <div className="detail-body">
        <div className="detail-poster"><Poster item={item} /></div>
        <div className="detail-info">
          <h1>{item.title}</h1>
          <div className="meta">
            <span className="score">★ {item.score.toFixed(1)}</span>
            <span>{item.year}</span>
            <span className="rating-box">{item.rating}</span>
            <span>{item.type === "show" ? seasonsLabel(item) : fmtRuntime(item.runtime)}</span>
            {item.genres.map((g) => <span key={g} className="tag">{g}</span>)}
          </div>
          <p className="overview">{item.overview}</p>
          <div className="actions">
            <Link to={`/play/${item.id}`} className="btn primary">
              <Icon name="play" /> {item.type === "show" ? `Play ${sxe(1, 1)}` : "Play"}
            </Link>
            <button className="btn ghost" title="Download the original file (phase 2)"><Icon name="download" /> Download</button>
            <button className={`btn ghost ${watched ? "on" : ""}`} onClick={() => setWatched(!watched)}>
              <Icon name="check" /> {watched ? "Watched" : "Mark watched"}
            </button>
            <button className="btn ghost icon-only" title="Fix match (search TMDB)"><Icon name="edit" /></button>
          </div>

          <dl className="tech">
            <div><dt>Playback</dt><dd><PlayBadge item={item} /></dd></div>
            <div><dt>Video</dt><dd>{m.video} · {m.resolution}{m.hdr ? ` · ${m.hdr}` : ""}</dd></div>
            <div><dt>Audio</dt><dd>{m.audio}</dd></div>
            <div><dt>Container</dt><dd>{m.container}{m.size ? ` · ${m.size}` : ""}</dd></div>
            <div><dt>Match</dt><dd>TMDB / IMDb ids appear here once matched</dd></div>
          </dl>
          <p className="tech-note">
            {method === "Direct Play" && "Plays as-is in the browser. No server work."}
            {method === "Direct Stream" && "Video is browser-friendly. The server repackages it (and converts the audio if needed) with no quality loss."}
            {method === "Transcode" && `${m.video} isn't playable in most browsers. The server converts it to H.264 on the GPU (NVENC / VAAPI / QSV).`}
          </p>
        </div>
      </div>

      {item.type === "show" && (
        <section className="seasons">
          <div className="season-tabs">
            {item.seasons!.map((_, k) => (
              <button key={k} className={`chip ${season === k + 1 ? "on" : ""}`} onClick={() => setSeason(k + 1)}>
                Season {k + 1}
              </button>
            ))}
          </div>
          <ol className="episodes">
            {eps.map((e) => (
              <li key={e.episode}>
                <Link to={`/play/${item.id}?s=${e.season}&e=${e.episode}`} className="episode">
                  <span className="ep-num">{e.episode}</span>
                  <div className="ep-thumb"><Backdrop item={item} className="ep-img" /><span className="round-btn"><Icon name="play" size={16} /></span></div>
                  <div className="ep-text">
                    <div className="ep-title">{e.title} <span className="muted">· {sxe(e.season, e.episode)}</span></div>
                    <p>{e.overview}</p>
                  </div>
                  <span className="ep-time">{e.runtime}m</span>
                </Link>
              </li>
            ))}
          </ol>
        </section>
      )}

      {similar.length > 0 && (
        <div className="rows">
          <Row title="More like this">{similar.map((i) => <PosterCard key={i.id} item={i} />)}</Row>
        </div>
      )}
    </div>
  );
}
