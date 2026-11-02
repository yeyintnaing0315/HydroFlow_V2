import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    extensions: [".mjs", ".mts", ".ts", ".tsx", ".jsx", ".js", ".json"],
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
      "/map-tiles/osm": {
        target: "https://tile.openstreetmap.org",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/map-tiles\/osm/, ""),
        headers: {
          "User-Agent": "HydroFlow/1.0 (academic flood-relief prototype)",
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    testTimeout: 20_000,
  },
});
