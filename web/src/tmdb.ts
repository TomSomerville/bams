// TMDB key helpers for the UI. The server verifies and stores the key (PUT /api/settings/tmdb-key);
// every BAMS install uses its owner's own key, there is no shared key.
//   - "API Read Access Token" (a long JWT starting "eyJ"), preferred
//   - "API Key" (32 hex chars)

export const TMDB_SIGNUP_URL = "https://www.themoviedb.org/settings/api";

export type KeyKind = "token" | "apikey";

export function keyKind(key: string): KeyKind | null {
  const k = key.trim();
  if (/^eyJ[\w-]+\.[\w-]+\.[\w-]+$/.test(k)) return "token";
  if (/^[0-9a-f]{32}$/i.test(k)) return "apikey";
  return null;
}
