/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `vite --mode demo` runs the independent demo experience: its own port, proxied to the
// separate demo backend (port 8001), with the demo flag switched on at build time.
export default defineConfig(({ mode }) => {
  const demo = mode === "demo";
  const target = demo ? "http://127.0.0.1:8001" : "http://127.0.0.1:8000";
  return {
    plugins: [react()],
    define: demo ? { "import.meta.env.VITE_DEMO_MODE": JSON.stringify("1") } : {},
    build: demo ? { outDir: "dist-demo" } : {},
    server: {
      port: demo ? 5174 : 5173,
      proxy: { "/api": target, "/images": target },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      css: false,
    },
  };
});
