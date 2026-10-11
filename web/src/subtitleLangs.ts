// OpenSubtitles' languages for "Check OpenSubtitles". SHARED with the TV app (tv/src/screens/Player.tsx): no React,
// router or web-only imports, and no storage (each app remembers the last pick in its own way).

/** OpenSubtitles' language codes offered (theirs: two letters, a few with a region). */
export const OS_LANGUAGES = ["ar", "bg", "cs", "da", "de", "el", "en", "es", "et", "fa", "fi", "fr", "he", "hi", "hr",
  "hu", "id", "is", "it", "ja", "ko", "lt", "lv", "ms", "nl", "no", "pl", "pt-br", "pt-pt", "ro", "ru", "sk", "sl", "sr",
  "sv", "th", "tr", "uk", "vi", "zh-cn", "zh-tw"];

/** "pt-br" -> "Brazilian Portuguese" (the browser's own names). */
export function languageName(code: string | null): string {
  if (!code) return "Unknown language";
  try {
    return new Intl.DisplayNames(["en"], { type: "language" }).of(code) ?? code;
  } catch {
    return code;
  }
}

/** The language to search in first: the last one searched, else the remembered subtitle language, else the
 *  device's (mapped to OpenSubtitles' codes: "pt-BR" -> "pt-br", "de-AT" -> "de"). */
export function defaultLanguage(saved: string | null, subLang: string | null): string {
  const want = (saved || subLang || navigator.language || "en").toLowerCase();
  return OS_LANGUAGES.includes(want) ? want : OS_LANGUAGES.find((c) => c === want.split("-")[0])
    ?? (want.startsWith("pt") ? "pt-pt" : want.startsWith("zh") ? "zh-cn" : "en");
}
