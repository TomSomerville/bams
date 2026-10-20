import { useEffect, useRef, useState, type MouseEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { ContinueItem, ItemSummary, PlayMethod, ShownItem, WatchlistItem } from "../api";
import { useAuth } from "../auth";
import { listedLook } from "../everywhere";
import { fmtRuntime, PLAY_LABEL, plural, subLabel, sxe } from "../format";
import { listName } from "../homeRows";
import { useMusic } from "../music";
import { callFor, useItemServer } from "../servers";
import { Poster } from "./Art";
import Icon from "./Icon";

/** How far through something the user is: 0..1, or null when there's nothing to show. */
export function progressOf(item: ItemSummary): number | null {
  const p = item.progress;
  if (!p || p.watched || !p.position || !p.duration) return null;
  return Math.min(1, p.position / p.duration);
}

/** Watched / unwatched markers on a poster: a tick when it's all watched, the number of unwatched episodes of a
 *  show that's been started, and a progress bar for a movie stopped part-way. */
export function WatchMarks({ item }: { item: ItemSummary }) {
  const all = item.kind === "movie" || item.kind === "episode" ? item.progress?.watched : !!item.episodes && item.unwatched === 0;
  const left = item.kind === "show" && item.episodes && item.unwatched && item.unwatched < item.episodes ? item.unwatched : 0;
  const pct = progressOf(item);
  return (
    <>
      {all && <span className="corner-badge watched" title="Watched"><Icon name="check" size={12} /></span>}
      {left > 0 && <span className="corner-badge count" title={`${left} unwatched episode${left === 1 ? "" : "s"}`}>{left}</span>}
      {pct !== null && <div className="progress"><div style={{ width: `${pct * 100}%` }} /></div>}
    </>
  );
}

export function PosterCard({ item }: { item: ItemSummary }) {
  const { to } = useItemServer(item);
  return (
    <Link to={to(`/title/${item.id}`)} className="poster-card">
      <div className="poster-frame">
        <Poster src={item.poster} title={item.title} />
        {item.match_status === "unmatched" && <span className="corner-badge warn" title="Not matched on TMDB">?</span>}
        <WatchMarks item={item} />
        <div className="poster-hover">
          <span className="round-btn"><Icon name="info" size={18} /></span>
          <ListToggle item={item} />
        </div>
      </div>
      <div className="poster-title">{item.title}</div>
      <div className="poster-sub">{subLabel(item)}</div>
    </Link>
  );
}

/** Puts an item on the user's watch list or takes it off, on the item's own server (each server keeps its part of
 *  the list; the watch list page and Home put them together). `big`: a labelled button (title pages); else a round
 *  icon (posters, episode rows: `small`). `onChange` once the server has done it. Nothing for music, or for a server
 *  too old to have watch lists (no `watchlist` on its items). */
export function ListToggle({ item, big, small, what = "", onChange }: {
  item: ItemSummary; big?: boolean; small?: boolean; what?: string; onChange?: (on: boolean) => void;
}) {
  const { rid } = useItemServer(item);
  const { prefs } = useAuth();
  const [on, setOn] = useState(!!item.watchlist);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => setOn(!!item.watchlist), [item.id, item.watchlist]);
  if (item.watchlist === undefined) return null;
  const name = listName(prefs.watchlist_name);
  const label = err ?? (on ? `Remove${what} from ${name}` : `Add${what} to ${name}`);
  const toggle = (e: MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (busy) return;
    setBusy(true);
    setErr(null);
    const call = callFor(rid);
    const path = `/api/watchlist/${item.id}`;
    (on ? call.del(path) : call.put(path, {}))
      .then(() => { setOn(!on); onChange?.(!on); })
      .catch((x: Error) => setErr(`Couldn't change ${name}: ${x.message}`))
      .finally(() => setBusy(false));
  };
  if (big) {
    return (
      <button className={`btn ghost list-btn ${on ? "on" : ""}`} onClick={toggle} disabled={busy} title={label} aria-pressed={on}>
        <Icon name={on ? "check" : "plus"} /> {name}{what && ` (${what.trim()})`}
      </button>
    );
  }
  return (
    <button className={small ? `icon-btn subtle list-toggle-small ${on ? "on" : ""}` : `round-btn list-toggle ${on ? "on" : ""}`}
      onClick={toggle} disabled={busy} title={label} aria-label={label} aria-pressed={on}>
      <Icon name={on ? "bookmarkOn" : "bookmark"} size={small ? 16 : 18} />
    </button>
  );
}

