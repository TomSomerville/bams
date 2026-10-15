// What the TV plays as-is and what the server has to help with. Samsung's 2022 TVs (Tizen 6.5) decode far more
// than a browser: MKV/AVI/TS, HEVC (incl. 10-bit HDR), VP9, AV1, MPEG-2/4, VC-1, and AC3/EAC3 sound. Not DTS or
// TrueHD (Samsung dropped DTS in 2018), not 10-bit H.264, not Dolby Vision without an HDR10 base layer.
// A Fire TV says itself what it decodes (Android's codec list, firetv.ts `FireCaps`): sticks differ a lot (HEVC,
// AV1, 4K, Dolby sound only through an AV receiver...).
// The server's own rules for browsers are in server/bams/stream.py `plan`; these replace them for the TV.

import type { FileInfo } from "./api";
import { hasAvplay, hasExo } from "./engine";
import { fireInfo } from "./firetv";
import { pc } from "./platform";
import { prefs } from "./prefs";

type Caps = {
  containers: Set<string>; video: Set<string>; audio: Set<string>; h264HighBit: boolean; dvProfile5: boolean;
  /** the largest picture each video codec decodes (Fire TV: a 1080p stick takes no 4K), when known */
  size?: Record<string, { w: number; h: number }>;
};

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

// A PC's browser (theatre mode, development) is asked what it decodes, the way the web player's canDecode() does
// (web/src/pages/Player.tsx): Edge on Windows decodes Dolby and, with the hardware, HEVC; Chrome on Linux neither.
// Containers as the server's own browser rules have them (stream.FILE_OK_CONTAINERS: Chromium plays these).
const supported = (t: string): boolean => {
  try {
    return "MediaSource" in window ? MediaSource.isTypeSupported(t) : document.createElement("video").canPlayType(t) !== "";
  } catch {
    return false;
  }
};
const VIDEO_TYPES: Record<string, (ten: boolean) => string> = {
  HEVC: (ten) => `video/mp4; codecs="${ten ? "hvc1.2.4.L123.B0" : "hvc1.1.6.L123.B0"}"`,
  AV1: (ten) => `video/mp4; codecs="av01.0.08M.${ten ? "10" : "08"}"`,
  VP9: (ten) => `video/mp4; codecs="vp09.${ten ? "02" : "00"}.40.${ten ? "10" : "08"}"`,
  VP8: () => 'video/webm; codecs="vp8"',
};
let pcAsked: Caps | null = null;
function pcCaps(): Caps {
  if (!pcAsked) {
    const video = new Set(["H.264", ...Object.keys(VIDEO_TYPES).filter((c) => supported(VIDEO_TYPES[c](false)))]);
    const audio = new Set(["AAC", "MP3", "Opus", "Vorbis", "FLAC"]);
    if (supported('audio/mp4; codecs="ac-3"')) audio.add("AC3");
    if (supported('audio/mp4; codecs="ec-3"')) audio.add("EAC3");
    pcAsked = { containers: new Set(["MP4", "WebM", "MKV"]), video, audio, h264HighBit: false,
      dvProfile5: supported('video/mp4; codecs="dvh1.05.06"') };
  }
  return pcAsked;
}

// ExoPlayer's file readers (no ASF/WMV); codecs come from the device
const FIRE_CONTAINERS = new Set(["MKV", "MP4", "WebM", "TS", "AVI", "MPEG", "FLV", "OGG"]);

function fireCaps(): Caps | null {
  const f = fireInfo()?.caps;
  if (!f) return null;
  return { containers: FIRE_CONTAINERS, video: new Set(Object.keys(f.video)), audio: new Set(f.audio),
    h264HighBit: f.h264HighBit, dvProfile5: f.dvProfile5, size: f.video };
}

export function caps(): Caps {
  if (hasExo()) return fireCaps() ?? BROWSER;
  if (pc()) return pcCaps();
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
    // a PC's browser may decode a codec at 8 bits but not 10
    if (pc() && (v.bit_depth ?? 8) > 8 && VIDEO_TYPES[v.codec] && !supported(VIDEO_TYPES[v.codec](true))) {
      return { mode: "convert", why: `10-bit ${v.codec}` };
    }
    const max = c.size?.[v.codec];
    if (max && v.width && v.height && (Math.min(v.width, v.height) > Math.min(max.w, max.h) || Math.max(v.width, v.height) > Math.max(max.w, max.h))) {
      return { mode: "convert", why: `${v.height}p ${v.codec}: bigger than this device decodes` };
    }
  }
  const container = p.container ?? "";
  const track = p.audio[audio];
  const audioOk = !track || c.audio.has(track.codec);
  if (container && !c.containers.has(container)) return { mode: "remux", why: `${container} file` };
  if (!audioOk) return { mode: "remux", why: `${track.codec} sound` };
  return { mode: "direct", why: "plays as-is" };
}

/** The tallest picture a conversion may have (the server converts to H.264): what this device decodes, on a Fire
 *  TV; elsewhere as large as the server makes it. */
export function convertHeight(): number | undefined {
  const h264 = caps().size?.["H.264"];
  if (!h264) return undefined;
  return Math.max(480, Math.min(h264.w, h264.h));
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
