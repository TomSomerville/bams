import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "@fontsource-variable/montserrat";
import "./styles.css";
import App from "./App";
import { AuthProvider } from "./auth";
import { MusicProvider } from "./music";
import { VideoQueueProvider } from "./random";
import { RemotesProvider } from "./servers";
import { SettingsProvider } from "./settings";
import { inApp } from "./android";
import { START_THEATRE } from "./components/TheatreSettings";

// "Start in theatre mode on this browser" (Settings → This browser): the start page goes to the TV screens, unless
// the address says ?web
try {
  if (!inApp && location.pathname === "/" && !new URLSearchParams(location.search).has("web")
      && localStorage.getItem(START_THEATRE) === "1") location.replace("/theatre/");
} catch { /* storage unavailable */ }

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <SettingsProvider>
          <RemotesProvider>
            <MusicProvider>
              <VideoQueueProvider>
                <App />
              </VideoQueueProvider>
            </MusicProvider>
          </RemotesProvider>
        </SettingsProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
