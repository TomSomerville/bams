// The video queue (src/random.tsx): a holiday's Shuffle is untracked (no progress, not in Continue Watching) for the
// videos in it only; Play Random's queue is tracked as before.
import { startQueue, untracked } from "../src/random";
import { session } from "../src/platform";
import { eq, test } from "./harness";

const entry = (id: number) => ({ id, kind: "episode" as const, title: `E${id}`, show: "Show", season_number: 1,
  episode_number: id, runtime: 22, year: null, art: null });

test("queue: a holiday Shuffle is untracked, Play Random isn't", () => {
  const saved = session.get("bams.videoQueue");
  try {
    startQueue([entry(1), entry(2)], undefined, { untracked: true });
    eq(untracked(2, undefined), true, "an episode in the shuffle");
    eq(untracked(3, undefined), false, "an episode not in it");
    eq(untracked(2, 5), false, "the same id on another server");
    startQueue([entry(1), entry(2)], undefined);
    eq(untracked(2, undefined), false, "Play Random keeps tracking");
  } finally {
    if (saved === null) session.remove("bams.videoQueue"); else session.set("bams.videoQueue", saved);
  }
});
