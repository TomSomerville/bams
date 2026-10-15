import { createRoot } from "react-dom/client";
import "@fontsource-variable/montserrat";
import "./styles.css";
import App from "./App";
import { MusicProvider } from "./music";
import { pc } from "./platform";
import { installPcKeys } from "./pckeys";
import { installPointer } from "./pointer";
import { installScaling } from "./scale";

// a PC (theatre mode, development): any window size, PC/remote keys, the mouse (the TVs need none of it)
if (pc()) {
  installScaling();
  installPcKeys();
  installPointer();
}

// the music player sits above the app: it keeps playing across screens (and phases)
createRoot(document.getElementById("root")!).render(<MusicProvider><App /></MusicProvider>);
