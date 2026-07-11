import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// Claude Artifact は外部リクエスト不可（CSP）のため、
// すべてのJS/CSS/データを単一HTMLにインライン化する
export default defineConfig({
  plugins: [react(), tailwindcss(), viteSingleFile()],
  build: {
    target: "es2020",
    chunkSizeWarningLimit: 4000,
  },
});
