import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    // Native file events were being missed on Windows (edits not picked up, stale modules served),
    // so poll instead. Cheap at this project size.
    watch: { usePolling: true, interval: 250 },
    // the BAMS server (python -m bams serve)
    proxy: { "/api": "http://127.0.0.1:8484" },
  },
});
