import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { addExtra, api, checkExtras, extras, getServer, getToken, hello, nextAccount, otherAccounts, stashAccount, switchAccount, refreshTicket, renewTickets, savedUser, setSession, SIGNED_OUT, withFreshTicket, type Extra, type User } from "./api";
import type { ServerLibrary } from "../../web/src/api";
import { okDown, okUp } from "./hold";
import { keyHandler } from "./keys";
import { currentFid, move, settleFocus, type Dir } from "./nav";
import { exitApp, isBack, KEY, registerKeys } from "./tizen";
import { HOME, SEARCH } from "./pckeys";
import { pc, session, theatre } from "./platform";
import Connect from "./screens/Connect";
import Link from "./screens/Link";
import Home from "./screens/Home";
import Library from "./screens/Library";
import Detail from "./screens/Detail";
import Player from "./screens/Player";
import Search from "./screens/Search";
import Settings from "./screens/Settings";
import Watchlist from "./screens/Watchlist";
import Accounts from "./screens/Accounts";
import HolidayScreen from "./screens/Holiday";
import Rail from "./Rail";
import { useMusic } from "./music";
import { NowPlaying, PlaylistScreen, UserPlaylistScreen } from "./screens/Music";

export type Route =
  | { name: "home" }
  | { name: "watchlist" }
  // every movie and episode about the upcoming / recent holiday (a Home holiday row's "See all")
  | { name: "holiday"; which: "next" | "recent" }
  | { name: "library"; id: number; rid?: number }
  | { name: "detail"; id: number; rid?: number }
  // sleep: sleep mode's count of episodes still to play after this one (Player.tsx), carried to the next episode
  | { name: "player"; id: number; resume: boolean; rid?: number; sleep?: number }
  | { name: "playlist"; id: number; rid?: number }
  | { name: "my-playlist"; id: number; rid?: number }
  | { name: "search" }
  | { name: "settings" }
  // theatre mode: the accounts signed in on this PC (Switch account)
  | { name: "accounts" };

type Entry = { route: Route; fid: string | null; key: number };

type Nav = {
  route: Route;
  /** the screen at the bottom of the stack: the rail section this screen was reached from */
  root: Route;
  push: (r: Route) => void;
  replace: (r: Route) => void;
  /** the rail: start over from this screen */
  reset: (r: Route) => void;
  back: () => void;
  user: User | null;
  libraries: ServerLibrary[];
  /** the other BAMS servers on this TV (its own list, api.ts): state null = answered, else why not */
  servers: (Extra & { state: string | null })[];
  /** after adding/removing a server or changing which libraries show: read the list again, ask each server */
  reloadServers: () => void;
  /** add a server: find it, then link this TV to an account there (`again`: link one on the list again) */
  addServer: (again?: { url: string; name: string }) => void;
  signOut: () => void;
  changeServer: () => void;
  /** theatre mode: sign another account in on this PC (the current one stays signed in), or switch to one */
  addAccount: () => void;
  switchAccount: (userId: number) => void;
};

const NavCtx = createContext<Nav | null>(null);
export const useNav = () => useContext(NavCtx)!;

const ScreenCtx = createContext<{ fid: string | null }>({ fid: null });

/** Call once a screen's content is on the page: puts the focus back where it was (coming back to this screen), or
 *  on [data-autofocus] / the first thing (arriving fresh). */
export function useFocusOnReady(ready: boolean) {
  const { fid } = useContext(ScreenCtx);
  const done = useRef(false);
  useEffect(() => {
    if (!ready || done.current) return;
    done.current = true;
    // keeps trying while the content arrives (Home's shelves load after the page is "ready")
    return settleFocus(fid, () => document.querySelector("main"));
  }, [ready, fid]);
}

type Phase = "start" | "connect" | "link" | "main";

let keyCounter = 0;

