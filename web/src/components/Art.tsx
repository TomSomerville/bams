import { useState } from "react";

// Shown when an item has no artwork (not matched on TMDB yet, or TMDB has none):
// a brand-colour gradient with the title, picked consistently per title.
const HUES = ["#4257cd", "#844cbd", "#c34b73", "#f78737", "#2f9fd0"];
function fallbackBg(seed: string) {
  let h = 0;
  for (const c of seed) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return `linear-gradient(150deg, ${HUES[h % HUES.length]}, ${HUES[(h >> 3) % HUES.length]} 70%, #0f1216)`;
}

type ArtProps = { src: string | null | undefined; title: string; className?: string };

export function Poster({ src, title, className = "" }: ArtProps) {
  const [failed, setFailed] = useState(false);
  return src && !failed ? (
    <img className={className} src={src} alt={title} loading="lazy" onError={() => setFailed(true)} />
  ) : (
    <div className={`art-fallback ${className}`} style={{ background: fallbackBg(title) }}><span>{title}</span></div>
  );
}

/** Wide art: the backdrop if there is one, else the poster blurred behind a sharp copy of it. */
export function Backdrop({ src, poster, title, className = "" }: ArtProps & { poster?: string | null }) {
  const [failed, setFailed] = useState(false);
  if (src && !failed) return <img className={className} src={src} alt="" onError={() => setFailed(true)} />;
  return (
    <div className={`${className} backdrop-blur`} style={{ background: fallbackBg(title) }}>
      {poster && <div className="bb-fill"><Poster src={poster} title={title} /></div>}
      {poster && <div className="bb-poster"><Poster src={poster} title={title} /></div>}
    </div>
  );
}
