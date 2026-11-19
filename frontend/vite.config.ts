// © 2026 Sidra Riaz Awan. All rights reserved.
import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";
import pkg from "./package.json";
import { COPYRIGHT_HOLDER, COPYRIGHT_NOTICE } from "./src/lib/legal";

/** Keeps the copyright notice in production output: HTML metadata + a legal comment banner on every JS chunk. */
function copyright(): Plugin {
  return {
    name: "undeclared-copyright",
    transformIndexHtml: () => [
      { tag: "meta", attrs: { name: "copyright", content: COPYRIGHT_NOTICE }, injectTo: "head" },
      { tag: "meta", attrs: { name: "author", content: COPYRIGHT_HOLDER }, injectTo: "head" },
    ],
    generateBundle(_opts, bundle) {
      for (const f of Object.values(bundle)) {
        if (f.type === "chunk") f.code = `/*! ${COPYRIGHT_NOTICE} */\n${f.code}`;
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), copyright()],
  define: { "import.meta.env.VITE_APP_VERSION": JSON.stringify(pkg.version) },
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.API_PROXY_TARGET ?? "http://localhost:8000", changeOrigin: false } },
  },
});
