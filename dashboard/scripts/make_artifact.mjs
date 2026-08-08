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

const pickAll = (re, label) => {
  const m = [...html.matchAll(re)].map((x) => x[0]);
  if (!m.length) throw new Error(`${label} が dist/index.html に見つかりません`);
  return m;
};

const title = pickAll(/<title>[\s\S]*?<\/title>/g, "<title>")[0];
const style = pickAll(/<style[\s\S]*?<\/style>/g, "<style>").join("\n");
const scripts = pickAll(/<script type="module"[\s\S]*?<\/script>/g, "<script>");
if (scripts.length !== 1) {
  throw new Error(`インラインscriptが${scripts.length}個あります（1個を想定。lazyマッチの取りこぼし注意）`);
}
const script = scripts[0];

const fragment = `${title}
${style}
<div id="root"></div>
${script}
`;

writeFileSync(join(dist, "artifact.html"), fragment);
console.log(`✅ dist/artifact.html (${(fragment.length / 1024).toFixed(0)} KB)`);
