import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Relative base so the build works from any path (GitHub Pages serves it under /Yantraa/).
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: { chunkSizeWarningLimit: 900 }, // the demo data is bundled on purpose
});
