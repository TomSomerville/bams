import { useEffect, useState, type MouseEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api, MUSIC_KINDS, type FileInfo, type ItemDetail, type ItemSummary } from "../api";
import { Backdrop, Poster } from "../components/Art";
import { PlayBadge, PosterCard, progressOf } from "../components/Cards";
import FixMatch from "../components/FixMatch";
import Icon from "../components/Icon";
import Row from "../components/Row";
import { fmtClock, fmtRuntime, fmtSize, seasonsLabel, sxe } from "../format";
import { useApi } from "../useApi";
import { MusicDetail } from "./Music";

function TechInfo({ f }: { f: FileInfo }) {
  const p = f.probe;
  const rel = f.release ?? {};
  const video = p?.video
    ? [p.video.codec, p.video.resolution, p.video.hdr, p.video.bit_depth === 10 ? "10-bit" : null].filter(Boolean).join(" · ")
    : [rel.video_codec, rel.resolution].filter(Boolean).join(" · ") || "unknown";
  const audio = p?.audio.length
    ? p.audio.map((a) => [a.codec, a.channels ? `${a.channels}ch` : null, a.language].filter(Boolean).join(" ")).join(", ")
    : [rel.audio_codec, rel.audio_channels].filter(Boolean).join(" ") || "unknown";
  const subs = f.subtitles?.length ? f.subtitles.map((s) => s.label).join(", ")
    : p?.subtitles.length ? p.subtitles.map((s) => s.language ?? s.codec).join(", ") : null;
  return (
    <>
      <dl className="tech">
        <div><dt>Playback</dt><dd><PlayBadge method={f.playback.method} /></dd></div>
        <div><dt>Video</dt><dd>{video}</dd></div>
        <div><dt>Audio</dt><dd>{audio}</dd></div>
        <div><dt>File</dt><dd>{p?.container ?? f.path.split(".").pop()?.toUpperCase()} · {fmtSize(f.size)}</dd></div>
        {subs && <div><dt>Subtitles</dt><dd>{subs}</dd></div>}
      </dl>
      <p className="tech-note">
        {f.playback.source === "filename" && "Codec info from the file name (no ffprobe data yet). "}
        {f.playback.method === "direct_play" && "Plays as-is in the browser."}
        {f.playback.mode === "remux" && `Browsers can't decode ${f.playback.audio_codec} audio, so the server converts the audio to AAC while streaming. The video is passed through untouched.`}
        {f.playback.method === "direct_stream" && f.playback.mode === "file" && "Plays as-is in Chrome and Edge."}
        {f.playback.method === "transcode" && f.playback.mode === "transcode" &&
          `Browsers can't decode ${f.playback.video_codec ?? "this"} video, so the server converts it to H.264 while streaming.`}
        {f.playback.method === "transcode" && f.playback.mode === "file" &&
          `Browsers can't decode ${f.playback.video_codec ?? "this"} video, and the server has no FFmpeg to convert it. Download it instead.`}
        {f.playback.method !== "transcode" && f.playback.transcode_url && ["HEVC", "AV1", "VP9"].includes(f.playback.video_codec ?? "") &&
          ` Browsers that can't decode ${f.playback.video_codec} get a version converted to H.264.`}
      </p>
    </>
  );
}

/** Mark a movie/episode, or all of a season/show, watched or not; `done` reloads what shows it. */
function WatchedButton({ item, watched, done, small }: { item: ItemSummary; watched: boolean; done: () => void; small?: boolean }) {
  const label = watched ? "Mark unwatched" : "Mark watched";
  const what = item.kind === "season" ? " (season)" : item.kind === "show" ? " (all episodes)" : "";
  const toggle = (e: MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    api.put(`/api/items/${item.id}/watched`, { watched: !watched }).then(done).catch(() => {});
  };
  return small ? (
    <button className={`icon-btn subtle watch-toggle ${watched ? "on" : ""}`} onClick={toggle} title={label} aria-label={label}>
      <Icon name={watched ? "check" : "eye"} size={16} />
    </button>
  ) : (
    <button className="btn ghost" onClick={toggle}><Icon name={watched ? "eyeOff" : "check"} /> {label}{what}</button>
  );
}

function Episodes({ season, onChange }: { season: ItemSummary; onChange: () => void }) {
  const { data, reload } = useApi<ItemDetail>(`/api/items/${season.id}`);
  if (!data) return <p className="muted">Loading episodes…</p>;
  const changed = () => { reload(); onChange(); };
  return (
    <>
      <div className="season-bar">
        {data.overview && <p className="muted season-overview">{data.overview}</p>}
        {!!data.episodes && <WatchedButton item={data} watched={data.unwatched === 0} done={changed} />}
      </div>
      <ol className="episodes">
        {data.children.map((e) => (
          <li key={e.id}>
            <Link to={`/play/${e.id}`} className={`episode ${e.progress?.watched ? "seen" : ""}`}>
              <span className="ep-num">{e.episode_number ?? "·"}</span>
              <div className="ep-thumb">
                {e.still ? <img className="ep-img" src={e.still} alt="" loading="lazy" />
                  : <Backdrop src={null} poster={data.poster} title={e.title} className="ep-img" />}
                <span className="round-btn"><Icon name="play" size={16} /></span>
                {progressOf(e) !== null && <div className="progress"><div style={{ width: `${progressOf(e)! * 100}%` }} /></div>}
              </div>
              <div className="ep-text">
                <div className="ep-title">{e.title} <span className="muted">· {sxe(e.season_number!, e.episode_number)}</span></div>
                {e.overview && <p>{e.overview}</p>}
              </div>
              <span className="ep-time">{[e.air_date?.slice(0, 4), e.runtime ? `${e.runtime}m` : null].filter(Boolean).join(" · ")}</span>
              <WatchedButton small item={e} watched={!!e.progress?.watched} done={reload} />
            </Link>
          </li>
        ))}
      </ol>
    </>
  );
}

