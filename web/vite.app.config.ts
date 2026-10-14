import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The Android app's own pages (Downloads, Servers): `npm run build:app` -> dist-app, bundled into the APK by
// android/app/build.gradle.kts. They work with no server, so they're built separately from the server's web UI.
// Paths are relative to web/ (where npm runs), then to `root`.
export default defineConfig({
  root: "phone",
  base: "/app/",
  publicDir: "../public",
  plugins: [react()],
  build: { outDir: "../dist-app", emptyOutDir: true },
});
