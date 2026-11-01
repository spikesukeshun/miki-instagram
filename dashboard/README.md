# Instagram 週次の振り返りダッシュボード

エステサロンMIKIのInstagram運用（週3投稿）を、**前回の結果 → 次に試すこと → どの投稿のどこに入れたか →
ご本人の修正 → 投稿された内容での結果と判定** の1本の線で見るためのページ。
自己完結型の単一HTMLページ（外部通信なし）。2026-11 に9セクションから5セクションへ作り直した。

- **公開URL**: https://spikesukeshun.github.io/miki-instagram/
  - GitHub Pages（`main` ブランチの `docs/index.html`）でホスティング。閲覧にログイン不要・スマホ対応。
  - ⚠️ 公開Web（誰でもURLで閲覧可・noindex）。修正依頼の文・投稿メモ・キャプションの本文は載せない。
    予定の投稿は、表紙タイトル・試すこと（反映した箇所の文言を含む）・プレビューへのリンクを出す
    （プレビューページ自体も公開リポジトリの docs/ にある）。

## 画面の5セクション

| # | セクション | 中身 |
|---|---|---|
| 01 | 先週のまとめ | 振り返りの要約と、確定した先週の4つの数字（届いた人・保存・プロフィールを見た人・LPに来た人）を「いつもの範囲」と並べる |
| 02 | 振り返り | 判定できる投稿ごとの「試したこと → 結果 → 判定」、施策の通算、いまの標準・やめたこと、人の修正 |
| 03 | 今週の投稿と狙い | 次に試すことと、それを入れた予定の投稿（修正後の最新の内容） |
| 04 | LP（予約導線） | プロフィール → リンクのタップ → LP → しっかり見た → 予約ボタンの流れと、来た人の内訳（Instagram経由のみ） |
| 05 | 投稿の成績 | 直近9本の数字・試したこと・修正の有無（固定文の助言は出さない） |

判定の考え方（正は `review_inputs.py` の定数）:
- 判定は投稿から `MATURE_DAYS` 日たってから。それまでは「集計中」
- 「いつもの範囲」は直近の確定した投稿（週の数字は直近の週）の真ん中半分。増減の%は出さない
  （小さな数の%は大きく揺れて、毎週「低下」と出てしまっていた）
- 保存・プロフィールは率（÷届いた人）で比べる

## 毎週の更新（週次タスク）

手順の正は週次タスクの手順書 `~/.claude/scheduled-tasks/weekly-dashboard-update/SKILL.md`。流れだけ:

```bash
/usr/bin/python3 dashboard/fetch_dashboard_data.py               # 1. データ取得（約2分）
/usr/bin/python3 dashboard/review_inputs.py digest               # 2. 振り返りの材料を読む
#    → Claude が dashboard/data/review_draft.json を書く
/usr/bin/python3 dashboard/review_inputs.py check                # 3. 下書きの機械チェック
#    4. 翌週の投稿を作る（content.json の trial に「次に試すこと」を1本につき1つ）
/usr/bin/python3 dashboard/fetch_dashboard_data.py --local-only  # 5. シート・記録・振り返りを読み直す
(cd dashboard && npm run build)                                  # 6. ビルド
(cd dashboard && bash scripts/deploy_ghpages.sh --with-review)   # 7. 公開（振り返りも main に残す）
```

`deploy_ghpages.sh` は `main` の作業ツリーに触れず、一時 worktree で `docs/index.html`（と
`--with-review` のとき `dashboard/reviews/<日付>.json`）だけを差し替えて push する。
既存の `docs/<日付>` 投稿プレビューページには影響しない。

## 構成

```
dashboard/
├── fetch_dashboard_data.py   # Graph API → data/dashboard_data.json（--local-only はAPIを呼ばない）
├── fetch_ga4_data.py         # LP の GA4 / Search Console（未設定・失敗でも止めない）
├── review_inputs.py          # 数字の計算（derived）・digest・振り返りの check。画面はこの数字を表示するだけ
├── reviews/<日付>.json        # 振り返りの履歴（deploy_ghpages.sh --with-review がコミットする）
├── data/
│   ├── dashboard_data.json   # データスナップショット（ビルド時に必要な項目だけ埋め込み）
│   ├── review_draft.json     # 振り返りの下書き（gitignore）
│   └── theme_overrides.json  # テーマ分類の手動上書き（main repo 側とマージ。重複は main repo 優先）
├── scripts/                  # deploy_ghpages.sh / make_artifact.mjs
└── src/
    ├── config.ts             # テーマの表示名と色
    ├── types.ts              # derived の型
    └── components/           # Summary / Review / Upcoming / LpSection / PostTable
```

データの出どころ:
- 試すこと: content.json の `trial`（`rules/content-schema.md`）。項目の正は `review_post.py` の `TRIAL_LEVERS`
- 修正の記録: `review_post.py` が校閲を通すたびに `.git/content_history/<枠>.json` に追記（`content_baseline.py`）。
  週次タスクは `--origin weekly` で校閲し、その最後の版を「自動作成版」とする
- シート: ステータス・予定日時・プレビューURL と、キャプションの指紋（本文は載せない）。
  指紋で Instagram の投稿と突き合わせ、シートやアプリでの直接の書き換えも見つける

## API仕様メモ（2026-07実測）

- `impressions` は v22+ で廃止 → `views` を使用
- FEED系は全メトリクスを1コールで取得可、VIDEO（リール）は `profile_visits`/`follows` 非対応
- アカウントの `follower_count` 日次は直近30日のみ
- `metric_type=total_value` なら `profile_views`・`website_clicks`（プロフィールのリンクのタップ）の合計を過去の週でも取得可能
- GA4 のコース別（`customEvent:course`）は、GA4 の管理画面でカスタムディメンション（範囲: イベント）に
  登録した日以降の分しか取れない。未登録のあいだは画面に「未登録」と出る
