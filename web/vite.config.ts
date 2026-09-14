import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL(".", import.meta.url));
const apiTarget = process.env.NLM_API_PROXY || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(root, "./src"),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // Chat SSE can stay open for a long time — disable proxy timeouts.
      "/api": {
        target: apiTarget,
        changeOrigin: true,
        timeout: 0,
        proxyTimeout: 0,
      },
      "/health": {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "../web-static",
    emptyOutDir: true,
    assetsDir: "assets",
  },
});
