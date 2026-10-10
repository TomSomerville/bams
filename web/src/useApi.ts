import { useCallback, useEffect, useState } from "react";
import { useScope } from "./servers";

/** GET `path` (null = don't fetch). Re-fetches when the path changes. On another server's pages (/r/<rid>/…),
 *  "/api/…" goes to that server (servers.tsx). */
export function useApi<T>(path: string | null) {
  const { call } = useScope();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!!path);

  const load = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    try {
      setData(await call.get<T>(path));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [path, call]);

  useEffect(() => {
    setData(null);
    load();
  }, [load]);

  return { data, error, loading, reload: load };
}
