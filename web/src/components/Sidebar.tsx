import { NavLink } from "react-router-dom";
import Icon from "./Icon";

const NAV = [
  { to: "/", label: "Home", icon: "home", end: true },
  { to: "/movies", label: "Movies", icon: "film" },
  { to: "/tv", label: "TV Shows", icon: "tv" },
  { to: "/music", label: "Music", icon: "music", soon: true },
];

export default function Sidebar() {
  return (
    <nav className="sidebar">
      <NavLink to="/" className="brand" aria-label="BAMS home">
        <img src="/brand/bams-wordmark.png" alt="BAMS — Your Personal Media Stream" />
      </NavLink>
      <NavLink to="/" className="brand-icon" aria-label="BAMS home">
        <img src="/brand/bams-icon.png" alt="" />
      </NavLink>

      <div className="nav-group">
        <div className="nav-label">Libraries</div>
        {NAV.map((n) =>
          n.soon ? (
            <span key={n.to} className="nav-item disabled" title="Music arrives in phase 3">
              <Icon name={n.icon} /> <span>{n.label}</span> <em className="soon">soon</em>
            </span>
          ) : (
            <NavLink key={n.to} to={n.to} end={n.end} className="nav-item">
              <Icon name={n.icon} /> <span>{n.label}</span>
            </NavLink>
          ),
        )}
      </div>

      <div className="nav-group bottom">
        <NavLink to="/settings" className="nav-item">
          <Icon name="settings" /> <span>Settings</span>
        </NavLink>
      </div>
    </nav>
  );
}
