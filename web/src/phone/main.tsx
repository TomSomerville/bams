import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter } from "react-router-dom";
import "@fontsource-variable/montserrat";
import "../styles.css";
import App from "./App";

// The Android app's own pages (android/: assets/app, https://appassets.androidplatform.net/app/). Hash routes:
// the app opens #/downloads, #/servers or #/start.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <HashRouter>
      <App />
    </HashRouter>
  </StrictMode>,
);
