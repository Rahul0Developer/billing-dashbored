import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Apex POS React SPA — dev server proxies /api to FastAPI (port 8000).
export default defineConfig({
  plugins: [react()],
  base: "/app/",
  build: { outDir: "dist", sourcemap: false },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
