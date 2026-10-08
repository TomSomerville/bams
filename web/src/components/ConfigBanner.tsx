import { Link, useLocation } from "react-router-dom";
import { useSettings } from "../settings";
import Icon from "./Icon";

/** Shown on every page until a TMDB key is configured on the server. Clicking jumps to the key field. */
export default function ConfigBanner() {
  const { tmdb, serverError } = useSettings();
  const { pathname, hash } = useLocation();

  if (serverError && !tmdb) {
    return (
      <div className="config-banner" role="alert">
        <Icon name="alert" size={18} />
        <span><strong>Can't reach the BAMS server.</strong> Start it with <code>python -m bams serve</code>.</span>
      </div>
    );
  }
  if (!tmdb || tmdb.configured) return null;

  // Already looking at the field: the banner would just point at itself.
  const onTarget = pathname === "/settings" && hash === "#tmdb";

  return (
    <Link to="/settings#tmdb" className={`config-banner ${onTarget ? "quiet" : ""}`} role="alert">
      <Icon name="alert" size={18} />
      <span>
        <strong>TMDB API key not configured.</strong> BAMS can't fetch posters, descriptions or match your files
        until you add one.
      </span>
      <span className="config-banner-cta">Add key <Icon name="chevronRight" size={16} /></span>
    </Link>
  );
}
