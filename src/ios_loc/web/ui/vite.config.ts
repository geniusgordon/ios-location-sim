import path from "node:path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

// The Python package serves ../static, so that is where the build lands.
// In dev, /api and /ws proxy to `uv run ios-loc gui` on 9876.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  build: {
    outDir: "../static",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:9876",
      "/ws": { target: "ws://127.0.0.1:9876", ws: true },
    },
  },
})