/** Where a watch list entry opens: a movie's/show's page, a season's tab on its show's page, an episode picked out
 *  on its season's tab. */
export function listedPage(i: ShownItem): string {
  if (i.kind === "episode" && i.show && i.season_id) return `/title/${i.show.id}?season=${i.season_id}&episode=${i.id}`;
  if (i.kind === "season" && i.show) return `/title/${i.show.id}?season=${i.id}`;
  return `/title/${i.id}`;
}

/** An entry of the watch list: a poster (an episode or a season under its show's name, everywhere.ts listedLook).
 *  On hover, movies and episodes can be played straight away, and the bookmark takes it off (`onRemoved`). */
export function ListedCard({ item, onRemoved }: { item: ShownItem; onRemoved?: () => void }) {
  const { to } = useItemServer(item);
  const navigate = useNavigate();
  const look = listedLook(item);
  const playable = item.kind === "movie" || item.kind === "episode";
  return (
    <Link to={to(listedPage(item))} className="poster-card">
      <div className="poster-frame">
        <Poster src={look.poster} title={look.title} />
        {item.match_status === "unmatched" && <span className="corner-badge warn" title="Not matched on TMDB">?</span>}
        <WatchMarks item={item} />
        <div className="poster-hover">
          {playable ? (
            <button className="round-btn" aria-label={`Play ${look.title}${look.sub ? ` ${look.sub}` : ""}`}
              onClick={(e) => { e.preventDefault(); navigate(to(`/play/${item.id}`)); }}>
              <Icon name="play" size={18} />
            </button>
          ) : <span className="round-btn"><Icon name="info" size={18} /></span>}
          <ListToggle item={item} onChange={(on) => { if (!on) onRemoved?.(); }} />
        </div>
      </div>
      <div className="poster-title">{look.title}</div>
      <div className="poster-sub">{look.sub ?? subLabel(item)}</div>
    </Link>
  );
}

const LONG_PRESS = 500;  // ms held before a press counts as a long press

/** A long press (touch or mouse, held still) or a right-click on an element calls `onLong`; the click that ends a
 *  long press is swallowed so it doesn't also open the link under it. Presses inside `ignore` don't count. */
function useLongPress(onLong: () => void, ignore: string) {
  const timer = useRef(0);
  const from = useRef<{ x: number; y: number } | null>(null);
  const fired = useRef(false);
  const stop = () => {
    window.clearTimeout(timer.current);
    from.current = null;
  };
  const inside = (e: React.SyntheticEvent) => !!(e.target as Element).closest(ignore);
  return {
    onPointerDown: (e: React.PointerEvent) => {
      fired.current = false;
      if (e.button !== 0 || inside(e)) return;
      from.current = { x: e.clientX, y: e.clientY };
      timer.current = window.setTimeout(() => {
        fired.current = true;
        from.current = null;
        onLong();
      }, LONG_PRESS);
    },
    onPointerMove: (e: React.PointerEvent) => {
      const f = from.current;
      if (f && Math.hypot(e.clientX - f.x, e.clientY - f.y) > 10) stop();  // scrolling the row, not holding
    },
    onPointerUp: stop,
    onPointerCancel: stop,
    onPointerLeave: stop,
    onContextMenu: (e: React.MouseEvent) => {
      if (inside(e)) return;
      e.preventDefault();
      if (from.current) fired.current = true;  // a touch browser's own long press: swallow its click too
      stop();
      onLong();
    },
    onClickCapture: (e: React.MouseEvent) => {
      if (!fired.current) return;
      fired.current = false;
      e.preventDefault();
      e.stopPropagation();
    },
  };
}

/** Continue Watching: a wide still with the progress bar. The picture plays straight away; the show's name opens
 *  the show, the episode line opens its season (the show page on that season's tab). A long press (or right-click)
 *  offers to take it out of the row: the movie, or the whole show, until it's watched again (`onRemoved` once the
 *  server has done it). */
