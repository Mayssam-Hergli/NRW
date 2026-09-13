import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// GitHub Pages serves a project page at https://<org>.github.io/<repo>/, so
// every asset URL needs that repo-name prefix baked in. This repo is
// Mayssam-Hergli/NRW -- if the Pages project is ever renamed or moved to a
// user/org root page, this is the one line that needs to change.
export default defineConfig({
  base: "/NRW/",
  plugins: [react()],
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
