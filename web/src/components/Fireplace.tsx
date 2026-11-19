import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import { app, appAtLeast, inApp } from "../android";
import Icon from "./Icon";

// The fireplace (owner 2026-11-18): a looping yule-log video, full screen, to put on with holiday music. The button sits
// with "Add to playlist" and "Play queue" in the full-screen player (phones, and the Android app online and offline) and
// beside the queue button in the desktop bar. The video is a free-licensed clip in web/public (fireplace-CREDITS.txt);
// its credit must stay on screen with it.
//
// Open = `fire` in the navigation state, like the full-screen player, so Back closes it. It asks for full screen from
// the tap that opened it (the Android app shows it through its WebView's full-screen view; Back there leaves full
// screen, which closes it), and keeps the screen awake while it's open.

export const FIREPLACE_CREDIT = "Fire: “Kaminfeuer” by Larvis, CC BY-SA 4.0";
const SRC = `${import.meta.env.BASE_URL}fireplace.mp4`;

/** The Android app (0.2.11+) keeps the screen on for the page (bridge "keepAwake"). */
const appKeepsAwake = inApp && appAtLeast("0.2.11");

export function useFireplace(): { open: boolean; show: () => void; hide: () => void } {
  const location = useLocation();
  const navigate = useNavigate();
  const state = (location.state ?? {}) as Record<string, unknown>;
  const open = !!state.fire;
  return {
    open,
    show: () => {
      if (open) return;
      // full screen needs the tap itself, so it's asked here rather than when the picture appears
      void document.documentElement.requestFullscreen?.({ navigationUI: "hide" }).catch(() => undefined);
      navigate(location, { state: { ...state, fire: true } });
    },
    hide: () => { if (open) navigate(-1); },
  };
}

/** The button for the player's row of actions. */
export function FireplaceButton({ onClick, size = 22 }: { onClick: () => void; size?: number }) {
  return (
    <button className="icon-btn" onClick={onClick} aria-label="Fireplace" title="Fireplace">
      <Icon name="fire" size={size} />
    </button>
  );
}

export default function Fireplace({ title, artist, onClose }: { title: string | null; artist: string | null; onClose: () => void }) {
  const [shown, setShown] = useState(true);  // the close button and the song, hidden after a few quiet seconds
  const timer = useRef<number | undefined>(undefined);
  const wake = () => {
    setShown(true);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setShown(false), 3500);
  };

  // onClose is a new function at every render of the player (its clock redraws it every second): read it through a ref.
  // As a dependency, every redraw ran the cleanup, which left full screen, and that closed the fireplace.
  const close = useRef(onClose);
  close.current = onClose;

  useEffect(() => {
    wake();
    document.documentElement.classList.add("fp-open");
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") close.current(); else wake(); };
    // leaving full screen (Esc in a browser, Back in the app) closes the fireplace too
    let wasFull = !!document.fullscreenElement;
    const full = () => {
      if (wasFull && !document.fullscreenElement) close.current();
      wasFull = !!document.fullscreenElement;
    };
    window.addEventListener("keydown", key);
    document.addEventListener("fullscreenchange", full);
    return () => {
      window.clearTimeout(timer.current);
      document.documentElement.classList.remove("fp-open");
      window.removeEventListener("keydown", key);
      document.removeEventListener("fullscreenchange", full);
      if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined);
    };
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  // the screen stays on while the fire burns
  useEffect(() => {
    let lock: { release: () => Promise<void> } | null = null;
    let gone = false;
    const ask = () => {
      const wl = (navigator as Navigator & { wakeLock?: { request: (t: "screen") => Promise<{ release: () => Promise<void> }> } }).wakeLock;
      if (!wl || document.visibilityState !== "visible") return;
      wl.request("screen").then((l) => { if (gone) void l.release(); else lock = l; }).catch(() => undefined);
    };
    ask();
    document.addEventListener("visibilitychange", ask);  // a wake lock ends when the page is hidden
    if (appKeepsAwake) void app("keepAwake", { on: true }).catch(() => undefined);
    return () => {
      gone = true;
      document.removeEventListener("visibilitychange", ask);
      void lock?.release().catch(() => undefined);
      if (appKeepsAwake) void app("keepAwake", { on: false }).catch(() => undefined);
    };
  }, []);

  // into <body>: the desktop bar it opens from has a backdrop blur, which would hold a fixed layer inside the bar
  return createPortal(
    <div className={`fireplace ${shown ? "shown" : ""}`} role="dialog" aria-modal="true" aria-label="Fireplace"
      onPointerMove={wake} onClick={wake}>
      <video src={SRC} autoPlay loop muted playsInline disablePictureInPicture aria-hidden="true" />
      <button className="icon-btn fireplace-close" onClick={(e) => { e.stopPropagation(); onClose(); }}
        aria-label="Close the fireplace" title="Close"><Icon name="close" size={26} /></button>
      <div className="fireplace-foot">
        {title && <div className="fireplace-song"><b>{title}</b>{artist && <span> · {artist}</span>}</div>}
        <div className="fireplace-credit">{FIREPLACE_CREDIT}</div>
      </div>
    </div>,
    document.body,
  );
}
