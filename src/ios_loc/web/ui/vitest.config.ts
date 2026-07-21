import path from "node:path"
import { defineConfig } from "vitest/config"

// Pure-logic tests only -- no jsdom, no component rendering (see the plan's
// global constraints). The default `node` environment is deliberate.
export default defineConfig({
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  test: {
    include: ["src/**/*.test.ts"],
    environment: "node",
  },
})
