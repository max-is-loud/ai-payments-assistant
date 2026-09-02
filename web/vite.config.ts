/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The repo-root .env is the single place OWNER_API_TOKEN lives; Vite reads it
// from envDir and exposes only the prefixes listed here to the browser bundle.
export default defineConfig({
  plugins: [react()],
  envDir: "..",
  envPrefix: ["VITE_", "OWNER_API_TOKEN"],
  server: {
    port: 5173,
    // Node may bind ::1-only for "localhost"; browsers fall back between ::1 and 127.0.0.1.
    host: "127.0.0.1",
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } },
  },
  test: { environment: "jsdom", include: ["src/**/*.test.{ts,tsx}"], setupFiles: ["src/test-setup.ts"] },
});
