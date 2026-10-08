import { Route, Routes, useLocation } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import Home from "./pages/Home";
import Library from "./pages/Library";
import Detail from "./pages/Detail";
import Player from "./pages/Player";
import Search from "./pages/Search";
import Settings from "./pages/Settings";
import { useEffect } from "react";

export default function App() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  // The player takes the whole screen, no chrome.
  if (pathname.startsWith("/play/")) {
    return (
      <Routes>
        <Route path="/play/:id" element={<Player />} />
      </Routes>
    );
  }

  return (
    <div className="shell">
      <Sidebar />
      <div className="main">
        <TopBar />
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/movies" element={<Library type="movie" />} />
          <Route path="/tv" element={<Library type="show" />} />
          <Route path="/title/:id" element={<Detail />} />
          <Route path="/search" element={<Search />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<div className="page"><h1>Nothing here</h1></div>} />
        </Routes>
      </div>
    </div>
  );
}