export default function Detail() {
  const { id } = useParams();
  const { data: item, error, reload } = useApi<ItemDetail>(`/api/items/${id}`);
  const [seasonIdx, setSeasonIdx] = useState<number | null>(null);
  const [fixing, setFixing] = useState(false);
  const isMusic = !!item && MUSIC_KINDS.includes(item.kind);
  const genre = isMusic ? undefined : item?.genres[0];
  const { data: similar } = useApi<ItemSummary[]>(genre ? `/api/items?genre=${encodeURIComponent(genre)}&limit=20` : null);

  // default season: the first real season (not Specials) once the item loads
  useEffect(() => {
    if (!item) return;
    const first = item.children.findIndex((s) => (s.season_number ?? 0) > 0);
    setSeasonIdx(first >= 0 ? first : 0);
  }, [item?.id]); // eslint-disable-line react-hooks/exhaustive-deps -- not on reloads (marking watched)

  if (error) return <div className="page"><p className="key-msg bad">{error}</p></div>;
  if (!item) return <div className="page muted">Loading…</div>;
  if (isMusic) return <MusicDetail key={item.id} item={item} reload={reload} />;

  const season = item.kind === "show" && seasonIdx !== null ? item.children[seasonIdx] : null;
  const file = item.files.find((f) => f.available) ?? item.files[0];
  const more = (similar ?? []).filter((i) => i.id !== item.id);
  const resumeAt = item.kind === "movie" && item.progress && !item.progress.watched ? item.progress.position : 0;

  return (
    <div className="detail">
      <div className="detail-bg">
        <Backdrop src={item.backdrop} poster={item.poster} title={item.title} className="detail-img" />
        <div className="detail-shade" />
      </div>

      <div className="detail-body">
        <div className="detail-poster"><Poster src={item.poster} title={item.title} /></div>
        <div className="detail-info">
          <h1>{item.title}</h1>
          <div className="meta">
            {item.rating ? <span className="score">★ {item.rating.toFixed(1)}</span> : null}
            {item.year && <span>{item.year}</span>}
            <span>{item.kind === "show" ? seasonsLabel(item) : fmtRuntime(item.runtime)}</span>
            {item.genres.map((g) => <span key={g} className="tag">{g}</span>)}
          </div>
          {item.tagline && <p className="tagline">{item.tagline}</p>}
          {item.overview ? <p className="overview">{item.overview}</p>
            : item.match_status !== "matched" && item.match_status !== "manual" && (
              <p className="key-msg warn">
                {item.match_status === "pending" ? "Not looked up on TMDB yet (it happens after the next scan)."
                  : "BAMS couldn't confidently identify this on TMDB. Use Fix match to pick the right title."}
              </p>
            )}
          <div className="actions">
            {item.kind === "movie" && file && (
              <Link to={`/play/${item.id}`} className="btn primary">
                <Icon name="play" /> {resumeAt ? `Resume from ${fmtClock(resumeAt)}` : "Play"}
              </Link>
            )}
            {resumeAt > 0 && <Link to={`/play/${item.id}?start=0`} className="btn ghost"><Icon name="refresh" /> Start over</Link>}
            {item.kind === "movie" && <WatchedButton item={item} watched={!!item.progress?.watched} done={reload} />}
            {item.kind === "show" && !!item.episodes && <WatchedButton item={item} watched={item.unwatched === 0} done={reload} />}
            {item.kind === "movie" && file && (
              <a className="btn ghost" href={file.download_url} download><Icon name="download" /> Download</a>
            )}
            <button className="btn ghost" onClick={() => setFixing(true)}><Icon name="edit" /> Fix match</button>
            {item.ids.imdb && (
              <a className="btn ghost" href={`https://www.imdb.com/title/${item.ids.imdb}/`} target="_blank" rel="noreferrer">IMDb</a>
            )}
          </div>
          {item.kind === "movie" && file && <TechInfo f={file} />}
        </div>
      </div>

      {item.kind === "show" && item.children.length > 0 && (
        <section className="seasons">
          <div className="season-tabs">
            {item.children.map((s, k) => (
              <button key={s.id} className={`chip ${seasonIdx === k ? "on" : ""}`} onClick={() => setSeasonIdx(k)}>
                {s.title} <span className="chip-count">{s.unwatched === 0 && s.episodes ? "✓" : s.child_count}</span>
              </button>
            ))}
          </div>
          {season && <Episodes key={season.id} season={season} onChange={reload} />}
        </section>
      )}

      {more.length > 0 && (
        <div className="rows">
          <Row title="More like this">{more.map((i) => <PosterCard key={i.id} item={i} />)}</Row>
        </div>
      )}
      {fixing && <FixMatch item={item} onClose={() => { setFixing(false); reload(); }} />}
    </div>
  );
}
