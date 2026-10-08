import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import Icon from "./Icon";

export default function TopBar() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 8);
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);

  return (
    <header className={`topbar ${scrolled ? "scrolled" : ""}`}>
      <form
        className="search"
        onSubmit={(e) => {
          e.preventDefault();
          nav(q.trim() ? `/search?q=${encodeURIComponent(q.trim())}` : "/");
        }}
      >
        <Icon name="search" size={18} />
        <input
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            if (e.target.value.trim()) nav(`/search?q=${encodeURIComponent(e.target.value.trim())}`, { replace: true });
          }}
          placeholder="Search movies & shows"
          aria-label="Search"
        />
      </form>
      <div className="topbar-right">
        <span className="server-pill" title="Prototype: no server connected yet">
          <span className="dot" /> Prototype
        </span>
        <div className="avatar" title="Signed in as you">B</div>
      </div>
    </header>
  );
}
