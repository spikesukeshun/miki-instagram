# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**このファイルは索引です。** 絶対ルールと実行フローだけを持ち、判断基準の詳細は下記に置いている。
同じルールを2か所に書かないこと（三重管理でルールが迷子になった経緯は `rules/incidents.md`）。

## このリポジトリの読み方

| いつ読むか | ファイル |
|---|---|
| 投稿の文章を書く前（**毎回**）| `SKILL.md` — MIKIの文体・ブランドトーン・§14 に内容ルールの正 |
| content.json を書く前（**毎回**）| `rules/content-schema.md` — 全フィールド仕様・スライド型6種 |
| デザインやレイアウトを触る時 | `rules/carousel-design.md` — 案A の仕様と戻してはいけない実装 |
| リールを配信する時 | `rules/reels.md` — 手動投稿の理由と `deliver_reel.py` の手順 |
| ルールを変える時・同じ症状が再発した時 | `rules/incidents.md` — 過去の事故記録とインサイト戦略 |

## プロジェクト概要

エステ・リラクゼーションサロンのInstagram投稿を自動化し、フォロワーから直接予約が入るようにするツール。

- **ビジネス**: エステ・リラクゼーションサロン（Instagramプロアカウント / Meta Graph API利用可）
- **最終目標**: 投稿の自動スケジューリングにより、予約導線（DM・予約リンク）への流入を増やす
- **アクセストークン**: 長期トークン（60日）。期限切れに注意
- **予約導線**: キャプションに予約リンクを書く方法が審査不要で確実

## 技術スタック・主要ファイル

Python 3.11+ / Meta Graph API / Google Sheets（gspread）/ Google Drive（背景画像）/ Pillow。
定時実行は **GitHub Actions**（`.github/workflows/post.yml`）。環境変数は `.env`（`.env.example` 参照）。

| ファイル | 役割 |
|---|---|
| `create_post.py` | 投稿生成の本体。背景解決・画像生成・シート登録まで |
| `generate_carousel.py` | カルーセル画像の描画 |
| `review_post.py` | content.json の機械校閲（**省略不可**）|
| `post_scheduler.py` | 定時投稿・手動リールの公開確認・プレビュー削除 |
| `register_post.py` | スプレッドシート書き込み（A:H 固定）|
| `check_repo_sync.py` | ローカルが origin/main から遅れていないか検出 |
| `check_week_slots.py` | 週の空き枠判定（作成済みの投稿を二重に作らない）|
| `get_recent_insights.py` / `insight_report.py` | インサイト取得・全期間集計 |
| `preview_drive_images.py` | Drive候補をコンタクトシート化して目視確認 |
| `deliver_reel.py` | リールをLINE配信（手動投稿用）|

## 絶対ルール（毎回・例外なし）

判断に迷ったら `SKILL.md` §14 を読む。ここは「これだけは絶対」の要約。

- **サロン名を書かない。** キャプション・スライド・ハッシュタグのいずれにも
  「AMRTA」「AMRTA六本木」を出さない（MIKI個人への予約導線を優先するため）
- **スライドは6枚**（上限6）。末尾2枚（`slide8.jpg` / `slide7.jpg`）は
  コードが自動追加するので content.json に書かない
- **背景は Drive のサロン実写。既定は `bg_strategy: "edit"`。**
  `generate`（AI生成）は原則禁止。使う場合は `bg_generate_reason` に理由を書く
- **`reuse` / `edit` は `reuse_source="drive"` / `reuse_theme` / `reuse_filename` の3点セット必須。**
  `reuse_theme` は `menu` / `bridal` / `lifestyle` のみ（`reward` は0枚で使用不可）。
  ⚠️ **`reuse_filename` の書き忘れだけは `create_post.py` が止めてくれず、
  Drive の0番目の画像を黙って使ってしまう**（`create_post.py:371`）。自分で確認すること
- **「Driveに使える写真が無い」と判断する前に必ず目視する** → `preview_drive_images.py`。
  なお Drive「施術・メニュー紹介」の**「参考N」画像は例外扱いで全て使用可**
  （サロン名・人物・施術シーンが写っていてもよい。ユーザーが選定した公式素材のため）
- **トップレベル `bg_prompt` を必ず書く**（`no people` 込み）。省略すると
  `soft pink`（ピンク禁止違反）のデフォルトが入る。**プロンプトにピンク系を指定しない**
  （white / beige / cream / gold / warm tone を使う）
- **スライド本文（text/body）の一人称は「私」。** MIKIはタイトルのみ
- **CTAスライドのタイトルは固定文言**（修正依頼でも変更しない）：
  `MIKI指名 初回限定20%OFF\n（VIPコースのみ）`
- **キャプション**: 1〜2行目に主要キーワードの導入文（毎回固有の一文）→ 空行 → 3行目から
  「MIKIです。」／1000〜1500文字／絵文字3〜5個／`——` と英字の混入禁止／末尾に必ずCTA
