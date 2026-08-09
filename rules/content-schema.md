# content.json スキーマ

Claude Code が新規投稿のたびに手書きするファイルの仕様。
**投稿を作る前に必ずこれを読む。** 実装は `generate_carousel.py`（描画）と
`create_post.py:resolve_backgrounds()`（背景解決）。

実績27ファイル・163スライドの集計に基づく（2026-08-09 時点）。

---

## トップレベル

| フィールド | 必須 | 内容 |
|---|---|---|
| `slides` | ✅ | スライド配列。**6枚まで**（末尾の `slide8.jpg` / `slide7.jpg` はコードが自動追加するので含めない）|
| `caption` | ✅ | 投稿本文 1000〜1500文字。→ シートD列 |
| `hashtags` | ✅ | ハッシュタグ（スペース区切りの1文字列）。→ シートE列 |
| `memo` | ✅ | なぜこのテーマ・切り口にしたかの記録。→ シートF列 |
| `alt_text` | ✅ | 代替テキスト。「何が写っていて何が起きているか」を1〜2文で |
| `bg_prompt` | ✅ | **共通のフォールバックプロンプト**（下記）|
| `drive_theme` | 任意 | 新規生成した背景のDriveアップロード先テーマ。省略時はメニュー種別から自動判定（`create_post.py:678`）|
| `_generated_dir` | ⛔️ | **`create_post.py` が自動追記**（`create_post.py:707`）。手書きしない |

### トップレベル `bg_prompt` を必ず書く理由

スライド固有の `bg_prompt` が無いスライドで `generate` に入った時に使われる（`create_post.py:431`）。
**省略すると危険なデフォルトが入る**（`create_post.py:670`）:

```python
bg_prompt = result.get("bg_prompt", "Japanese esthetic salon, soft pink, elegant, luxury spa")
```

`soft pink` は**ピンク禁止ルール違反**、しかも `no people` が入っていない。
必ず自分で `no people` を含めた1本を書くこと。

## スライド共通フィールド

| フィールド | 必須 | 内容 |
|---|---|---|
| `type` | ✅ | `cover` / `text` / `list` / `price` / `cta` / `raw` の6種 |
| `title` | ✅ | 見出し。`\n` で改行可（高さは動的計算されるので固定値の心配は不要）|
| `bg_strategy` | ✅ | 背景の取り方。下記参照 |
| `reuse_source` `reuse_theme` `reuse_filename` | ✅※ | `reuse` / `edit` のとき**3つセットで必須**。ただし止まり方が違う（下記）|
| `focus_y` | 任意 | 写真クロップの縦位置 0.0〜1.0（default 0.5）。被写体が下寄りなら 0.55〜0.65、上寄りなら 0.35〜0.45 |
| `filename` | ⛔️ | `resolve_backgrounds()` が `bg_{timestamp}_{NN}.jpg` を自動割当（`create_post.py:339`）。既存 content.json には `bg01.jpg` 等が手書きで残っているが**上書きされるので意味はない** |
| `bubble` | 任意 | `assets/` 内の透過PNG名。タイトル右脇に丸型バブルを合成（`generate_carousel.py:295`）|
| `seed` | ⛔️ | `generate` 時にコードが記録する |

## 型ごとの固有フィールド

| type | フィールド | 備考 |
|---|---|---|
| `cover` | `kicker` 任意 / `tag` **実質必須** / `photo_h_ratio` 任意（default **0.55**）| `kicker` は自動で大文字化されるので英字推奨。`tag` は実績で全カバーが使用 |
| `text` | `text` ✅ / `slide_photo_h_ratio` 任意（default **0.35**、`0` で写真なし純クリーム）| 最も多用される型（163中92枚）|
| `list` | `items` ✅ / `footer` **実質必須** / `slide_photo_h_ratio` 任意 | **`items` は全角20文字以内**（折り返しなし固定幅描画のため、超えると画像外へはみ出す）|
| `price` | `title` / `top_note` / `columns`（最大2・`{label, lines}`）/ `notes` / `highlight` | 料金表。左右2カラム＋縦の区切り線（`generate_carousel.py:569`）|
| `cta` | `body` ✅ / `subtitle` ✅ / `slide_photo_h_ratio` 任意 | `title` は固定文言（下記）。`subtitle` は**最終行に 💌 が自動付与される**（`generate_carousel.py:728`）ので、絵文字を数える時は勘定に入れる |
| `raw` | — | 末尾2枚専用。コードが自動追加するので content.json に書かない |

