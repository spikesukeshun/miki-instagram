/**
 * dist/index.html（vite-plugin-singlefile 出力の完全なHTML）から
 * Claude Artifact 用のフラグメント dist/artifact.html を作る。
 * Artifact は公開時に <!doctype>...<head>...<body> で包まれるため、
 * title / インラインstyle / #root / インラインscript だけを取り出す。
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const dist = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");
const html = readFileSync(join(dist, "index.html"), "utf8");

const pick = (re, label) => {
  const m = html.match(re);
  if (!m) throw new Error(`${label} が dist/index.html に見つかりません`);
  return m[0];
};

const title = pick(/<title>[\s\S]*?<\/title>/, "<title>");
const style = pick(/<style[\s\S]*?<\/style>/, "<style>");
const script = pick(/<script type="module"[\s\S]*<\/script>/, "<script>");

const fragment = `${title}
${style}
<div id="root"></div>
${script}
`;

writeFileSync(join(dist, "artifact.html"), fragment);
console.log(`✅ dist/artifact.html (${(fragment.length / 1024).toFixed(0)} KB)`);
