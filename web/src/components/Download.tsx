import { useCallback, useEffect, useState, type MouseEvent } from "react";
import { useAuth } from "../auth";
import {
  appApi, downloadKey, DOWNLOADS_CHANGED, inApp, unplayableAudio, type AppInfo, type DownloadState,
} from "../android";
import { appServer, useScope } from "../servers";
import Icon from "./Icon";

// Download buttons: only in the Android app (android.ts), for accounts allowed to download (an admin turns it on
// in Settings → Accounts; on another server, its own admin decides, and the app shows what it answered).

let infoAsked: Promise<AppInfo> | null = null;

/** What the app says about itself (codecs, storage), asked once per page load; null outside the app. */
export function useAppInfo(): AppInfo | null {
  const [info, setInfo] = useState<AppInfo | null>(null);
  useEffect(() => {
    if (!inApp) return;
    infoAsked ??= appApi.info();
    infoAsked.then(setInfo).catch(() => { infoAsked = null; });
  }, []);
  return info;
}

/** The app's state of a download (asked again whenever downloads change). */
function useDownloadState(rid: number | null, key: string): DownloadState | null {
  const [state, setState] = useState<DownloadState | null>(null);
  const ask = useCallback(() => {
    const server = inApp ? appServer(rid) : null;
    if (!server) return;
    appApi.status(server, [key]).then((r) => setState(r[key] ?? null)).catch(() => {});
  }, [rid, key]);
  useEffect(() => {
    ask();
    window.addEventListener(DOWNLOADS_CHANGED, ask);
    return () => window.removeEventListener(DOWNLOADS_CHANGED, ask);
  }, [ask]);
  return state;
}

const pct = (s: DownloadState) => `${Math.floor(s.progress * 100)}%`;

function label(s: DownloadState | null, what: string): string {
  switch (s?.state) {
    case "queued": return "Waiting to download";
    case "downloading": return `Downloading ${pct(s)}`;
    case "paused": return "Waiting for Wi-Fi";
    case "failed": return "Download failed: try again";
    case "done": return "Downloaded";
    default: return `Download${what}`;
  }
}

/** Download a title, season, show, album, artist or playlist to the phone (Android app only).
 *  `what`: added to the label (" season"); `audio`: the file's audio codecs, to warn when the phone can't play
 *  them offline; `small`: an icon button for episode and track rows. */
export function DownloadButton({ kind = "item", id, title, what = "", audio, small }: {
  kind?: "item" | "playlist" | "user_playlist"; id: number; title: string; what?: string;
  audio?: (string | null | undefined)[]; small?: boolean;
}) {
  const { user } = useAuth();
  const { rid, remote } = useScope();
  const key = downloadKey(kind, id);
  const state = useDownloadState(rid, key);
  const info = useAppInfo();
  const [asking, setAsking] = useState<"remove" | "audio" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  // this server says whether we may; another server answers when the app asks it
  if (!inApp || (rid === null && !user.can_download) || (rid !== null && !remote?.signed_in)) return null;

  const server = appServer(rid);
  const path = { item: `/api/items/${id}/download`, playlist: `/api/playlists/${id}/download`,
    user_playlist: `/api/user-playlists/${id}/download` }[kind];
  const silent = audio ? unplayableAudio(info, audio) : [];
  const start = () => {
    setAsking(null);
    setErr(null);
    if (server) appApi.download(server, key, path, title).catch((e) => setErr(e.message));
  };
  const remove = () => {
    setAsking(null);
    if (server) appApi.remove(server, key).catch((e) => setErr(e.message));
  };
  const click = (e: MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (state?.within) return;  // part of a bigger download: removed with it
    const s = state?.state ?? "none";
    if (s === "none" || s === "failed") {
      if (silent.length && s === "none") setAsking("audio");
      else start();
    } else setAsking("remove");
  };
  const done = state?.state === "done";
  const busy = state?.state === "downloading" || state?.state === "queued" || state?.state === "paused";
  const text = state?.within ? "Downloaded (with the rest)" : label(state, what);

  const confirm = asking && (
    <span className="confirm download-confirm" onClick={(e) => { e.preventDefault(); e.stopPropagation(); }}>
      {asking === "audio"
        ? <>This phone can't play its {silent.join("/")} sound, so offline it plays without sound. Download anyway?</>
        : done ? <>Remove {title} from this phone?</> : <>Stop downloading {title}?</>}
      <button className={`btn ghost small ${asking === "remove" ? "danger" : ""}`}
        onClick={asking === "audio" ? start : remove}>{asking === "audio" ? "Download" : done ? "Remove" : "Stop"}</button>
      <button className="btn ghost small" onClick={() => setAsking(null)}>Cancel</button>
    </span>
  );

  if (small) {
    return (
      <>
        <button className={`icon-btn subtle download-toggle ${done ? "on" : ""} ${busy ? "busy" : ""}`} onClick={click}
          title={text} aria-label={`${text}: ${title}`}>
          {busy ? <span className="download-pct">{state?.state === "downloading" ? pct(state) : "…"}</span>
            : <Icon name={done ? "check" : "download"} size={16} />}
        </button>
        {confirm}
        {err && <span className="key-msg bad">{err}</span>}
      </>
    );
  }
  return (
    <>
      <button className={`btn ghost ${done ? "on" : ""}`} onClick={click} title={state?.error ?? undefined}
        disabled={!!state?.within}>
        <Icon name={done ? "check" : "download"} /> {text}
      </button>
      {confirm}
      {err && <p className="key-msg bad">{err}</p>}
    </>
  );
}
