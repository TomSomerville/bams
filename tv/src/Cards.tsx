import { mediaFor, type ItemSummary } from "./api";
import { progressOf } from "./format";

/** Poster (2:3) for shows and movies. `rid`: the item is from another of this TV's servers (api.ts). */
export function Poster({ item, fid, onPress, onFocus, autoFocus, rid }: {
  item: ItemSummary; fid: string; onPress: () => void; onFocus?: () => void; autoFocus?: boolean; rid?: number;
}) {
  const p = progressOf(item);
  const src = mediaFor(rid)(item.poster);
  const watched = item.progress?.watched || (item.kind === "show" && item.episodes && item.unwatched === 0);
  return (
    <button className="card poster" data-fid={fid} onClick={onPress} onFocus={onFocus} data-autofocus={autoFocus || undefined}>
      {src ? <img src={src} alt="" loading="lazy" /> : <div className="no-art"><span>{item.title}</span></div>}
      {!!item.unwatched && item.kind === "show" && <span className="badge">{item.unwatched}</span>}
      {watched && <span className="badge done">✓</span>}
      {p !== null && <div className="bar"><div style={{ width: `${p * 100}%` }} /></div>}
      <div className="card-title">{item.title}</div>
    </button>
  );
}

/** Wide card (16:9): Continue Watching, episodes. */
export function Wide({ img, title, sub, progress, fid, onPress, onFocus, rid }: {
  img: string | null | undefined; title: string; sub?: string | null; progress?: number | null;
  fid: string; onPress: () => void; onFocus?: () => void; rid?: number;
}) {
  const src = mediaFor(rid)(img);
  return (
    <button className="card wide" data-fid={fid} onClick={onPress} onFocus={onFocus}>
      {src ? <img src={src} alt="" loading="lazy" /> : <div className="no-art"><span>{title}</span></div>}
      {progress !== null && progress !== undefined && <div className="bar"><div style={{ width: `${progress * 100}%` }} /></div>}
      <div className="wide-text">
        <div className="wide-title">{title}</div>
        {sub && <div className="wide-sub">{sub}</div>}
      </div>
    </button>
  );
}

/** A labelled horizontal shelf. */
export function Shelf({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="shelf">
      <h2>{title}</h2>
      <div className="shelf-row" data-row>{children}</div>
    </section>
  );
}

/** Square card for music: an album cover, an artist (round), a playlist; the name is always shown under it. */
export function Square({ img, title, sub, fid, onPress, onFocus, rid, round }: {
  img: string | null | undefined; title: string; sub?: string | null; fid: string; onPress: () => void;
  onFocus?: () => void; rid?: number; round?: boolean;
}) {
  const src = mediaFor(rid)(img);
  return (
    <button className={`card square ${round ? "round-art" : ""}`} data-fid={fid} onClick={onPress} onFocus={onFocus}>
      <div className="square-art">{src ? <img src={src} alt="" loading="lazy" /> : <div className="no-art"><span>{title}</span></div>}</div>
      <div className="square-title">{title}</div>
      {sub && <div className="square-sub">{sub}</div>}
    </button>
  );
}
