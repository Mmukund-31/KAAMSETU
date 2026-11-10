/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// In development the app calls /api/... on its own origin and Vite forwards it to the backend,
// so no CORS setup is needed. KAAMSETU's API runs on 8001 on the dev machine (8000 is taken).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const target = env.VITE_PROXY_TARGET || "http://localhost:8001";
  return {
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: { "/api": { target, changeOrigin: true } },
    },
    build: {
      rollupOptions: {
        output: {
          // charts are only needed on Analytics; keep them out of the first load
          manualChunks: {
            react: ["react", "react-dom", "react-router-dom"],
            query: ["@tanstack/react-query"],
            charts: ["recharts"],
          },
        },
      },
    },
    preview: { port: 4173, proxy: { "/api": { target, changeOrigin: true } } },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      css: false,
      restoreMocks: true,
      coverage: {
        provider: "v8",
        include: ["src/**"],
        // type-only and entry files have no logic to cover
        exclude: ["src/test/**", "src/types/**", "src/main.tsx", "src/vite-env.d.ts"],
        reporter: ["text-summary", "text"],
      },
    },
  };
});
