import { useNav } from "./App";
import Icon, { type IconName } from "./Icon";

/** The menu down the left: Home, each video library, Search, Settings. Slim until it has the focus. */
export default function Rail() {
  const nav = useNav();
  const r = nav.route;
  const items: { id: string; label: string; icon: IconName; active: boolean; go: () => void }[] = [
    { id: "home", label: "Home", icon: "home", active: r.name === "home", go: () => nav.reset({ name: "home" }) },
    ...nav.libraries.filter((l) => l.type !== "music").map((l) => ({
      id: `lib${l.id}`, label: l.name, icon: (l.type === "show" ? "tv" : "film") as IconName,
      active: r.name === "library" && r.id === l.id, go: () => nav.reset({ name: "library", id: l.id }),
    })),
    { id: "search", label: "Search", icon: "search", active: r.name === "search", go: () => nav.reset({ name: "search" }) },
    { id: "settings", label: "Settings", icon: "gear", active: r.name === "settings", go: () => nav.reset({ name: "settings" }) },
  ];
  return (
    <nav className="rail" data-group>
      <img className="rail-logo" src="bams-icon.png" alt="" />
      {items.map((it) => (
        <button key={it.id} data-fid={`rail-${it.id}`} className={`rail-item ${it.active ? "active" : ""}`} data-entry={it.active || undefined} onClick={it.go}>
          <Icon name={it.icon} />
          <span>{it.label}</span>
        </button>
      ))}
    </nav>
  );
}
