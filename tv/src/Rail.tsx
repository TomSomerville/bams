import { Fragment } from "react";
import { useNav } from "./App";
import Icon, { type IconName } from "./Icon";

type Item = { id: string; label: string; icon: IconName; active: boolean; go: () => void };

/** The menu down the left: Home, each video library (this server's, then each connected server's under its name),
 *  Search, Settings. Slim until it has the focus. */
export default function Rail() {
  const nav = useNav();
  const r = nav.route;
  const libItem = (rid: number | undefined, l: { id: number; name: string; type: string }): Item => ({
    id: rid === undefined ? `lib${l.id}` : `r${rid}-lib${l.id}`, label: l.name, icon: (l.type === "show" ? "tv" : l.type === "music" ? "music" : "film") as IconName,
    active: r.name === "library" && r.id === l.id && r.rid === rid,
    go: () => nav.reset({ name: "library", id: l.id, rid }),
  });
  const top: Item[] = [
    { id: "home", label: "Home", icon: "home", active: r.name === "home", go: () => nav.reset({ name: "home" }) },
    ...nav.libraries.map((l) => libItem(undefined, l)),
  ];
  // this TV's other servers' libraries, the ones it shows (Settings)
  const remote = nav.servers.map((s) => ({
    s, items: s.libraries.filter((l) => !s.hidden[l.id]).map((l) => libItem(s.id, l)),
  })).filter((g) => g.items.length);
  const bottom: Item[] = [
    { id: "search", label: "Search", icon: "search", active: r.name === "search", go: () => nav.reset({ name: "search" }) },
    { id: "settings", label: "Settings", icon: "gear", active: r.name === "settings", go: () => nav.reset({ name: "settings" }) },
  ];
  const button = (it: Item) => (
    <button key={it.id} data-fid={`rail-${it.id}`} className={`rail-item ${it.active ? "active" : ""}`} data-entry={it.active || undefined} onClick={it.go}>
      <Icon name={it.icon} />
      <span>{it.label}</span>
    </button>
  );
  return (
    <nav className="rail" data-group>
      <img className="rail-logo" src="bams-icon.png" alt="" />
      {top.map(button)}
      {remote.map(({ s, items }) => (
        <Fragment key={s.id}>
          <div className="rail-server"><span>{s.name}{s.state ? ` · ${s.state}` : ""}</span></div>
          {items.map(button)}
        </Fragment>
      ))}
      {bottom.map(button)}
    </nav>
  );
}