export default function App() {
  const [phase, setPhase] = useState<Phase>("start");
  const [user, setUser] = useState<User | null>(savedUser());
  const [libraries, setLibraries] = useState<ServerLibrary[]>([]);
  const [servers, setServers] = useState<Nav["servers"]>([]);
  const states = useRef<Record<number, string | null>>({});
  // the list now (as last seen), then again once each server answered (a few seconds at most when one is offline)
  const reloadServers = useCallback(() => {
    const show = () => setServers(extras().map((e) => ({ ...e, state: e.token ? states.current[e.id] ?? null : "signed out" })));
    show();
    void checkExtras().then((s) => { states.current = s; show(); });
  }, []);
  const [adding, setAdding] = useState<{ url: string; name: string } | "find" | null>(null);
  const [stack, setStack] = useState<Entry[]>([{ route: { name: "home" }, fid: null, key: 0 }]);
  const music = useMusic();
  // a video starting pauses the music (like the web)
  const watching = stack[stack.length - 1].route.name === "player";
  const { pause } = music;
  useEffect(() => {
    if (watching) pause();
  }, [watching, pause]);
  const [fatal, setFatal] = useState<string | null>(null);

  // where to start: no server -> Connect; no token -> Link; else check both still work
  const start = useCallback(async () => {
    setFatal(null);
    const server = getServer();
    if (!server) return setPhase("connect");
    if (!getToken()) {
      if (await hello(server)) return setPhase("link");
      // theatre mode: the server is the one the page came from; wait for it (the fatal screen retries) rather than
      // asking for another
      if (theatre()) return setFatal(`Waiting for the BAMS server at ${server.replace(/^https?:\/\//, "")}…`);
      return setPhase("connect");
    }
    try {
      const st = await api.get<{ user: User | null }>("/api/auth/state");
      if (!st.user) {
        setSession(null);
        return setPhase("link");
      }
      setUser(st.user);
      setSession(getToken(), st.user);
      await refreshTicket(true);
      setLibraries(await api.get<ServerLibrary[]>("/api/libraries"));
      reloadServers();  // not awaited: an offline server mustn't hold up the start
      setStack([{ route: { name: "home" }, fid: null, key: ++keyCounter }]);
      setPhase("main");
    } catch (e) {
      setFatal((e as Error).message);
    }
  }, [reloadServers]);

  useEffect(() => {
    registerKeys();
    void start();
  }, [start]);

  useEffect(() => {
    const out = () => {
      setSession(null);
      setPhase("link");
    };
    window.addEventListener(SIGNED_OUT, out);
    return () => window.removeEventListener(SIGNED_OUT, out);
  }, []);

  // On a PC the "can't reach the server" screen tries again by itself: a theatre box that came up before the server
  // or its Wi-Fi must get going without anyone pressing a key.
  useEffect(() => {
    if (!fatal || !pc()) return;
    const t = setTimeout(() => void start(), 5000);
    return () => clearTimeout(t);
  }, [fatal, start]);

  // Tickets die with a server restart (api.ts renewTickets): a picture that fails to load gets a fresh ticket and
  // one more try, and so does everything after the page was hidden (a TV or PC that slept).
  useEffect(() => {
    const onError = (e: Event) => {
      const img = e.target;
      if (!(img instanceof HTMLImageElement) || img.dataset.retried || !img.src.includes("/api/t/")) return;
      img.dataset.retried = "1";
      void renewTickets().then(() => {
        const url = withFreshTicket(img.src);
        if (url && url !== img.src) img.src = url;
      });
    };
    const onShow = () => {
      if (!document.hidden && getToken()) void renewTickets();
    };
    window.addEventListener("error", onError, true);  // a picture's error doesn't bubble: catch it on the way down
    document.addEventListener("visibilitychange", onShow);
    return () => {
      window.removeEventListener("error", onError, true);
      document.removeEventListener("visibilitychange", onShow);
    };
  }, []);

  // keep the media ticket fresh while the app stays open
  useEffect(() => {
    if (phase !== "main") return;
    const t = setInterval(() => void refreshTicket().catch(() => undefined), 30 * 60 * 1000);
    return () => clearInterval(t);
  }, [phase]);

  const nav = useMemo<Nav>(() => {
    const remember = (s: Entry[]) => s.map((e, i) => (i === s.length - 1 ? { ...e, fid: currentFid() } : e));
    return {
      route: stack[stack.length - 1].route,
      root: stack[0].route,
      push: (r) => setStack((s) => [...remember(s), { route: r, fid: null, key: ++keyCounter }]),
      replace: (r) => setStack((s) => [...s.slice(0, -1), { route: r, fid: null, key: ++keyCounter }]),
      reset: (r) => setStack([{ route: r, fid: null, key: ++keyCounter }]),
      back: () => setStack((s) => {
        if (s.length > 1) return s.slice(0, -1);
        if (s[0].route.name !== "home") return [{ route: { name: "home" }, fid: null, key: ++keyCounter }];
        exitApp();
        return s;
      }),
      user,
      libraries,
      servers,
      reloadServers,
      signOut: () => {
        void api.post("/api/auth/logout").catch(() => undefined);
        setSession(null);
        // theatre mode: another account signed in on this PC takes over
        if (theatre() && nextAccount()) void start();
        else setPhase("link");
      },
      addAccount: () => {
        stashAccount();
        setPhase("link");
      },
      switchAccount: (id) => {
        if (switchAccount(id)) void start();
      },
      changeServer: () => setPhase("connect"),
      addServer: (again) => setAdding(again ?? "find"),
    };
  }, [stack, user, libraries, servers, reloadServers, start]);

  // PC keys (pckeys.ts): Home, and Search (the Search key, or typing a letter outside a text box). On the Search
  // screen itself, Search.tsx takes the letters.
  useEffect(() => {
    if (phase !== "main" || adding) return;
    const home = () => nav.reset({ name: "home" });
    const search = (e: Event) => {
      if (nav.route.name === "search") return;
      const text = (e as CustomEvent<string>).detail;
      if (text) session.set("bams.q", text);
      if (nav.route.name === "player") nav.replace({ name: "search" });
      else nav.push({ name: "search" });
    };
    window.addEventListener(HOME, home);
    window.addEventListener(SEARCH, search);
    return () => {
      window.removeEventListener(HOME, home);
      window.removeEventListener(SEARCH, search);
    };
  }, [nav, phase, adding]);

  // the remote: the screen's own handler first (the player), then Back and the arrows
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const h = keyHandler();
      if (h && h(e)) {
        e.preventDefault();
        return;
      }
      // the remote's media keys, outside the video player: the music
      const mk = ({ [KEY.PLAY_PAUSE]: music.toggle, [KEY.PLAY]: music.toggle, [KEY.PAUSE]: music.pause,
        [KEY.NEXT]: music.next, [KEY.FF]: music.next, [KEY.PREV]: music.prev, [KEY.RW]: music.prev,
        [KEY.STOP]: music.stop } as Record<number, () => void>)[e.keyCode];
      if (mk && music.current) {
        e.preventDefault();
        mk();
        return;
      }
      if (isBack(e)) {
        e.preventDefault();
        if (adding) setAdding(null);  // adding a server: Back cancels it
        else if (phase === "main") nav.back();
        else if (phase === "start" || (phase === "connect" && !getServer())) exitApp();
        return;
      }
      const dir: Dir | undefined = ({ [KEY.LEFT]: "left", [KEY.RIGHT]: "right", [KEY.UP]: "up", [KEY.DOWN]: "down" } as Record<number, Dir>)[e.keyCode];
      if (dir) {
        const t = e.target as HTMLInputElement;
        if (t.tagName === "INPUT" && (dir === "left" || dir === "right")) {
          const atEdge = dir === "left" ? t.selectionStart === 0 : t.selectionEnd === t.value.length;
          if (!atEdge) return;  // moving the caret
        }
        e.preventDefault();
        move(dir);
        return;
      }
      if (e.keyCode === KEY.ENTER) {
        if (okDown(e)) {  // a card that can be held (hold.ts): pressed or held, it's decided there
          e.preventDefault();
          return;
        }
        const el = document.activeElement as HTMLElement | null;
        // OK presses the focused button ourselves (the same on every TV firmware; native activation is cancelled)
        if (el && (el.tagName === "BUTTON" || (el.tagName !== "INPUT" && el.hasAttribute("data-focus")))) {
          e.preventDefault();
          el.click();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [nav, phase, adding, music]);

  useEffect(() => {
    const up = (e: KeyboardEvent) => {
      if (e.keyCode === KEY.ENTER) okUp();
    };
    window.addEventListener("keyup", up);
    return () => window.removeEventListener("keyup", up);
  }, []);

  if (fatal) {
    return (
      <div className="center-screen">
        <img className="wordmark" src="bams-wordmark.png" alt="BAMS" />
        <p className="error big">{fatal}</p>
        <div className="button-row">
          <button className="btn primary" data-autofocus onClick={() => void start()} ref={(b) => b?.focus()}>Try again</button>
          <button className="btn" onClick={() => { setFatal(null); setPhase("connect"); }}>Change server</button>
        </div>
      </div>
    );
  }
  if (phase === "start") return <div className="center-screen"><div className="spinner" /></div>;
  if (phase === "connect") return <Connect onConnected={() => void start()} />;
  if (phase === "link") {
    // theatre mode, adding an account (or this one's session ended): back to one still signed in on this PC
    const back = theatre() ? otherAccounts()[0] : undefined;
    return <Link onLinked={() => void start()} onChangeServer={() => setPhase("connect")}
      back={back && { name: back.name, go: () => { if (nextAccount()) void start(); } }} />;
  }
  // adding another server (Settings): find it, then link this TV to an account there; Back cancels
  if (adding === "find") {
    return <Connect adding={{ onPick: (url, name) => setAdding({ url, name }), onCancel: () => setAdding(null) }} />;
  }
  if (adding) {
    return <Link key={adding.url} target={{ ...adding, onDone: (token, u) => {
      addExtra(adding.url, adding.name, token, u);
      setAdding(null);
      reloadServers();
    } }} onLinked={() => undefined} onChangeServer={() => setAdding("find")} />;
  }

  const top = stack[stack.length - 1];
  const r = top.route;
  return (
    <NavCtx.Provider value={nav}>
      <ScreenCtx.Provider value={{ fid: top.fid }} key={top.key}>
        {r.name === "player" ? (
          <Player key={`${r.rid ?? ""}-${r.id}`} id={r.id} rid={r.rid} resume={r.resume} sleep={r.sleep} />
        ) : (
          <div className={`shell ${music.current ? "has-np" : ""}`}>
            <Rail />
            <main className="content" data-scroll>
              {r.name === "home" && <Home />}
              {r.name === "watchlist" && <Watchlist />}
              {r.name === "holiday" && <HolidayScreen key={r.which} which={r.which} />}
              {r.name === "library" && <Library key={`${r.rid ?? ""}-${r.id}`} id={r.id} rid={r.rid} />}
              {r.name === "detail" && <Detail id={r.id} rid={r.rid} />}
              {r.name === "search" && <Search />}
              {r.name === "playlist" && <PlaylistScreen id={r.id} rid={r.rid} />}
              {r.name === "my-playlist" && <UserPlaylistScreen key={r.id} id={r.id} rid={r.rid} />}
              {r.name === "settings" && <Settings />}
              {r.name === "accounts" && <Accounts />}
            </main>
            <NowPlaying />
          </div>
        )}
      </ScreenCtx.Provider>
    </NavCtx.Provider>
  );
}
