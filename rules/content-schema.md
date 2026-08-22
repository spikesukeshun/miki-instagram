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

スライド固有の `bg_prompt` が無いスライドで `generate` に入った時に使われる。

以前は省略時に `"Japanese esthetic salon, soft pink, elegant, luxury spa"` という
デフォルトが入り、**ピンク禁止違反かつ `no people` 抜けのプロンプトが黙って使われていた**。
デフォルトは廃止し、`validate_bg_prompt()` で止める方式に変更済み（2026-08-09）。

検査するのは次の3点:

1. 空でないこと
2. ピンク系の色語を含まないこと（`BANNED_BG_PROMPT_WORDS`。white / beige / cream / gold / warm tone を使う）
3. `no people` を**小文字のまま**含むこと（`review_post.py:180` が完全一致で見るため `No People` は不可）

**止まるタイミング**（どちらも画像・シートへ書く前）:

| 対象 | いつ検査されるか |
|---|---|
| トップレベル | `create_post.py` の背景解決に入る直前。ただし **`generate` に行き着きうるスライドがあり、かつそのスライドが自前の `bg_prompt` を持たない時だけ**（全スライドが Drive の reuse/edit なら共通プロンプトは一度も使われないので、その1フィールドで投稿作成を止めない）|
| スライドレベル | 実際に生成へ渡す直前（＝使われるプロンプトは必ず検査される）|

書くこと自体は**毎回必須**。上の条件は「書き忘れても止まらない場合がある」という意味ではなく、
「使われないフィールドで作業を止めない」という運用上の緩和。

## スライド共通フィールド

| フィールド | 必須 | 内容 |
|---|---|---|
| `type` | ✅ | `cover` / `text` / `list` / `price` / `cta` / `raw` の6種 |
| `title` | ✅ | 見出し。`\n` で改行可（高さは動的計算されるので固定値の心配は不要）|
| `bg_strategy` | ✅ | 背景の取り方。下記参照 |
| `reuse_source` `reuse_theme` `reuse_filename` | ✅ | `reuse` / `edit` のとき**3点セットで必須**。1つでも欠けると `create_post.py` が止まる（下記）|
| `focus_y` | 任意 | 写真クロップの縦位置 0.0〜1.0（default 0.5）。被写体が下寄りなら 0.55〜0.65、上寄りなら 0.35〜0.45 |
| `filename` | ⛔️ | `resolve_backgrounds()` が `bg_{timestamp}_{NN}.jpg` を自動割当（`create_post.py:339`）。既存 content.json には `bg01.jpg` 等が手書きで残っているが**上書きされるので意味はない** |
| `bubble` | 任意 | `assets/` 内の透過PNG名。タイトル右脇に丸型バブルを合成（`generate_carousel.py:295`）|
| `seed` | ⛔️ | `generate` 時にコードが記録する |

## 型ごとの固有フィールド

| type | フィールド | 備考 |
|---|---|---|
| `cover` | `kicker` 任意 / `tag` **実質必須** / `photo_h_ratio` 任意（default **0.55**）| `kicker` は自動で大文字化されるので英字推奨。`tag` は実績で全カバーが使用 |
| `text` | `text` ✅ / `slide_photo_h_ratio` 任意（default **0.35**、`0` で写真なし純クリーム）| 最も多用される型（実績の過半数）|
| `list` | `items` ✅ / `footer` **実質必須** / `slide_photo_h_ratio` 任意 | **`items` は全角20文字以内**（折り返しなし固定幅描画のため、超えると画像外へはみ出す）|
| `price` | `title` / `top_note` / `columns`（最大2・`{label, lines}`）/ `notes` / `highlight` | 料金表。左右2カラム＋縦の区切り線（`generate_carousel.py:569`）|
| `cta` | `body` ✅ / `subtitle` ✅ / `slide_photo_h_ratio` 任意 | `title` は固定文言（下記）。`subtitle` は**最終行に 💌 が自動付与される**（`generate_carousel.py:728`）ので、絵文字を数える時は勘定に入れる |
| `raw` | — | 末尾2枚専用。コードが自動追加するので content.json に書かない |

### CTAスライドのタイトル（恒久・変更禁止）

```
MIKI指名 Instagram限定20%OFF\n（VIPコースのみ）
```

改行なしの `MIKI指名 Instagram限定20%OFF（VIPコースのみ）` も許容される
（`review_post.py:24-25`）が、実績はほぼ全件が改行版。改行版を使う。

**「MIKI指名」と「Instagram限定」の間のスペースは半角1つ。** `review_post.py:200` は完全一致で
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

### 3点セットは1つでも欠けたら止まる（2026-08-09 にコード側で統一）

`create_post.py:_validate_reuse_fields()` が `reuse` / `edit` の全スライドについて
`reuse_source` / `reuse_theme` / `reuse_filename` の欠落を**画像を1枚も落とす前にまとめて検査し、
足りないフィールド名を挙げて `ValueError` で停止する**。
`reuse_source` の値も `drive` / `instagram` のみ許可（`"Drive"` や typo は停止）。
値が想定外だと3点セット検査を素通りしてAI生成へ落ちるため。

以前は3つで挙動がバラバラで、特に **`reuse_filename` の書き忘れだけは黙って通り、
Drive の `reuse_index` 番目（既定0番）の画像で投稿が完成していた**。
この暗黙フォールバックは削除済み。**Drive 画像は必ずファイル名で解決される。**

ファイル名が Drive に見つからない場合も、別画像やAI生成へ落とさずその場で停止し、
ファイル名一覧を確認するコマンドをエラーメッセージに出す。
`reuse_source: "instagram"`（過去投稿の転用）も、解決・ダウンロードに失敗したら
AI生成へ落とさず停止する。**`reuse` / `edit` から静かにAI生成へ落ちる経路はもう無い。**
ただし `local` はファイルが見つからないと今もHF生成へフォールバックする
（`create_post.py` の local 分岐。実績で使われていないため未対応）。

`review_post.py:138` も同じ3点セットを見るが、これはフロー上 `create_post.py` の**後**に走る。
**先に止まるのは `create_post.py` 側**なので、エラーが出たら content.json を直して作り直す。

### スライドレベルの `bg_prompt` について

`generate` を使うスライドにだけ書く。`reuse` / `edit` のスライドには不要
（実績163スライド中、スライドレベルの `bg_prompt` があるのは6枚だけ）。
書く場合は `no people` を必ず含める（`review_post.py:180` がチェックし、
`create_post.py` も生成直前に `validate_bg_prompt()` で同じ3点を見て停止する）。

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
