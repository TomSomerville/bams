import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "@fontsource-variable/montserrat";
import "./styles.css";
import App from "./App";
import { MusicProvider } from "./music";
import { SettingsProvider } from "./settings";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <SettingsProvider>
        <MusicProvider>
          <App />
        </MusicProvider>
      </SettingsProvider>
    </BrowserRouter>
  </StrictMode>,
);
