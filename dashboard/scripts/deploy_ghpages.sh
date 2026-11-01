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
#   bash scripts/deploy_ghpages.sh --with-review         # 週次タスク: 振り返りの下書きも一緒に残す
#
# --with-review:
#   dashboard/data/review_draft.json（振り返りの下書き・gitignore）を
#   dashboard/reviews/<written_on>.json として、docs/index.html と同じコミットで main に入れる。
#   review_inputs.py check を通らない下書きは入れずに止まる。
#   下書きを週次 worktree の中で追跡しないのは、翌週の `git merge --ff-only origin/main` と
#   ぶつけないため（追跡するファイルは、この一時 worktree からしか書かない）。
#
# 特徴:
#   - main の作業ツリーには触れず、一時 worktree で docs/index.html だけを
#     差し替えて push するので、編集中の変更を巻き込まない。
#   - 既存の docs/<日付> 投稿プレビューページには影響しない（ルートのみ更新）。
set -euo pipefail

DASH_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(git -C "$DASH_DIR" rev-parse --show-toplevel)"
BUILT="$DASH_DIR/dist/index.html"
DRAFT="$DASH_DIR/data/review_draft.json"

WITH_REVIEW=0
for arg in "$@"; do
  case "$arg" in
    --with-review) WITH_REVIEW=1 ;;
    *) echo "❌ 不明な引数: $arg" >&2; exit 1 ;;
  esac
done

if [ ! -f "$BUILT" ]; then
  echo "❌ $BUILT がありません。先に 'cd dashboard && npm run build' を実行してください。" >&2
  exit 1
fi

REVIEW_ON=""
if [ "$WITH_REVIEW" = 1 ]; then
  if [ ! -f "$DRAFT" ]; then
    echo "❌ 振り返りの下書きがありません: $DRAFT" >&2
    exit 1
  fi
  if ! /usr/bin/python3 "$DASH_DIR/review_inputs.py" check "$DRAFT"; then
    echo "❌ 振り返りの下書きがチェックを通りません（上の ✗ を直してから、ビルドと公開をやり直す）" >&2
    exit 1
  fi
  REVIEW_ON="$(/usr/bin/python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["written_on"])' "$DRAFT")"
fi

TMP="$(mktemp -d)"
cleanup() { git -C "$REPO_ROOT" worktree remove --force "$TMP" 2>/dev/null || true; rm -rf "$TMP"; }
trap cleanup EXIT

git -C "$REPO_ROOT" fetch origin main -q
git -C "$REPO_ROOT" worktree add --detach "$TMP" origin/main >/dev/null 2>&1

mkdir -p "$TMP/docs"
cp "$BUILT" "$TMP/docs/index.html"
git -C "$TMP" add docs/index.html
if [ -n "$REVIEW_ON" ]; then
  mkdir -p "$TMP/dashboard/reviews"
  cp "$DRAFT" "$TMP/dashboard/reviews/$REVIEW_ON.json"
  git -C "$TMP" add "dashboard/reviews/$REVIEW_ON.json"
fi

if git -C "$TMP" diff --cached --quiet; then
  echo "変更なし（公開中の内容と同一）。デプロイをスキップします。"
  exit 0
fi

git -C "$TMP" commit -q -m "deploy: ダッシュボード更新 $(date +%Y-%m-%d)${REVIEW_ON:+（振り返り $REVIEW_ON）}"
git -C "$TMP" push origin HEAD:main >/dev/null 2>&1
echo "✅ デプロイ完了。数分後に反映されます: https://spikesukeshun.github.io/miki-instagram/"
