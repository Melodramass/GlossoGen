import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

/**
 * Pure functions use Node by default. Component regressions opt into jsdom
 * with a per-file environment annotation; these do not replace browser profiling.
 */
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
