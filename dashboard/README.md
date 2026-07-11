# Instagram AIマーケティングダッシュボード

エステサロンMIKIのInstagram運用（週3投稿）の意思決定を支援するダッシュボード。
Claude Artifact として公開する自己完結型の単一HTMLページ（外部通信なし）。

- **公開URL**: https://claude.ai/code/artifact/59ebc25f-9153-449f-b977-34666127b0c8
  （非公開Artifact。閲覧にはclaude.aiへのログインが必要。共有はページの共有メニューから）

## 毎週の更新手順

Claude Code に「**ダッシュボードを更新して**」と依頼すれば以下が自動実行される。
手動でやる場合：

```bash
# 1. Instagram Graph API から最新データを取得（~2分）
/usr/bin/python3 dashboard/fetch_dashboard_data.py

# 2. ビルド（型チェック + 単一HTML化 + Artifact用フラグメント生成）
cd dashboard && npm run build

# 3. Claude Code が dist/artifact.html を同じURLに再公開する
#    （このURLを維持するには、公開済みArtifactのURLを url パラメータで指定）
```

更新時に Claude Code が `data/dashboard_data.json` の `claude_comment` に
今週の所見を書き込むと、ダッシュボードの「AI分析」セクションに表示される。

## 構成

```
dashboard/
├── fetch_dashboard_data.py   # Graph API → data/dashboard_data.json
├── data/
│   ├── dashboard_data.json   # データスナップショット（ビルド時に埋め込み）
│   └── theme_overrides.json  # テーマ分類の手動上書き（media_id → theme）
├── scripts/make_artifact.mjs # dist/index.html → dist/artifact.html（Artifact用）
└── src/
    ├── config.ts             # スコア重み（★）・閾値・テーマ定義・ファネル係数
    ├── lib/analytics.ts      # 週次集計・投稿スコア(100点)・テーマ統計・ヒートマップ
    ├── lib/insights.ts       # ルールベースAI分析（根拠つき）
    ├── lib/strategy.ts       # 来週の投稿戦略エンジン
    └── components/           # 画面セクション①〜⑨
```

## スコア設計（ユーザー指定の重要度）

DMにつながらないリーチは価値が低い、という方針で星重み×自己分布の百分位で合成：

| ★5 | ★4 | ★3 | ★2 |
|---|---|---|---|
| プロフィール誘導率・保存率・フォロワー増加 | リーチ・インプレッション | コメント・いいね | シェア |

- DM率はAPI非提供のためスコア対象外（ファネルで手入力）
- 成功ライン: スコア60点以上

## API仕様メモ（2026-07実測）

- `impressions` は v22+ で廃止 → `views` を使用
- FEED系は全メトリクスを1コールで取得可、VIDEO（リール）は `profile_visits`/`follows` 非対応
- アカウントの `follower_count` 日次は直近30日のみ
- `metric_type=total_value` なら `profile_views` 等の合計を過去の週でも取得可能
- DM数・予約数はAPIで取得不可 → ダッシュボード内の手入力欄（localStorage・端末ごと）
