import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { api, LIBRARIES_CHANGED, type ServerLibrary } from "../api";
import { useAuth } from "../auth";
import { useApi } from "../useApi";
import { LIB_TYPES } from "../format";
import Icon from "./Icon";
import { useReorder } from "./useReorder";

export default function Sidebar() {
  const { user } = useAuth();
  const { data, reload } = useApi<ServerLibrary[]>("/api/libraries");
  const [libs, setLibs] = useState<ServerLibrary[] | null>(null);
  useEffect(() => setLibs(data), [data]);
  useEffect(() => {  // added, renamed, removed or reordered elsewhere (Settings)
    window.addEventListener(LIBRARIES_CHANGED, reload);
    return () => window.removeEventListener(LIBRARIES_CHANGED, reload);
  }, [reload]);

  // admins arrange the libraries by dragging (or the arrow keys); everyone sees that order
  const move = (from: number, to: number) => {
    if (!libs) return;
    const next = [...libs];
    next.splice(to, 0, ...next.splice(from, 1));
    setLibs(next);
    api.put("/api/libraries/order", { ids: next.map((l) => l.id) })
      .then(() => window.dispatchEvent(new Event(LIBRARIES_CHANGED))).catch(reload);
  };
  const { listRef, dragging, handle, rowClass } = useReorder<HTMLDivElement>(libs?.length ?? 0, move);

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
        <div ref={listRef} className={`nav-libs ${dragging ? "dragging" : ""}`}>
          {libs?.map((l, i) => (
            <div key={l.id} className={`nav-row ${rowClass(i)}`}>
              <NavLink to={`/library/${l.id}`} className="nav-item">
                <Icon name={LIB_TYPES[l.type].icon} /> <span>{l.name}</span>
              </NavLink>
              {user.is_admin && libs.length > 1 && (
                <button type="button" className="reorder-handle nav-handle" aria-label={`Move ${l.name}`} {...handle(i)}>
                  <Icon name="grip" size={16} />
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="nav-group bottom">
        <NavLink to="/settings" className="nav-item">
          <Icon name="settings" /> <span>Settings</span>
        </NavLink>
      </div>
    </nav>
  );
}
