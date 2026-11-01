import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// Claude Artifact は外部リクエスト不可（CSP）のため、
// すべてのJS/CSS/データを単一HTMLにインライン化する
export default defineConfig({
  plugins: [react(), tailwindcss(), viteSingleFile()],
  // JSON を ES モジュールの名前付き export として出す。embedded.ts が使う項目だけを
  // 取り込めば、使わない項目（全投稿の生データなど）はビルドから落ちる
  json: { stringify: false },
  build: {
    target: "es2020",
    chunkSizeWarningLimit: 4000,
  },
});
