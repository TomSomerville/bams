import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, type ServerStatus } from "../api";
import Icon from "./Icon";

export default function TopBar() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const [scrolled, setScrolled] = useState(false);
  const [scan, setScan] = useState<ServerStatus["scans"]["running"]>(null);

  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 8);
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);

  // Show a small "Scanning…" pill while the server is scanning a library.
  useEffect(() => {
    let alive = true;
    const tick = () => api.get<ServerStatus>("/api/status").then((s) => alive && setScan(s.scans.running)).catch(() => {});
    tick();
    const t = setInterval(tick, 5000);
    return () => { alive = false; clearInterval(t); };
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
          placeholder="Search shows, movies & music"
          aria-label="Search"
        />
      </form>
      <div className="topbar-right">
        {scan && (
          <Link to="/settings" className="server-pill" title={scan.step}>
            <span className="dot" /> Scanning…
          </Link>
        )}
      </div>
    </header>
  );
}
