const PATHS = {
  home: "M3 11 12 3l9 8v10h-6v-6H9v6H3z",
  film: "M4 4h16v16H4zM8 4v16M16 4v16M4 8h4M4 12h4M4 16h4M16 8h4M16 12h4M16 16h4",
  tv: "M3 6h18v12H3zM8 21h8M12 18v3",
  search: "M10.5 4a6.5 6.5 0 1 1 0 13 6.5 6.5 0 0 1 0-13zM15.5 15.5 21 21",
  gear: "M12 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6zM12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1",
  play: "M7 4v16l13-8z",
  pause: "M7 4h4v16H7zM13 4h4v16h-4z",
  back10: "M4 12a8 8 0 1 0 2.3-5.7M4 4v4h4",
  fwd30: "M20 12a8 8 0 1 1-2.3-5.7M20 4v4h-4",
  audio: "M4 9h4l5-4v14l-5-4H4zM16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11",
  subs: "M3 5h18v14H3zM7 11h4M13 11h4M7 15h10",
  check: "M5 12l5 5 9-10",
  restart: "M4 12a8 8 0 1 0 2.3-5.7M4 4v4h4",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6z",
  next: "M5 4v16l11-8zM18 4h2v16h-2z",
  prev: "M19 4v16L8 12zM4 4h2v16H4z",
  music: "M9 18V5l12-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM21 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z",
  shuffle: "M16 3h5v5M4 20 21 3M21 16v5h-5M15 15l6 6M4 4l5 5",
  stop: "M6 6h12v12H6z",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  up: "M6 15l6-6 6 6",
  down: "M6 9l6 6 6-6",
  close: "M6 6l12 12M18 6 6 18",
  plus: "M12 5v14M5 12h14",
  // add to a playlist: lines with a plus (the web's Icon has the same)
  listPlus: "M3 6h12M3 12h12M3 18h7M17 14v8M13 18h8",
  edit: "M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4",
  // a bed (headboard, sleeper's head, blanket, frame), with two stars above it in FILLS: sleep mode
  sleep: "M3 9v11M3 17h18v3M9 17v-4h9a3 3 0 0 1 3 3v1M6 15.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z",
  // the watch list: a bookmark, filled when the item is on it
  bookmark: "M6 3h12v18l-6-4.5L6 21z",
  bookmarkOn: "M6 3h12v18l-6-4.5L6 21z",
};
// Filled shapes drawn over an icon's strokes (small stars don't read as strokes); the web's Icon has the same
const FILLS: Partial<Record<keyof typeof PATHS, string>> = {
  sleep: "M14 1l1.1 2.4 2.4 1.1-2.4 1.1L14 8l-1.1-2.4-2.4-1.1 2.4-1.1zM20 5.5l.7 1.3 1.3.7-1.3.7-.7 1.3-.7-1.3-1.3-.7 1.3-.7z",
  bookmarkOn: "M6 3h12v18l-6-4.5L6 21z",
};

export type IconName = keyof typeof PATHS;

export default function Icon({ name, size = 36 }: { name: IconName; size?: number }) {
  const fill = name === "play" || name === "pause" || name === "next" || name === "prev" || name === "stop";
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" aria-hidden="true"
      fill={fill ? "currentColor" : "none"} stroke={fill ? "none" : "currentColor"} strokeWidth={2}
      strokeLinecap="round" strokeLinejoin="round">
      <path d={PATHS[name]} />
      {FILLS[name] && <path d={FILLS[name]} fill="currentColor" stroke="none" />}
    </svg>
  );
}