- **`alt_text` は文章で書く**（キーワード羅列はNG）
- **スプレッドシートは A〜H の8列固定。I列以降を使わない**

## 新規投稿のフロー

「スケジュールを組んで」「次の投稿を作って」と言われたら、**この順番どおりに実行する**。

```bash
# 0. コード同期チェック（省略不可）
#    ローカルが origin/main から遅れていると、確定済みルールが巻き戻る
python3 check_repo_sync.py

# 1. 直近インサイトの取得（省略不可・content.json 作成より先）
#    テーマ別平均いいね／戦略ヒントを次回のテーマ選定に反映する
python3 get_recent_insights.py

# 2. 空き枠の確認（先の分まで作成済みのことが多い）
python3 check_week_slots.py
```

3. **`SKILL.md` と `rules/content-schema.md` を読んでから** content.json を書く（**省略不可**）
4. 画像生成とシート登録：

```bash
python create_post.py --content-file content.json
```

`--content-file` を付けない `python create_post.py` は Groq に文章を自動生成させる旧経路。
現在の運用では使わない（定時投稿の GitHub Actions は `post_scheduler.py` だけを実行する）。

5. 校閲（**省略不可**）。❌ が出たら content.json を直して 4 に戻る：

```bash
python review_post.py content.json
```

6. 後片付け（**省略不可**）。実行ログの `seed=XXXXXX` を渡す：

```bash
python cleanup_backgrounds.py --seed XXXXXX --force   # generate 画像があった回
python cleanup_backgrounds.py --no-generate --force   # reuse/edit だけの回（通常こちら）
```

`cleanup_backgrounds.py` は `backgrounds/` の画像と `generated/carousel_*.jpg` を削除し、
seed を `upload_history.json` に記録して Drive への重複アップを防ぐ。
seed が複数ある場合はスペース区切りで渡す。

**プレビューページの削除は自動**。`post_scheduler.py` が投稿成功時に
`docs/{slug}/index.html` を GitHub から削除する（失敗しても投稿フローは止まらない）。

## 修正依頼のフロー

修正はすべて**チャット経由**（シート経由の自動修正フローは 2026-07-11 に廃止済み）。

1. チャットで修正指示を受けて content.json を直す
2. `python create_post.py --content-file content.json` を再実行
3. **修正指示文を渡して校閲する**（依頼内容が反映されたかも検証される）：

```bash
python review_post.py content.json --revision "修正依頼の全文"
```

4. `cleanup_backgrounds.py` を実行する（新規投稿時と同じ）

## リール動画は「手動投稿」

Graph API ではリールに本体の音源ライブラリ（トレンド音源）を付けられないため、
**リールだけは MIKIさんがアプリから音源を選んで投稿する**（2026-08-06〜）。
カルーセルの自動投稿フローは従来どおり。

```bash
python3 deliver_reel.py --datetime "2026/08/21 21:00" \
                        --video ~/Desktop/美喜のinstagram/miki-profile-reel/reel_new.mp4 \
                        --content-file content_2026-08-21-2100.json
```

ステータスは `確認待ち` →（配信）→ `手動投稿待ち` →（Graph APIで自動検知）→ `投稿済み`。
「手動投稿待ち」は自動投稿の対象外だが、`check_week_slots.py` からは枠が埋まって見えるので
重複してカルーセルが作られることはない。

詳細（配信手順・督促の仕組み・GitHub Pages を使う理由）→ `rules/reels.md`

## スプレッドシートの列（A〜H の8列固定）

| 列 | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| 内容 | 投稿日時 | メニュー種別 | 画像ファイル名 | 投稿文 | ハッシュタグ | 投稿メモ | ステータス | プレビューURL |

- **I列以降は使わない。** 2026-07-11 に修正指示・seed・alt_text を廃止した
- `alt_text` は content.json だけで管理する。seed は `create_post.py` のログから
  `cleanup_backgrounds.py --seed` に渡す。**どちらもシートに書かない**
- 書き込みは必ず `register_post.py` の `register()` / `update_spreadsheet_row()` を通す。
  範囲は `A:H` 固定（`SHEET_LAST_COL` / `SHEET_NUM_COLS`）で、行を更新するたびに
  I列以降を自動でクリアする。**この範囲を広げないこと**

## 過去の事故から得た教訓

詳細な記録は `rules/incidents.md`。要点だけ：

- **ルールを文章に書くだけでは、コードが古いと巻き戻る。** 恒久ルールは
  `review_post.py` の機械チェックか、コード側の恒久実装のどちらかに落とすこと
- **投稿を生成するディレクトリが origin/main から遅れていないか毎回確認する。**
  2026-08-08、ローカル main が4月版のまま4か月放置され「画像を作るコードは4月版・
  投稿するコードは8月版」という食い違いが起きた → `check_repo_sync.py`
- **同じルールを2か所に書かない。書いた瞬間から片方が腐り始める。**
  コード内の数値（px値・デフォルト値）をドキュメントに転記しないこと
