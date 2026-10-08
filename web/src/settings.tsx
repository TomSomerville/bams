// Server settings as the UI sees them. The server is the source of truth (GET /api/settings);
// the TMDB key itself never comes back to the browser, only whether one is set and its last 4.
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type TmdbStatus } from "./api";

type Settings = {
  /** null while loading or when the server can't be reached */
  tmdb: TmdbStatus | null;
  serverError: string | null;
  refresh: () => Promise<void>;
  setTmdb: (s: TmdbStatus) => void;
};

const Ctx = createContext<Settings | null>(null);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [tmdb, setTmdb] = useState<TmdbStatus | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const s = await api.get<{ tmdb: TmdbStatus }>("/api/settings");
      setTmdb(s.tmdb);
      setServerError(null);
    } catch (e) {
      setServerError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return <Ctx.Provider value={{ tmdb, serverError, refresh, setTmdb }}>{children}</Ctx.Provider>;
}

export function useSettings() {
  const s = useContext(Ctx);
  if (!s) throw new Error("useSettings outside SettingsProvider");
  return s;
}
