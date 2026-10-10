// This TV's own settings (kept on the TV, not the account): playback choices and remembered languages.

type Prefs = {
  /** convert every video on the server, even what the TV would play as-is (for troubleshooting) */
  alwaysConvert: boolean;
  /** some Samsung models do decode DTS: let them try */
  dts: boolean;
  audioLang: string | null;
  /** subtitle language, "" = off */
  subLang: string | null;
  /** seconds the subtitles are shown later than their times (the TV delays its picture; the text isn't) */
  subDelay: number;
};

const KEY = "bams.prefs";
const DEFAULTS: Prefs = { alwaysConvert: false, dts: false, audioLang: null, subLang: null, subDelay: 0 };

function load(): Prefs {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || "{}") };
  } catch {
    return { ...DEFAULTS };
  }
}

export const prefs: Prefs = load();

export function setPref<K extends keyof Prefs>(k: K, v: Prefs[K]) {
  prefs[k] = v;
  try {
    localStorage.setItem(KEY, JSON.stringify(prefs));
  } catch { /* storage unavailable */ }
}
