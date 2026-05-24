# 引き継ぎ：#22〜#24 作成セッション向け

最終更新：2026-05-19／前任セッション：tender-franklin-00a039（#15〜#21 完成）

## このセッションでやること

**#22・#23・#24 の3件を一気に全部作る**（ユーザー要望）。
すべて通常投稿（create_post.py 経由）。BA（動画）パイプラインは今回不要。

| # | Row | 投稿日時(JST) | テーマ | CTA 文言テンプレ |
|---|---|---|---|---|
| 22 | 22 | 2026/05/27(水) 21:00 | MIKIのぼやき②（お客様から学んだこと・自己語り／人柄） | 「DMで『はじめまして』の一言だけで大丈夫」 |
| 23 | 23 | 2026/05/29(金) 21:00 | 悩み共感（ライフプラン） | 「DMで『これから話したい』だけでOK」 |
| 24 | 24 | 2026/05/31(土) 12:00 | お客様の声（過去B再編集③／エステ後の食事5選） | 「DMで『食事も気になる』」 |

- #22 は自己語り系（インサイト最強テーマ・平均いいね最高）。MIKI個人の人柄が出る回。
- #24 は過去ブライダル（2023-06-18「エステ後の食事」）の再編集 →「エステ後におすすめの食事5選＋お客様の声1〜2件」。過去キャプションは流用せず現スタイルに書き直す。listスライドが活きる回。

## 最終KPI

初DM獲得（5/10〜5/31 の投稿期間で最低1件）。全件 CTA を中盤ソフト・スライド6・末尾の3箇所に。「気軽に・一言だけでもOK・初めての方こそ」を必ず1箇所。

## 必ず最初に走らせる

```bash
cd /Users/shunsuke/Desktop/美喜のinstagram/.claude/worktrees/tender-franklin-00a039
/usr/bin/python3 get_recent_insights.py   # 省略不可。recent_insights.json 更新
```

## 作り方（3件とも同じ）

```bash
# Claude Code が content_NN.json を作成（ルールは下記）
/usr/bin/python3 create_post.py --content-file content_22.json --post-datetime "2026/05/27 21:00"
/usr/bin/python3 review_post.py content_22.json          # ✅ が出るまで直す。省略不可
rm -f backgrounds/bg_*.jpg generated/carousel_*.jpg      # cleanup（cleanup_backgrounds.py は無いので手動）
# #23, #24 も同様に日時を変えて実行
```

⚠️ **`--post-datetime` は必須**。省略すると既定値 `2026/04/12 21:00` の行に誤登録される（今セッションで実際に踏んだ罠）。誤登録したら `register_post.get_sheet()` で該当行を `delete_rows()` するか正しい日時で再実行して上書き。

生成後はプレビューURL `https://spikesukeshun.github.io/miki-instagram/YYYY-MM-DD-HHMM/` を MIKI に共有して確認をもらう。

## ★このセッションで確定した新ルール（必ず継承）

1. **背景はDrive写真のみ。AI generate は禁止**（ユーザー指定がない限り）。cover/cta も含め全スライド `bg_strategy:"edit"`（または"reuse"）。**必ず4点セット**で書く：
   ```json
   "bg_strategy": "edit", "reuse_source": "drive", "reuse_theme": "menu", "reuse_filename": "○○.JPG"
   ```
2. **気持ち悪い表現を使わない**：「胸がきゅっとなる」「手を動かしながら」等の身体・情緒過剰表現は禁止（MIKI本人がNGと明言）。
3. **写真の見せ方**：`slide_photo_h_ratio` はカルーセル全体でデフォルト統一（個別に変えるとスワイプ時に高さがガタつき、MIKIが嫌う）。**被写体位置の調整は `focus_y` のみ**で行う（0=上/0.5=中央/1=下、0.1刻みで微調整）。顔・輪郭が切れないか毎回プレビュー確認。
4. **キャプションの自然さ最優先**：不自然な日本語・直訳調を避ける。CTAは「送ってください」(お願い)より「ひと言だけでも大丈夫です」(安心・ハードル下げ)を優先。同じ趣旨の文を近接して2回繰り返さない（重複チェック）。
5. **サロン名「AMRTA」の写り込み**：一部Drive写真に写る（BirthDay.JPG＝誕生日カード／outside.JPG＝すりガラス／Reception.JPG＝壁看板）。原則スライドにサロン名は載せない方針。目立つ写り込みがあれば別写真にするか MIKI に相談。※#21 は MIKI 判断で許容済み。
6. **絵文字 3〜5個**（review_post.py は3-5でOK。`✨…✨` は2個カウント）。

