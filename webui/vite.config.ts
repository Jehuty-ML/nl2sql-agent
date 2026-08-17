import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:6010",
      "/health": "http://127.0.0.1:6010",
      "/download": "http://127.0.0.1:6010",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
