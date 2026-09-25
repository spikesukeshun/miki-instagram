"""リールを「動画として設計する」ための仕組み（フェーズ0〜2）。

- フェーズ0: Google Drive の素材受け皿と素材台帳（drive_setup.py / catalog.py）
- フェーズ1: 動画・写真の取り込みと解析（ingest.py / media_analysis.py）
- フェーズ2: テーマからリールの設計図を作り、素材を探して不足を洗い出す
  （plan_schema.py / plan_validate.py / asset_search.py / plan_report.py / plan.py）

設計の考え方と書き方のルールは rules/reel-planning.md。
動画の組み立て・音声・カバー・配信（フェーズ3以降）はまだ無い。
"""
