import { defineConfig } from "vite";

export default defineConfig({
  build: {
    outDir: "wireviz_gui/static/dist",
    emptyOutDir: true,
    rollupOptions: {
      input: "frontend/main.js",
      output: {
        entryFileNames: "app.js",
        assetFileNames: "app[extname]",
      },
    },
  },
});
