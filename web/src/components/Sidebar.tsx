import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { api, LIBRARIES_CHANGED, SERVER_RENAMED, type RemoteServer, type ServerLibrary } from "../api";
import { useAuth } from "../auth";
import { setLibraryOrder, useRemotes } from "../servers";
import { useApi } from "../useApi";
import { LIB_TYPES } from "../format";
import Icon from "./Icon";
import { useReorder } from "./useReorder";

export default function Sidebar() {
  const { user } = useAuth();
  const { servers } = useRemotes();
  const { data, reload } = useApi<ServerLibrary[]>("/api/libraries");
  const [libs, setLibs] = useState<ServerLibrary[] | null>(null);
  useEffect(() => setLibs(data), [data]);
  useEffect(() => {  // added, renamed, removed or reordered elsewhere (Settings)
    window.addEventListener(LIBRARIES_CHANGED, reload);
    return () => window.removeEventListener(LIBRARIES_CHANGED, reload);
  }, [reload]);
  // this server's own libraries go under its name (Settings → Server name), like other servers' do
  const hello = useApi<{ name: string }>("/api/hello");
  const reloadName = hello.reload;
  useEffect(() => {
    window.addEventListener(SERVER_RENAMED, reloadName);
    return () => window.removeEventListener(SERVER_RENAMED, reloadName);
  }, [reloadName]);

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
        {!!libs?.length && (
          <div className="nav-label nav-server" title={hello.data?.name}><span>{hello.data?.name ?? " "}</span></div>
        )}
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
        {/* other BAMS servers this account is connected to: their libraries, as named and chosen in Settings */}
        {servers?.map((s) => <RemoteLibraries key={s.id} s={s} />)}
      </div>

      <div className="nav-group bottom">
        <NavLink to="/settings" className="nav-item">
          <Icon name="settings" /> <span>Settings</span>
        </NavLink>
      </div>
    </nav>
  );
}

/** Another server's libraries, the ones shown here. Anyone can drag them into order: it's kept in this browser
 *  (servers.tsx), like their names, so it needs no admin rights there and changes nothing for others. */
function RemoteLibraries({ s }: { s: RemoteServer }) {
  const shown = s.libraries.filter((l) => l.show);
  const move = (from: number, to: number) => {
    const next = [...shown];
    next.splice(to, 0, ...next.splice(from, 1));
    let k = 0;  // hidden libraries keep their places in the order; the shown ones swap theirs
    setLibraryOrder(s.id, s.libraries.map((l) => (l.show ? next[k++].id : l.id)));
  };
  const { listRef, dragging, handle, rowClass } = useReorder<HTMLDivElement>(shown.length, move);
  if (!shown.length) return null;
  const state = !s.signed_in ? "signed out" : !s.online ? "offline" : null;
  return (
    <div className="nav-remote">
      <div className="nav-label nav-server" title={`${s.name} (${s.url}), signed in as ${s.account}`}>
        <span>{s.name}</span>
        {state && <NavLink to="/settings#servers" className="nav-state" title={state === "signed out"
          ? "Sign in to this server again in Settings" : "Can't reach this server right now"}>{state}</NavLink>}
      </div>
      <div ref={listRef} className={`nav-libs ${dragging ? "dragging" : ""}`}>
        {shown.map((l, i) => (
          <div key={l.id} className={`nav-row ${rowClass(i)}`}>
            <NavLink to={`/r/${s.id}/library/${l.id}`} className="nav-item">
              <Icon name={LIB_TYPES[l.type].icon} /> <span>{l.name}</span>
            </NavLink>
            {shown.length > 1 && (
              <button type="button" className="reorder-handle nav-handle" aria-label={`Move ${l.name}`} {...handle(i)}>
                <Icon name="grip" size={16} />
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
