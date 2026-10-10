import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, getServer, getToken, hello, refreshTicket, savedUser, setSession, SIGNED_OUT, type User } from "./api";
import type { ServerLibrary } from "../../web/src/api";
import { keyHandler } from "./keys";
import { currentFid, focusFirst, focusId, move, type Dir } from "./nav";
import { exitApp, isBack, KEY, registerKeys } from "./tizen";
import Connect from "./screens/Connect";
import Link from "./screens/Link";
import Home from "./screens/Home";
import Library from "./screens/Library";
import Detail from "./screens/Detail";
import Player from "./screens/Player";
import Search from "./screens/Search";
import Settings from "./screens/Settings";
import Rail from "./Rail";

export type Route =
  | { name: "home" }
  | { name: "library"; id: number }
  | { name: "detail"; id: number }
  | { name: "player"; id: number; resume: boolean }
  | { name: "search" }
  | { name: "settings" };

type Entry = { route: Route; fid: string | null; key: number };

type Nav = {
  route: Route;
  push: (r: Route) => void;
  replace: (r: Route) => void;
  /** the rail: start over from this screen */
  reset: (r: Route) => void;
  back: () => void;
  user: User | null;
  libraries: ServerLibrary[];
  signOut: () => void;
  changeServer: () => void;
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
    setTimeout(() => {
      const main = document.querySelector("main") ?? document;
      if (!focusId(fid)) focusFirst(main);
    });
  }, [ready, fid]);
}

type Phase = "start" | "connect" | "link" | "main";

let keyCounter = 0;

export default function App() {
  const [phase, setPhase] = useState<Phase>("start");
  const [user, setUser] = useState<User | null>(savedUser());
  const [libraries, setLibraries] = useState<ServerLibrary[]>([]);
  const [stack, setStack] = useState<Entry[]>([{ route: { name: "home" }, fid: null, key: 0 }]);
  const [fatal, setFatal] = useState<string | null>(null);

  // where to start: no server -> Connect; no token -> Link; else check both still work
  const start = useCallback(async () => {
    setFatal(null);
    const server = getServer();
    if (!server) return setPhase("connect");
    if (!getToken()) {
      return setPhase((await hello(server)) ? "link" : "connect");
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
      setStack([{ route: { name: "home" }, fid: null, key: ++keyCounter }]);
      setPhase("main");
    } catch (e) {
      setFatal((e as Error).message);
    }
  }, []);

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
      signOut: () => {
        void api.post("/api/auth/logout").catch(() => undefined);
        setSession(null);
        setPhase("link");
      },
      changeServer: () => setPhase("connect"),
    };
  }, [stack, user, libraries]);

  // the remote: the screen's own handler first (the player), then Back and the arrows
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const h = keyHandler();
      if (h && h(e)) {
        e.preventDefault();
        return;
      }
      if (isBack(e)) {
        e.preventDefault();
        if (phase === "main") nav.back();
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
  }, [nav, phase]);

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
  if (phase === "link") return <Link onLinked={() => void start()} onChangeServer={() => setPhase("connect")} />;

  const top = stack[stack.length - 1];
  const r = top.route;
  return (
    <NavCtx.Provider value={nav}>
      <ScreenCtx.Provider value={{ fid: top.fid }} key={top.key}>
        {r.name === "player" ? (
          <Player key={`${r.id}`} id={r.id} resume={r.resume} />
        ) : (
          <div className="shell">
            <Rail />
            <main className="content" data-scroll>
              {r.name === "home" && <Home />}
              {r.name === "library" && <Library id={r.id} />}
              {r.name === "detail" && <Detail id={r.id} />}
              {r.name === "search" && <Search />}
              {r.name === "settings" && <Settings />}
            </main>
          </div>
        )}
      </ScreenCtx.Provider>
    </NavCtx.Provider>
  );
}
