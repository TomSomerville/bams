// What the TV plays as-is and what the server has to help with. Samsung's 2022 TVs (Tizen 6.5) decode far more
// than a browser: MKV/AVI/TS, HEVC (incl. 10-bit HDR), VP9, AV1, MPEG-2/4, VC-1, and AC3/EAC3 sound. Not DTS or
// TrueHD (Samsung dropped DTS in 2018), not 10-bit H.264, not Dolby Vision without an HDR10 base layer.
// The server's own rules for browsers are in server/bams/stream.py `plan`; these replace them for the TV.

import type { FileInfo } from "./api";
import { hasAvplay } from "./engine";
import { prefs } from "./prefs";

type Caps = { containers: Set<string>; video: Set<string>; audio: Set<string>; h264HighBit: boolean; dvProfile5: boolean };

const TV: Caps = {
  containers: new Set(["MKV", "MP4", "AVI", "TS", "WebM", "WMV", "MPEG", "FLV"]),
  video: new Set(["H.264", "HEVC", "VP9", "AV1", "VP8", "MPEG-4", "MPEG-2", "MPEG-1", "VC-1"]),
  audio: new Set(["AAC", "MP3", "AC3", "EAC3", "FLAC", "Opus", "Vorbis", "PCM", "WMA", "MP2"]),
  h264HighBit: false,
  dvProfile5: false,
};

// a desktop browser (development): what Chromium plays in <video>
const BROWSER: Caps = {
  containers: new Set(["MP4", "WebM", "MKV"]),
  video: new Set(["H.264", "VP9", "AV1", "VP8"]),
  audio: new Set(["AAC", "MP3", "Opus", "Vorbis", "FLAC"]),
  h264HighBit: false,
  dvProfile5: false,
};

export function caps(): Caps {
  const c = hasAvplay() ? TV : BROWSER;
  if (prefs.dts && hasAvplay()) return { ...c, audio: new Set([...c.audio, "DTS"]) };
  return c;
}

export type Mode = "direct" | "remux" | "convert";

export type Plan = { mode: Mode; why: string };

/** How to play `file` with audio track `audio` (and picture subtitles to burn in, or null). */
export function plan(file: FileInfo, audio: number, burn: string | null): Plan {
  const p = file.probe;
  if (burn) return { mode: "convert", why: "subtitles drawn into the picture" };
  if (prefs.alwaysConvert) return { mode: "convert", why: "Settings: always convert" };
  if (!p) return { mode: "direct", why: "not probed yet: trying the file" };
  const c = caps();
  const v = p.video;
  if (v) {
    if (!c.video.has(v.codec)) return { mode: "convert", why: `${v.codec} video` };
    if (v.codec === "H.264" && !c.h264HighBit && ((v.bit_depth ?? 8) > 8 || /high 10|4:2:2|4:4:4/i.test(v.profile ?? ""))) {
      return { mode: "convert", why: "10-bit H.264" };
    }
    if (v.dv_profile === 5 && !c.dvProfile5) return { mode: "convert", why: "Dolby Vision without HDR10" };
  }
  const container = p.container ?? "";
  const track = p.audio[audio];
  const audioOk = !track || c.audio.has(track.codec);
  if (container && !c.containers.has(container)) return { mode: "remux", why: `${container} file` };
  if (!audioOk) return { mode: "remux", why: `${track.codec} sound` };
  return { mode: "direct", why: "plays as-is" };
}

/** Of a title's files (versions), the one to play: available, plays as-is if any does, then the biggest. */
export function pickFile(files: FileInfo[]): FileInfo | null {
  const ok = files.filter((f) => f.available);
  if (!ok.length) return null;
  const score = (f: FileInfo) => (plan(f, 0, null).mode === "direct" ? 2 : plan(f, 0, null).mode === "remux" ? 1 : 0);
  return [...ok].sort((a, b) => score(b) - score(a) || b.size - a.size)[0];
}

/** Which audio track: the language picked last time, else the default-flagged one, else the first. */
export function pickAudio(file: FileInfo): number {
  const tracks = file.audio_tracks ?? [];
  if (!tracks.length) return 0;
  const lang = prefs.audioLang;
  const byLang = lang ? tracks.find((t) => t.language === lang) : undefined;
  return (byLang ?? tracks.find((t) => t.default) ?? tracks[0]).index;
}
