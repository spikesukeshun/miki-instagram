#!/usr/bin/env bash
#
# deploy_ghpages.sh
# ────────────────────────────────────────────────────
# ビルド済み dist/index.html を GitHub Pages（main ブランチの docs/index.html）に
# 反映して公開URLを最新化する。
#
#   公開URL: https://spikesukeshun.github.io/miki-instagram/
#
# 使い方（毎週の更新時）:
#   /usr/bin/python3 dashboard/fetch_dashboard_data.py   # データ再取得
#   cd dashboard && npm run build                        # 再ビルド
#   bash scripts/deploy_ghpages.sh                       # 公開URLへ反映
#
# 特徴:
#   - main の作業ツリーには触れず、一時 worktree で docs/index.html だけを
#     差し替えて push するので、編集中の変更を巻き込まない。
#   - 既存の docs/<日付> 投稿プレビューページには影響しない（ルートのみ更新）。
set -euo pipefail

DASH_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(git -C "$DASH_DIR" rev-parse --show-toplevel)"
BUILT="$DASH_DIR/dist/index.html"

if [ ! -f "$BUILT" ]; then
  echo "❌ $BUILT がありません。先に 'cd dashboard && npm run build' を実行してください。" >&2
  exit 1
fi

TMP="$(mktemp -d)"
cleanup() { git -C "$REPO_ROOT" worktree remove --force "$TMP" 2>/dev/null || true; rm -rf "$TMP"; }
trap cleanup EXIT

git -C "$REPO_ROOT" fetch origin main -q
git -C "$REPO_ROOT" worktree add --detach "$TMP" origin/main >/dev/null 2>&1

mkdir -p "$TMP/docs"
cp "$BUILT" "$TMP/docs/index.html"
git -C "$TMP" add docs/index.html

if git -C "$TMP" diff --cached --quiet; then
  echo "変更なし（公開中の内容と同一）。デプロイをスキップします。"
  exit 0
fi

git -C "$TMP" commit -q -m "deploy: ダッシュボード更新 $(date +%Y-%m-%d)"
git -C "$TMP" push origin HEAD:main >/dev/null 2>&1
echo "✅ デプロイ完了。数分後に反映されます: https://spikesukeshun.github.io/miki-instagram/"
