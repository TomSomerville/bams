// The quality line under a playing song's title and artist ("FLAC · 24-bit / 96 kHz", "MP3 · 320 kbps"; a song the
// server converts while streaming: "ALAC 24-bit / 96 kHz → AAC 256 kbps"). Shared with the TV app and the Android
// app's own pages: keep it free of React, the router and browser-only code.

/** What the server says about a track's file (`playback` of a queue track; stream.plan_audio). */
export type AudioQuality = {
  audio_codec?: string | null;
  sample_rate?: number | null;
  bit_depth?: number | null;
  bitrate?: number | null;
  channels?: number | null;
  /** "transcode": converted while streaming, to `output` */
  mode?: string;
  output?: "aac" | "flac" | null;
  /** what the server converts to when asked (its Settings → Music choice) */
  convert_to?: "aac" | "flac" | null;
};

const LOSSLESS = ["FLAC", "ALAC", "PCM", "WAVPACK", "APE", "WMA LOSSLESS", "DSD", "TRUEHD", "MLP", "TTA"];

/** The bitrate the server converts to (stream.audio_cmd: AAC 256k). */
const AAC_KBPS = 256;

function rate(hz: number): string {
  if (hz >= 1_000_000) return `${(hz / 1_000_000).toFixed(1)} MHz`;
  const k = hz / 1000;
  return `${Number.isInteger(k) ? k : k.toFixed(1)} kHz`;
}

function channels(n: number | null | undefined): string | null {
  return n && n > 2 ? ({ 6: "5.1", 8: "7.1" } as Record<number, string>)[n] ?? `${n} ch` : null;
}

/** The file as it is: "FLAC · 16-bit / 44.1 kHz", "MP3 · 320 kbps", "AAC · 256 kbps". */
export function fileQuality(q: AudioQuality): string | null {
  const codec = q.audio_codec;
  if (!codec) return null;
  const lossless = LOSSLESS.includes(codec.toUpperCase());
  const parts = [codec];
  if (lossless) {
    const depth = q.bit_depth && codec.toUpperCase() !== "DSD" ? `${q.bit_depth}-bit` : null;
    const hz = q.sample_rate ? rate(q.sample_rate) : null;
    if (depth || hz) parts.push([depth, hz].filter(Boolean).join(" / "));
  } else if (q.bitrate) {
    parts.push(`${Math.round(q.bitrate / 1000)} kbps`);
  } else if (q.sample_rate) {
    parts.push(rate(q.sample_rate));
  }
  const ch = channels(q.channels);
  if (ch) parts.push(ch);
  return parts.join(" · ");
}

/** What's playing: the file's quality, and what it's converted to when the server converts it (`converted`: a
 *  player that asked for the conversion itself, after it couldn't decode the file as it is). */
export function qualityLine(q: AudioQuality | null | undefined, converted = false): string | null {
  if (!q) return null;
  const file = fileQuality(q);
  if (q.mode !== "transcode" && !converted) return file;
  const to = (q.output ?? q.convert_to) === "flac" ? "FLAC (lossless)" : `AAC ${AAC_KBPS} kbps`;
  return file ? `${file.replace(" · ", " ")} → ${to}` : `Converted to ${to}`;
}
