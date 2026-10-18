// Text subtitles on the TV apps (Samsung and Fire TV draw them the same way, src/vtt.ts): the server's WebVTT is read
// right, and a line is on screen exactly while the player's clock is within it, moved by the Timing control.
import { cueAt, parseVtt } from "../src/vtt";
import { eq, ok, test } from "./harness";

// as subtitles.webvtt sends them: FFmpeg's short form (no hours) for a film under an hour, hours past one, settings
// after the end time, two lines, italics, other markup, a bare "&", Windows line ends, a numbered cue
const VTT = "WEBVTT\r\n\r\n00:01.000 --> 00:02.500\r\nCafé <i>déjà</i> vu\r\n\r\n" +
  "2\n00:01:05.250 --> 00:01:07.000 line:90% align:start\nFirst line\n<font color=\"#ff0\">Second</font> & more\n\n" +
  "01:00:00.000 --> 01:00:01.500\nAn hour in\n\n00:10.000 --> 00:11.000\n\n";

test("subtitles: the server's WebVTT is read with every time form, markup kept or dropped as it should", () => {
  const cues = parseVtt(VTT);
  eq(cues.length, 3, "cues (the empty one dropped)");
  eq(cues[0].start, 1, "short form start");
  eq(cues[0].end, 2.5, "short form end");
  eq(cues[0].text, "Café <i>déjà</i> vu", "italics kept");
  eq(cues[1].start, 65.25, "minutes and milliseconds");
  eq(cues[1].end, 67, "end time before the cue settings");
  eq(cues[1].text, "First line<br>Second &amp; more", "two lines; <font> dropped, & escaped");
  eq(cues[2].start, 3600, "hours");
  eq(cues[2].end, 3601.5, "hours end");
});

test("subtitles: a line is shown exactly while the player's clock is within it", () => {
  const cues = parseVtt(VTT);
  eq(cueAt(cues, 0.99), undefined, "just before");
  eq(cueAt(cues, 1)?.start, 1, "at its start");
  eq(cueAt(cues, 2.5)?.start, 1, "at its end");
  eq(cueAt(cues, 2.51), undefined, "just after");
  eq(cueAt(cues, 66)?.start, 65.25, "the second line");
  eq(cueAt(cues, 3600.7)?.start, 3600, "an hour in");
  eq(cueAt([], 1), undefined, "no subtitles");
});

test("subtitles: the Timing control moves them later (+) or earlier (-) by its value", () => {
  const cues = parseVtt(VTT);
  eq(cueAt(cues, 1.2, 0.5), undefined, "+0.5 s: not yet at 1.2 s");
  eq(cueAt(cues, 1.5, 0.5)?.start, 1, "+0.5 s: from 1.5 s");
  eq(cueAt(cues, 2.9, 0.5)?.start, 1, "+0.5 s: until 3 s");
  eq(cueAt(cues, 0.6, -0.4)?.start, 1, "-0.4 s: already at 0.6 s");
  ok(!cueAt(cues, 2.2, -0.4), "-0.4 s: gone by 2.2 s");
});
