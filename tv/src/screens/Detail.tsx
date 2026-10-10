import { useEffect, useState } from "react";
import { api, media, type ContinueItem, type ItemDetail, type ItemSummary } from "../api";
import { useFocusOnReady, useNav } from "../App";
import Icon from "../Icon";
import { clock, metaLine, progressOf, runtime, sxe } from "../format";
import { pickAudio, pickFile, plan } from "../plan";

/** A movie, show, season or episode: art, text, Play / Resume, and for shows the seasons and their episodes. */
export default function Detail({ id }: { id: number }) {
  const nav = useNav();
  const [item, setItem] = useState<ItemDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [next, setNext] = useState<ContinueItem | null>(null);
  const [season, setSeason] = useState<number | null>(null);
  const [episodes, setEpisodes] = useState<ItemDetail | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    api.get<ItemDetail>(`/api/items/${id}`).then((d) => {
      setItem(d);
      if (d.kind === "show") {
        const saved = Number(sessionStorage.getItem(`bams.season.${id}`));
        const ids = d.children.map((c) => c.id);
        setSeason((s) => s ?? (ids.includes(saved) ? saved : d.children.find((c) => (c.unwatched ?? 0) > 0)?.id ?? ids[0] ?? null));
      }
    }).catch((e) => setErr((e as Error).message));
    api.get<ContinueItem[]>("/api/continue?limit=100")
      .then((c) => setNext(c.find((x) => x.show?.id === id || x.season_id === id) ?? null)).catch(() => undefined);
  }, [id, reload]);

  // a show's season (or a season's own page): its episodes
  useEffect(() => {
    if (item?.kind === "season") return setEpisodes(item);
    if (season === null) return;
    sessionStorage.setItem(`bams.season.${id}`, String(season));
    api.get<ItemDetail>(`/api/items/${season}`).then(setEpisodes).catch((e) => setErr((e as Error).message));
  }, [item, season, id]);

  useFocusOnReady(!!item && (item.kind === "movie" || item.kind === "episode" || !!episodes));

  if (err) return <div className="page"><p className="error big">{err}</p></div>;
  if (!item) return <div className="page"><div className="spinner" /></div>;

  const playable = item.kind === "movie" || item.kind === "episode";
  const show = item.kind === "episode" ? item.ancestors.find((a) => a.kind === "show") : item.kind === "season" ? item.ancestors[0] : null;
  const back = item.backdrop || show?.backdrop || item.still;
  const pos = item.progress?.position ?? 0;
  const file = playable ? pickFile(item.files) : null;
  const how = file ? plan(file, pickAudio(file), null) : null;

  const markWatched = async (target: ItemSummary, watched: boolean) => {
    await api.put(`/api/items/${target.id}/watched`, { watched }).catch(() => undefined);
    setReload((n) => n + 1);
    if (season) api.get<ItemDetail>(`/api/items/${season}`).then(setEpisodes).catch(() => undefined);
  };

  return (
    <div className="detail">
      {back && <img className="detail-art" src={media(back) ?? undefined} alt="" />}
      <div className="detail-shade" />
      <div className="detail-body">
        <div className="detail-top">
          {item.poster && item.kind !== "episode" && <img className="detail-poster" src={media(item.poster) ?? undefined} alt="" />}
          <div className="detail-text">
            {show && <div className="eyebrow">{show.title}{item.kind === "episode" ? ` · ${sxe(item)}` : ""}</div>}
            <h1>{item.title}</h1>
            <div className="meta">{metaLine(item)}{item.air_date ? `  ·  ${item.air_date}` : ""}</div>
            {item.tagline && <p className="tagline">{item.tagline}</p>}
            {item.overview && <p className="overview clamp4">{item.overview}</p>}
            {playable && file?.probe && (
              <div className="tech">
                {[file.probe.video?.resolution, file.probe.video?.hdr, file.probe.video?.codec,
                  file.probe.audio[0] && `${file.probe.audio[0].codec}${file.probe.audio[0].channels === 6 ? " 5.1" : file.probe.audio[0].channels === 8 ? " 7.1" : ""}`,
                  how && (how.mode === "direct" ? "Plays as-is" : how.mode === "remux" ? `Sound converted (${how.why})` : `Converted (${how.why})`)]
                  .filter(Boolean).join("  ·  ")}
              </div>
            )}
            {playable && !file && <p className="error">No file of this is available right now (drive offline or moved).</p>}
            <div className="button-row">
              {playable && file && pos > 0 && (
                <button className="btn primary" data-autofocus data-fid="resume" onClick={() => nav.push({ name: "player", id, resume: true })}>
                  <Icon name="play" size={30} /> Resume from {clock(pos)}
                </button>
              )}
              {playable && file && (
                <button className={`btn ${pos > 0 ? "" : "primary"}`} data-autofocus={pos > 0 ? undefined : true} data-fid="play"
                  onClick={() => nav.push({ name: "player", id, resume: false })}>
                  <Icon name={pos > 0 ? "restart" : "play"} size={30} /> {pos > 0 ? "From the start" : "Play"}
                </button>
              )}
              {!playable && next && (
                <button className="btn primary" data-autofocus data-fid="next" onClick={() => nav.push({ name: "player", id: next.id, resume: true })}>
                  <Icon name="play" size={30} /> {next.reason === "resume" ? "Resume" : "Play"} {sxe(next)}
                </button>
              )}
              {(playable || item.kind === "show" || item.kind === "season") && (
                <button className="btn" data-fid="watched" onClick={() => void markWatched(item, !(playable ? item.progress?.watched : item.unwatched === 0))}>
                  <Icon name={(playable ? item.progress?.watched : item.unwatched === 0) ? "eye" : "check"} size={30} />
                  {(playable ? item.progress?.watched : item.unwatched === 0) ? "Mark unwatched" : "Mark watched"}
                </button>
              )}
            </div>
          </div>
        </div>

        {item.kind === "show" && item.children.length > 1 && (
          <div className="chips seasons" data-row>
            {item.children.map((s) => (
              <button key={s.id} data-fid={`season-${s.id}`} className={`chip ${season === s.id ? "on" : ""}`} onClick={() => setSeason(s.id)}>
                {s.title}{s.unwatched ? ` (${s.unwatched})` : ""}
              </button>
            ))}
          </div>
        )}
        {episodes && (item.kind === "show" || item.kind === "season") && (
          <div className="episodes">
            {episodes.children.map((e, n) => {
              const p = progressOf(e);
              return (
                <button key={e.id} className="episode" data-fid={`ep-${e.id}`} data-autofocus={(!next && n === 0) || undefined} onClick={() => nav.push({ name: "player", id: e.id, resume: true })}>
                  <div className="ep-still">
                    {e.still ? <img src={media(e.still) ?? undefined} alt="" loading="lazy" /> : <div className="no-art" />}
                    {p !== null && <div className="bar"><div style={{ width: `${p * 100}%` }} /></div>}
                    {e.progress?.watched && <span className="badge done">✓</span>}
                  </div>
                  <div className="ep-text">
                    <div className="ep-title">{e.episode_number ? `${e.episode_number}. ` : ""}{e.title}</div>
                    <div className="meta">{[e.air_date, runtime(e.runtime)].filter(Boolean).join("  ·  ")}</div>
                    {e.overview && <p className="clamp2">{e.overview}</p>}
                  </div>
                </button>
              );
            })}
            {!episodes.children.length && <p className="muted">No episodes in this season.</p>}
          </div>
        )}
      </div>
    </div>
  );
}
