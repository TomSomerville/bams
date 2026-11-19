// The fireplace on the TV (owner 2026-11-18), as on the web (web/src/components/Fireplace.tsx): a looping yule-log
// video over the whole screen while the music plays. Opened from the now-playing bar (screens/Music.tsx NowPlaying);
// Back closes it. Its two buttons (play/pause, close) and the song and the clip's credit show for a few seconds after
// any key, then fade. The clip is tv/public/fireplace.mp4 (fireplace-CREDITS.txt): the credit must stay with it.
// The screen stays on while it shows: Fire TV through the app (BamsAndroid.keepAwake), Samsung by turning its
// screensaver off, a PC (theatre mode) with a wake lock where the browser allows one.

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Icon from "./Icon";
import { keyHandler, setKeyHandler } from "./keys";
import { focus } from "./nav";
import { isBack, KEY } from "./tizen";

const CREDIT = "Fire: “Kaminfeuer” by Larvis, CC BY-SA 4.0";

type WakeLock = { release: () => Promise<void> };

/** The screen stays on (true) or may sleep again (false), however this device does it. */
function stayAwake(on: boolean, lock: { current: WakeLock | null }) {
  try { window.BamsAndroid?.keepAwake?.(on); } catch { /* an older Fire TV app */ }
  try {
    const ac = window.webapis?.appcommon;
    ac?.setScreenSaver?.(on ? ac.AppCommonScreenSaverState.SCREEN_SAVER_OFF : ac.AppCommonScreenSaverState.SCREEN_SAVER_ON);
  } catch { /* not a Samsung TV */ }
  const wl = (navigator as Navigator & { wakeLock?: { request: (t: "screen") => Promise<WakeLock> } }).wakeLock;
  if (on && wl) wl.request("screen").then((l) => { lock.current = l; }).catch(() => undefined);
  if (!on) { void lock.current?.release().catch(() => undefined); lock.current = null; }
}

export default function Fireplace({ title, artist, playing, onToggle, onClose }: {
  title: string; artist: string | null; playing: boolean; onToggle: () => void; onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(true);
  const timer = useRef<number | undefined>(undefined);
  const close = useRef(onClose);
  close.current = onClose;

  const shownNow = useRef(true);
  shownNow.current = shown;

  useEffect(() => {
    const wake = () => {
      setShown(true);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setShown(false), 4000);
    };
    wake();
    setTimeout(() => focus(ref.current?.querySelector<HTMLElement>("[data-fid='fire-close']")));
    const before = keyHandler();
    setKeyHandler((e) => {
      const hidden = !shownNow.current;
      wake();
      if (isBack(e)) {
        close.current();
        return true;
      }
      // while the buttons are hidden, OK and the arrows only bring them back; media keys work as usual
      return hidden && [KEY.ENTER, KEY.LEFT, KEY.UP, KEY.RIGHT, KEY.DOWN].includes(e.keyCode);
    });
    window.addEventListener("pointermove", wake);
    const lock = { current: null as WakeLock | null };
    stayAwake(true, lock);
    return () => {
      window.clearTimeout(timer.current);
      setKeyHandler(before);
      window.removeEventListener("pointermove", wake);
      stayAwake(false, lock);
    };
  }, []);

  // into <body>, above everything (a layer inside the now-playing bar would be held to the bar)
  return createPortal(
    <div className={`fireplace ${shown ? "shown" : ""}`} data-trap ref={ref}>
      <video src="fireplace.mp4" autoPlay loop muted playsInline aria-hidden="true" />
      <div className="fireplace-foot">
        <div className="fireplace-song"><b>{title}</b>{artist ? `  ·  ${artist}` : ""}</div>
        <div className="fireplace-buttons">
          <button className="round" data-fid="fire-play" onClick={onToggle} aria-label={playing ? "Pause" : "Play"}>
            <Icon name={playing ? "pause" : "play"} />
          </button>
          <button className="round" data-fid="fire-close" onClick={onClose} aria-label="Close the fireplace"><Icon name="close" /></button>
        </div>
        <div className="fireplace-credit">{CREDIT}</div>
      </div>
    </div>,
    document.body,
  );
}
