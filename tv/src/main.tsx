import { createRoot } from "react-dom/client";
import "@fontsource-variable/montserrat";
import "./styles.css";
import App from "./App";
import { MusicProvider } from "./music";

// the music player sits above the app: it keeps playing across screens (and phases)
createRoot(document.getElementById("root")!).render(<MusicProvider><App /></MusicProvider>);