## ★新機能：listスライドのタイトル右にバブル画像（main にコミット済 / commit 4c36bcc）

- `generate_carousel.py` に `paste_title_bubble` 実装済み。`assets/miki_bubble_ring.png`（金枠・円形・透過PNG）を使用。
- **使い方**：listスライドに1行足すだけ。
  ```json
  "type": "list", "title": "…", "items": [...], "bubble": "miki_bubble_ring.png"
  ```
  → タイトル右脇に自動配置（右端はみ出しクランプ・非正方形の中央正方形クロップ・縦下端クランプ込み）。
- `assets/` に `miki_bubble_ring.png`（円形・推奨）と `miki_bubble.png`（正方形）がある。
- #24（食事5選＝listスライド）でバブルを使うと MIKI の人柄が出て良い。

## コードを変更したら Codex レビュー必須（memoryルール）

新規ファイル作成・複数ファイル変更は完了報告の前に `codex-review` スキルを自走で実行。今セッションのバブル機能も Codex レビュー → 指摘反映済み。

## 使える Drive 写真（theme="menu" / 全157枚の一部・確認済み）

`BirthDay.JPG, outside.JPG, フェイシャル引き上げ.JPG, お腹のマッサージ 1.JPG, jacuzzi.JPG, Jacuzzi time.JPG, makeup room.JPG, herbs.JPG, head massage.JPG, Hamam bath.JPG, Reception.JPG, candle.jpg, Droom.JPG, elbow.JPG …`

全リスト取得：
```bash
/usr/bin/python3 -c "from drive_manager import list_drive_images; print(sorted(i['name'] for i in list_drive_images('menu')))"
```
- ファイル名は拡張子の大小（.JPG / .jpg）も正確に。
- 文章に合う写真を Claude が選定（#20/#21 と被りすぎない配分。自己語り回はパウダールーム・小物・空間系が合う）。

## Python 環境（重要）

**`/usr/bin/python3`（macOS システム Python 3.9）固定**。`python3`(3.14)/`python3.12` は gspread/groq/googleapiclient 未導入なので使わない。必ずフルパス指定。

## コンテンツ生成の絶対ルール（CLAUDE.md 抜粋・据え置き）

1. キャプション 1〜2 行目に SEO 主要キーワード／**3 行目から「MIKIです。」開始**（1行目に置かない）
2. 1000〜1500字／絵文字 3〜5 個
3. `——`（em dash）禁止。ローマ字・「・」「-」以外の記号は本文では避ける（MIKI / VIP / 数字 / %／「」（）／--- 区切り／絵文字は実運用OK）
4. スライド本文（text/body/items）に「MIKI」を使わない（一人称は「私」）。※元案に「MIKIが磨き上げます」等があっても「私が」に直す（#21で実施）
5. スライドタイトルの「MIKI」は品格チェック必須
6. CTA スライドのタイトルは恒久固定 **「MIKI指名 初回限定20%OFF\n（VIPコースのみ）」**
7. list スライドの items は **全角20文字以内**
8. AI 生成スライドは 5〜6 枚。末尾2枚（slide7.jpg/slide8.jpg）はシステム自動付与（content.json に書かない）
9. alt_text は短い文章（キーワード羅列でない）
10. キャプション末尾に CTA を必ず入れる
11. `review_post.py content_NN.json` を毎回必ず実行（修正依頼処理時は `--revision "依頼文"` も付ける）

## インサイト戦略（参考）

- ライフスタイル・自己語り：平均いいね最高 → #22 はここに該当、丁寧に作る
- メニュー・サービス：いいね最低 → 全体の50%以下に
- お客様の声・list 系（#24）：保存されやすい構成を意識

## 参考：過去の詳細プラン

- `/Users/shunsuke/.claude/plans/14-10-https-docs-google-com-spreadsheet-frolicking-penguin.md`（全体スケジュール・テーマ別CTA）

---
## 完了済みの記録（#15〜#21）

- #15〜#21 すべて content_NN.json 作成・プレビュー登録・スプレッドシート登録済み。
- #16（BA一般）は2枚目が動画→静止画になる不具合を修正し 2026/05/14 21:00 に再登録。動画＋静止画の混在カルーセルは `instagram_mixed.py`（root, main済）＋`post_scheduler.py` の分岐で対応済み。
- #19（BAブライダル）は F1〜F8 の5秒動画（明度統一＋テロップ「肩甲骨に注目」）入りで完成。
- #20（自己肯定）/#21（メニュー＋料金）完成。#21 でバブル機能を新規実装・main コミット。
