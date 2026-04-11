# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

エステ・リラクゼーションサロンのInstagram投稿を自動化し、フォロワーから直接予約が入るようにするツール。

- **ビジネス**: エステ・リラクゼーションサロン
- **Instagramアカウント**: プロアカウント（Meta Graph API利用可）
- **最終目標**: 投稿の自動スケジューリングにより、予約導線（DM・予約リンク）への流入を増やす

## 技術スタック

- **言語**: Python 3.11+
- **Instagram API**: Meta Graph API（投稿・インサイト取得）
- **スケジューラー**: APScheduler（ローカル実行）または GitHub Actions（クラウド実行）
- **データ管理**: Google Sheets または CSV（投稿スケジュール管理）
- **環境変数**: `python-dotenv`（`.env`ファイルでトークン管理）

## 主要ファイル構成（予定）

```
├── .env                  # APIトークン（Gitに含めない）
├── requirements.txt      # 依存パッケージ
├── post_scheduler.py     # 投稿スケジューリングのメイン処理
├── instagram_api.py      # Meta Graph API ラッパー
├── content/              # 投稿用画像・動画
└── schedule.csv          # 投稿スケジュール（日時・キャプション・ハッシュタグ）
```

## 開発コマンド

```bash
# 依存パッケージのインストール
pip install -r requirements.txt

# 環境変数の設定
cp .env.example .env
# .env にアクセストークン等を記入

# 投稿スケジューラーの実行
python post_scheduler.py

# 手動で1件テスト投稿
python instagram_api.py --test
```

## Meta Graph API 重要事項

- **必要なもの**: Facebookページ連携済みのInstagramプロアカウント
- **アクセストークン**: 長期トークン（60日）を使用。期限切れに注意
- **投稿できるもの**: 画像1枚、カルーセル（複数画像）、リール動画
- **DM自動返信**: Messenger API経由（Meta審査が必要な場合あり）
- **予約導線**: 投稿キャプションに予約リンク（STORES予約・Airrsv等）を記載する方法が審査不要で確実

## .env の構成

```
INSTAGRAM_ACCESS_TOKEN=your_token_here
INSTAGRAM_BUSINESS_ACCOUNT_ID=your_account_id_here
FACEBOOK_PAGE_ID=your_page_id_here
```

## コンテンツ生成ルール（重要）

### サロン名について
- キャプション・スライド・ハッシュタグのいずれにも「AMRTA六本木」「AMRTA」のサロン名は記載しない
- MIKI個人への予約導線を優先するため

### スライド構成
- AIが生成するスライド：コンテンツに応じて5〜8枚（最適枚数をAIが判断）
- **末尾2枚は常に固定**（システムが自動追加）：
  - 後ろから2枚目：`slide8.jpg`
  - 最後（一番後ろ）：`slide7.jpg`（MIKIプロフィール）
- 背景画像はスライドごとにAIが戦略を判断する（`backgrounds/` フォルダ、Gitには含めない）
  - `reuse`: 過去投稿の画像をそのまま転用（雰囲気が合う場合）
  - `edit`: 過去投稿の画像をPIL加工して転用（ブラー・明度・オーバーレイなどスライド種別に応じた加工）
  - `generate`: Pollinations.aiで新規生成（表紙や印象的な場面など）
  - 過去投稿データが豊富にあるため、テーマに合うものは積極的にreuse/editを活用する

### コンテンツ生成エンジン（役割分担）

| シーン | 担当 | 方法 |
|---|---|---|
| 対話セッションでの新規投稿作成 | **Claude Code**（このセッション） | Claude Codeがスライド文章・キャプション・ハッシュタグを生成・校閲し、`content.json`に書き出す |
| 自動修正処理（GitHub Actions） | **Groq API** | `process_revisions.py`が自動実行 |

**対話セッションでの実行コマンド:**
```bash
# Claude Codeがcontent.jsonを生成した後
python create_post.py --content-file content.json
```

**content.jsonを使わない（従来動作）:**
```bash
python create_post.py  # Groqで自動生成
```

### キャプションスタイル
- **Claude Codeが作成する場合**: 過去投稿の文体・MIKIのブランドトーンを参照して生成・校閲する
- **Groqが作成する場合**: create_post.pyが自動的に過去投稿を取得して文体参照
- スタイル（自分語り・情報提供・共感訴求など）はテーマに応じて判断する（「自分語り系に固定」ではない）
- 文章量：1000〜1500文字程度
- 言い回し：柔らかく親しみやすい・読者に語りかける口調
- 段落は短く区切る（`\n\n`で区切る）・絵文字は要所のみ
- 冒頭「MIKIです。」、末尾に必ずCTA（「MIKI指名 初回限定20%OFF」「DMからご相談」）
- 英語・ローマ字の混入禁止（「・」「-」以外の記号も不可）

## 恒久デザインルール（毎回必ず確認・適用すること）

これらは過去の修正依頼から確定したルール。新規投稿・修正・レビューの都度チェックする。

### 背景画像（bg_prompt）
- **全スライド共通**: `no people` を必ず含める（人物なし静物・インテリア写真を優先）
- 過激・性的・露骨な肌露出は禁止。ウェディングドレスや適度な露出は問題なし
- 施術中のベッド画像など不自然に過激な構図は避ける

### スライド構成
- AIが生成するスライドは **5〜6枚**（末尾2枚の固定スライドと合わせて合計7〜8枚）
- **末尾2枚は必ず固定**（コードが自動追加、Claude Codeはスライドに含めない）：
  - 後ろから2枚目：`slide8.jpg`（サロン情報）
  - 最後：`slide7.jpg`（MIKIプロフィール）

### レイアウト（generate_carousel.py で実装済み）
- タイトルと本文の間の余白：区切り線から本文まで 100px（text スライド）、60px（cta スライド）
- リストスライドの区切り線から項目まで：45px
- これらはコードに反映済み。content.json の内容に関わらず自動適用される。

### セッション開始時の確認事項
新しい content.json を作成・レビューする際は以下を必ずチェックする：
1. 全スライドの bg_prompt に `no people` が入っているか（静物・インテリア中心）
2. slides の枚数が 6 枚以内か（slide8/slide7 を除く）
3. タイトルの改行が文節の区切りで自然か（助詞「は」「を」「が」止めは極力避ける）
