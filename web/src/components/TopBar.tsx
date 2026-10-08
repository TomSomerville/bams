import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, type ServerStatus } from "../api";
import { useAuth } from "../auth";
import Icon from "./Icon";

/** The signed-in user's initial; the menu has their account page and signing out. */
function Account() {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, [open]);
  return (
    <div className="account">
      <button className="avatar" onClick={(e) => { e.stopPropagation(); setOpen(!open); }} aria-haspopup="menu"
        aria-expanded={open} title={user.name}>{user.name.slice(0, 1).toUpperCase()}</button>
      {open && (
        <div className="account-menu" role="menu">
          <div className="account-name">{user.name}<span className="muted">{user.is_admin ? "Admin" : "Viewer"}</span></div>
          <Link to="/settings#account" role="menuitem">Account &amp; password</Link>
          <button role="menuitem" onClick={signOut}>Sign out</button>
        </div>
      )}
    </div>
  );
}

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
        <Account />
      </div>
    </header>
  );
}
