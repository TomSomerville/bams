import { NavLink } from "react-router-dom";
import type { ServerLibrary } from "../api";
import { useApi } from "../useApi";
import { LIB_TYPES } from "../format";
import Icon from "./Icon";

export default function Sidebar() {
  const { data: libs } = useApi<ServerLibrary[]>("/api/libraries");

  return (
    <nav className="sidebar">
      <NavLink to="/" className="brand" aria-label="BAMS home">
        <img src="/brand/bams-wordmark.png" alt="BAMS — Bad Ass Media Server" />
      </NavLink>
      <NavLink to="/" className="brand-icon" aria-label="BAMS home">
        <img src="/brand/bams-icon.png" alt="" />
      </NavLink>

      <div className="nav-group">
        <NavLink to="/" end className="nav-item">
          <Icon name="home" /> <span>Home</span>
        </NavLink>
        {!!libs?.length && <div className="nav-label">Libraries</div>}
        {libs?.map((l) => (
          <NavLink key={l.id} to={`/library/${l.id}`} className="nav-item">
            <Icon name={LIB_TYPES[l.type].icon} /> <span>{l.name}</span>
          </NavLink>
        ))}
      </div>

      <div className="nav-group bottom">
        <NavLink to="/settings" className="nav-item">
          <Icon name="settings" /> <span>Settings</span>
        </NavLink>
      </div>
    </nav>
  );
}
