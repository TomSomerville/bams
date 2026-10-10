import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "@fontsource-variable/montserrat";
import "./styles.css";
import App from "./App";
import { AuthProvider } from "./auth";
import { MusicProvider } from "./music";
import { RemotesProvider } from "./servers";
import { SettingsProvider } from "./settings";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <SettingsProvider>
          <RemotesProvider>
            <MusicProvider>
              <App />
            </MusicProvider>
          </RemotesProvider>
        </SettingsProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
