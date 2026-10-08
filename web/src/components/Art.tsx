import { useState } from "react";
import type { Item } from "../data";
import { backdropUrl, posterUrl } from "../data";

// Placeholder gradient (in brand colors) shown while art is missing — the same fallback
// the real app will use for unmatched items.
const HUES = ["#4257cd", "#844cbd", "#c34b73", "#f78737", "#2f9fd0"];
function fallbackBg(id: string) {
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  const a = HUES[h % HUES.length];
  const b = HUES[(h >> 3) % HUES.length];
  return `linear-gradient(150deg, ${a}, ${b} 70%, #0f1216)`;
}

export function Poster({ item, className = "" }: { item: Item; className?: string }) {
  const [failed, setFailed] = useState(false);
  return failed ? (
    <div className={`art-fallback ${className}`} style={{ background: fallbackBg(item.id) }}>
      <span>{item.title}</span>
    </div>
  ) : (
    <img className={className} src={posterUrl(item)} alt={item.title} loading="lazy" onError={() => setFailed(true)} />
  );
}

/** Backdrop if the item has one, otherwise its poster stretched and blurred. */
export function Backdrop({ item, className = "" }: { item: Item; className?: string }) {
  const [failed, setFailed] = useState(false);
  const src = backdropUrl(item);
  if (src && !failed) return <img className={className} src={src} alt="" onError={() => setFailed(true)} />;
  return (
    <div className={`${className} backdrop-blur`} style={{ background: fallbackBg(item.id) }}>
      <div className="bb-fill"><Poster item={item} /></div>
      <div className="bb-poster"><Poster item={item} /></div>
    </div>
  );
}
