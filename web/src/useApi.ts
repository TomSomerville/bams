import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

/** GET `path` (null = don't fetch). Re-fetches when the path changes. */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!!path);

  const load = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    try {
      setData(await api.get<T>(path));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    setData(null);
    load();
  }, [load]);

  return { data, error, loading, reload: load };
}
