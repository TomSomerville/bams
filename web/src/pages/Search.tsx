import { useSearchParams } from "react-router-dom";
import { items } from "../data";
import { PosterCard } from "../components/Cards";

export default function Search() {
  const [params] = useSearchParams();
  const q = (params.get("q") ?? "").toLowerCase();
  const hits = items.filter(
    (i) => i.title.toLowerCase().includes(q) || i.genres.some((g) => g.toLowerCase().includes(q)) || String(i.year) === q,
  );
  return (
    <div className="page">
      <div className="page-head">
        <h1>Results for “{params.get("q")}”</h1>
        <span className="count">{hits.length}</span>
      </div>
      {hits.length ? (
        <div className="grid">{hits.map((i) => <PosterCard key={i.id} item={i} />)}</div>
      ) : (
        <p className="muted">Nothing in your libraries matches that.</p>
      )}
    </div>
  );
}