### CTAスライドのタイトル（恒久・変更禁止）

```
MIKI指名 初回限定20%OFF\n（VIPコースのみ）
```

改行なしの `MIKI指名 初回限定20%OFF（VIPコースのみ）` も許容される
（`review_post.py:24-25`）が、実績はほぼ全件が改行版。改行版を使う。

**「MIKI指名」と「初回限定」の間のスペースは半角1つ。** `review_post.py:200` は完全一致で
判定するため、スペースが2つあるだけで ❌ になる（実績に1件その取りこぼしがある）。

`body` に以下は書かない（`review_post.py:209-215` が ❌ で止める）:
「MIKIに会いに来てください」「まずはお気軽にDMでご連絡ください」など
→ 「MIKIにお任せください。」に置き換える。

## bg_strategy の値

| 値 | 使用 | 内容 |
|---|---|---|
| `edit` | **既定**（実績のほぼ全て）| Drive画像をダウンロードしてPIL加工（スライド種別に応じたブラー・明度調整）|
| `reuse` | まれ | Drive画像を加工せずそのまま転用（鮮明に保ちたい時）|
| `generate` | **原則禁止** | HF（FLUX→SDXL）で新規生成。`HF_TOKEN` 未設定時、および FLUX・SDXL の両方が失敗した時に Pollinations.ai へフォールバック。使う場合は `bg_generate_reason` に理由必須 |
| `local` | まれ | `local_path` で指定したローカルファイルを使う |

`reuse_theme` に使えるのは **`menu` / `bridal` / `lifestyle`** のみ。
`reward`（ご褒美）は Drive に0枚のため `review_post.py` が ❌ で止める。

### ⚠️ 3点セットの「止まり方」は同じではない

`create_post.py` は3つを同じようには守ってくれない。**`reuse_filename` の書き忘れだけは
黙って通り、意図しない画像で投稿が完成する。**

| 欠落 | 実際の挙動 |
|---|---|
| `reuse_source` | `create_post.py:345` で `ValueError` 停止（原因も明示される）|
| `reuse_theme` | `create_post.py:355` で **`"reward"` にデフォルト** → 0枚 → `:388` で停止するが、メッセージは「Drive取得に失敗」で原因が読み取れない |
| `reuse_filename` | ❌ **`create_post.py:371` で `drive_files[reuse_index]`（既定0番）を黙って採用。停止しない** |

```python
# create_post.py:371 — reuse_filename が無いと静かにここへ落ちる
if not matched_file and drive_files and reuse_index < len(drive_files):
    matched_file = drive_files[reuse_index]
```

3つ揃っているかを機械的に見るのは **`review_post.py:138`** だが、これはフロー上
`create_post.py` の**後**に走る。つまり画像は既に出来上がっている。
**content.json を書いた時点で自分で3つ揃っているか確認すること。**

### スライドレベルの `bg_prompt` について

`generate` を使うスライドにだけ書く。`reuse` / `edit` のスライドには不要
（実績163スライド中、スライドレベルの `bg_prompt` があるのは6枚だけ）。
書く場合は `no people` を必ず含める（`review_post.py:180` がチェックする）。

---

## 記入例（cover）

```json
{
  "type": "cover",
  "title": "はじめてのエステで\n迷わないために",
  "kicker": "FIRST VISIT GUIDE",
  "tag": "- 迷ったらここを見てください -",
  "bg_strategy": "edit",
  "reuse_source": "drive",
  "reuse_theme": "menu",
  "reuse_filename": "makeup room.JPG",
  "focus_y": 0.45
}
```

`reuse_filename` は**拡張子の大文字小文字まで正確に**指定する。
ファイル名は必ずライブのDriveで確認する（`preview_drive_images.py` か下記）:

```bash
/usr/bin/python3 -c "from drive_manager import list_drive_images; print([x['name'] for x in list_drive_images('menu')])"
```
