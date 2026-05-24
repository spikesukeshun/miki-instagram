# Before/After カルーセル試作環境

参考投稿 https://www.instagram.com/p/DXsigplk5C_/ のデザイン（左右分割 Before/After + 動画混在 + MIKI吹き出し）を真似るための試作スペース。

## 重要

**本流（`create_post.py` / `generate_carousel.py` / `instagram_api.py` / `content.json` / `review_post.py`）には一切手を加えない**。ここは隔離されたサンドボックス。試作で OK が出たら、別タスクで本流統合を検討する。

## ディレクトリ

```
experiments/before_after/
├── README.md                  # このファイル
├── content_ba.json            # サンプル content（BA 専用スキーマ）
├── ba_helpers.py              # 共通ヘルパー（吹き出し・BA 合成）
├── generate_ba_carousel.py    # 生成パイプライン CLI
├── post_ba_mixed.py           # 動画混在カルーセル投稿（Meta Graph API）
├── assets/                    # ユーザー提供素材（gitignore）
└── generated/                 # 出力先（gitignore）
```

## 使い方

### 1. 素材を `assets/` に置く

`content_ba.json` のサンプルでは下記のファイル名を参照している（パスは content_ba.json からの相対）:
- `assets/case1_before.jpg`, `assets/case1_after.jpg`
- `assets/case1.mp4`
- `assets/case2_before.jpg`, `assets/case2_after.jpg`

ファイル名はサンプル用。`content_ba.json` を書き換えれば任意の名前で OK。

### 2. dry-run で生成のみ実行

```bash
cd <repo-root>
python -m experiments.before_after.generate_ba_carousel --dry-run
```

`generated/` にスライド画像（jpg）と動画（mp4 のコピー）が出力される。
Instagram には何も投稿されない。

### 3. 生成物を目視確認

`experiments/before_after/generated/` を Finder などで開いて、
- 左右分割の境界線
- Before/After ラベル
- 吹き出しの位置・テキスト
を確認する。

### 4. （画面収録が届いたあと）デザインを微調整

`ba_helpers.py` の以下を画面収録に合わせて調整:
- `_draw_label_badges`: ラベルの位置・色・形状
- `compose_ba_split`: 境界線の太さ・色（content_ba.json の `divider` で個別指定可）
- `draw_speech_bubble`: 吹き出しの形状・しっぽ・色

### 5. 実投稿（publish）

動画を Drive 等に上げて公開 URL を取得し、`content_ba.json` の各スライドに `image_url` / `video_url` を埋めてから:

```bash
python -m experiments.before_after.generate_ba_carousel --publish
```

`post_ba_mixed.post_mixed_carousel()` が呼ばれて Meta Graph API で投稿される。

#### 投稿前に API 動作確認だけしたい場合

`post_ba_mixed.py` 単体に dry-run モードがあり、子コンテナ作成までで止まる:

```bash
python -m experiments.before_after.post_ba_mixed --content experiments/before_after/content_ba.json --dry-run
```

## 本流に影響していないことの確認

```bash
git diff main -- create_post.py generate_carousel.py instagram_api.py content.json review_post.py process_revisions.py
```

何も差分が出なければ OK。

## 画面収録の前後で進められる範囲

**画面収録なしで動く部分（このコミットの実装範囲）**
- `compose_ba_split`（左右分割 + ラベルバッジ + オプションの吹き出し）
- `draw_speech_bubble`（角丸長方形 + 三角しっぽ、汎用デザイン）
- `post_mixed_carousel`（IMAGE + VIDEO 混在カルーセル投稿）
- `--dry-run` での生成パイプライン

**画面収録を見てから別タスクで詰める部分**
- 境界線・ラベル・吹き出しのデザイン微調整（色・形・位置）
- 吹き出しに MIKI アバター画像を合成するか
- 動画スライドの数・トリミング・キャプション焼き込み有無
- カルーセル全体の構成（参考投稿の枚数・並び）
