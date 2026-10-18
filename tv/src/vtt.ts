// Text subtitles in the player: the server's WebVTT (subtitles.webvtt) parsed into cues, and the cue on screen at a
// moment of the player's clock. Kept apart from Player.tsx so tests can check the timing (tv/test/subtitles.test.ts).

export type Cue = { start: number; end: number; text: string };

/** WebVTT -> cues. Keeps <i>/<b>, drops other markup. */
export function parseVtt(text: string): Cue[] {
  const out: Cue[] = [];
  const t = (s: string) => {
    const p = s.trim().split(":").map(Number);
    return p.length === 3 ? p[0] * 3600 + p[1] * 60 + p[2] : p[0] * 60 + p[1];
  };
  for (const block of text.replace(/\r/g, "").split(/\n\n+/)) {
    const lines = block.split("\n");
    const i = lines.findIndex((l) => l.includes("-->"));
    if (i < 0) continue;
    const [a, b] = lines[i].split("-->");
    const body = lines.slice(i + 1).join("<br>")
      .replace(/<(?!\/?(i|b|br)>)[^>]*>/g, "")
      .replace(/&(?!(amp|lt|gt|nbsp);)/g, "&amp;");
    if (body.trim()) out.push({ start: t(a), end: t(b.trim().split(/\s/)[0]), text: body });
  }
  return out;
}

/** The cue to show at `time` (s) on the player's clock, `delay` (s) being the menu's Timing: + shows them later. */
export function cueAt(cues: Cue[], time: number, delay = 0): Cue | undefined {
  const at = time - delay;
  return cues.length ? cues.find((c) => at >= c.start && at <= c.end) : undefined;
}
