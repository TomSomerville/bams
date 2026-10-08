import { Route, Routes, useLocation } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import ConfigBanner from "./components/ConfigBanner";
import NowPlaying from "./components/NowPlaying";
import { useMusic } from "./music";
import Home from "./pages/Home";
import Library from "./pages/Library";
import Detail from "./pages/Detail";
import { PlaylistPage } from "./pages/Music";
import Player from "./pages/Player";
import Search from "./pages/Search";
import Settings from "./pages/Settings";
import { useEffect } from "react";

export default function App() {
  const { pathname } = useLocation();
  const music = useMusic();
  const watching = pathname.startsWith("/play/");
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  // Starting a video pauses the music.
  const { pause } = music;
  useEffect(() => {
    if (watching) pause();
  }, [watching, pause]);

  // The player takes the whole screen, no chrome.
  if (watching) {
    return (
      <Routes>
        <Route path="/play/:id" element={<Player />} />
      </Routes>
    );
  }

  return (
    <div className={`shell ${music.current ? "has-np" : ""}`}>
      <Sidebar />
      <div className="main">
        <ConfigBanner />
        <TopBar />
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/library/:id" element={<Library />} />
          <Route path="/title/:id" element={<Detail />} />
          <Route path="/playlist/:id" element={<PlaylistPage />} />
          <Route path="/search" element={<Search />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<div className="page"><h1>Nothing here</h1></div>} />
        </Routes>
      </div>
      <NowPlaying />
    </div>
  );
}