export function ContinueCard({ item, onRemoved }: { item: ContinueItem; onRemoved?: () => void }) {
  const { to, rid } = useItemServer(item);
  const [menu, setMenu] = useState(false);
  const press = useLongPress(() => setMenu(true), ".continue-menu");
  const pct = progressOf(item);
  const img = item.still || item.show?.backdrop || item.backdrop || item.show?.poster || item.poster;
  const title = item.show?.title ?? item.title;
  const left = item.progress?.duration && item.progress.position
    ? Math.max(1, Math.round((item.progress.duration - item.progress.position) / 60)) : null;
  const sub = [
    item.kind === "episode" ? `${sxe(item.season_number!, item.episode_number)} · ${item.title}` : null,
    item.reason === "next" ? "Next episode" : left ? `${fmtRuntime(left)} left` : null,
  ].filter(Boolean).join(" · ");
  const page = to(item.show ? `/title/${item.show.id}` : `/title/${item.id}`);
  const seasonPage = item.season_id ? `${page}?season=${item.season_id}` : page;
  return (
    <div className="continue-card" {...(onRemoved ? press : {})}>
      <Link to={to(`/play/${item.id}`)} className="continue-frame" aria-label={`Play ${title}${item.show ? ` ${item.title}` : ""}`}>
        {img ? <img className="continue-img" src={img} alt="" loading="lazy" draggable={false} /> : <Poster src={null} title={title} />}
        <div className="continue-play"><span className="round-btn"><Icon name="play" size={18} /></span></div>
        {pct !== null && <div className="progress"><div style={{ width: `${pct * 100}%` }} /></div>}
      </Link>
      <Link to={page} className="poster-title">{title}</Link>
      <Link to={seasonPage} className="poster-sub">{sub}</Link>
      {menu && onRemoved && (
        <ContinueMenu path={`/api/continue/${item.id}`} rid={rid} onClose={() => setMenu(false)} onRemoved={onRemoved} />
      )}
    </div>
  );
}

/** Over a Continue Watching card after a long press: take it out of the row, or not. Escape or a press anywhere
 *  else closes it. */
function ContinueMenu({ path, rid, onClose, onRemoved }: {
  path: string; rid: number | null; onClose: () => void; onRemoved: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    ref.current?.querySelector("button")?.focus();
    const away = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) close.current();
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") close.current();
    };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", esc);
    };
  }, []);
  const remove = async () => {
    setBusy(true);
    setErr(null);
    try {
      await callFor(rid).del(path);
      onRemoved();
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  };
  return (
    <div className="continue-menu" ref={ref}>
      {err && <p className="continue-menu-err">{err}</p>}
      <button className="btn small primary" onClick={() => void remove()} disabled={busy}>
        <Icon name="close" size={14} /> Remove from Continue Watching
      </button>
      <button className="btn small ghost" onClick={onClose}>Cancel</button>
    </div>
  );
}

/** Square album cover; the play button on hover starts the album without opening it. */
export function AlbumCard({ item, showArtist = true }: { item: ItemSummary; showArtist?: boolean }) {
  const music = useMusic();
  const { to, rid } = useItemServer(item);
  return (
    <Link to={to(`/title/${item.id}`)} className="poster-card album-card">
      <div className="poster-frame square">
        <Poster src={item.poster} title={item.title} />
        <div className="poster-hover">
          <button className="round-btn" aria-label={`Play ${item.title}`}
            onClick={(e) => { e.preventDefault(); music.playItem(item.id, { rid }); }}>
            <Icon name="play" size={18} />
          </button>
        </div>
      </div>
      <div className="poster-title">{item.title}</div>
      <div className="poster-sub">{[showArtist ? item.parent_title : null, item.year].filter(Boolean).join(" · ")}</div>
    </Link>
  );
}

export function ArtistCard({ item }: { item: ItemSummary }) {
  const { to } = useItemServer(item);
  return (
    <Link to={to(`/title/${item.id}`)} className="poster-card artist-card">
      <div className="poster-frame round"><Poster src={item.poster} title={item.title} /></div>
      <div className="poster-title">{item.title}</div>
      <div className="poster-sub">{plural(item.child_count ?? 0, "album")}</div>
    </Link>
  );
}

/** Any item in a grid or row: the right card for its kind. */
export function ItemCard({ item }: { item: ItemSummary }) {
  if (item.kind === "album") return <AlbumCard item={item} />;
  if (item.kind === "artist") return <ArtistCard item={item} />;
  return <PosterCard item={item} />;
}

export function PlayBadge({ method }: { method: PlayMethod }) {
  const cls = method === "direct_play" ? "ok" : method === "direct_stream" ? "mid" : "hot";
  return <span className={`play-badge ${cls}`} title="How BAMS would play this in a browser">{PLAY_LABEL[method]}</span>;
}
