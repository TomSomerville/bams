import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

// Tizen runs the app from file://, where module scripts don't load (no CORS origin). So the build is one classic
// script (IIFE, dynamic imports inlined) loaded with `defer`, and Tizen 6.5's Chromium (85) gets ES2019.
function classicScript(): Plugin {
  return {
    name: "bams-classic-script",
    apply: "build",
    enforce: "post",
    transformIndexHtml(html) {
      return html
        .replace(/<script type="module" crossorigin/g, "<script defer")
        .replace(/<link rel="modulepreload"[^>]*>/g, "")
        .replace(/ crossorigin/g, "");
    },
  };
}

export default defineConfig({
  base: "./",
  plugins: [react(), classicScript()],
  build: {
    target: "es2019",
    modulePreload: false,
    cssCodeSplit: false,
    assetsInlineLimit: 0,
    rollupOptions: { output: { format: "iife", inlineDynamicImports: true } },
  },
  server: { port: 5174, host: true, watch: { usePolling: true, interval: 250 } },
});
