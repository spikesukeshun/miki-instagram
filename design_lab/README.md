# design_lab — カルーセルデザイン検証サンドボックス

既存の `generate_carousel.py` には**一切手を加えず**、ここで4つの新デザイン案を比較する。

## 構成

```
design_lab/
├── variants/
│   ├── _base.py                      # 共通ユーティリティ（フォント・クロップ等）
│   ├── variant_a_magazine.py         # 案A：明朝・余白主義（雑誌風）
│   ├── variant_b_monochrome.py       # 案B：モノクロ＋差し色
│   ├── variant_c_beige.py            # 案C：くすみベージュ × 親密
│   └── variant_d_themed.py           # 案D：テーマ別カラーパレット
├── render_all.py                     # 全variantで cover/text/list/cta を描画
├── grid_preview.py                   # 過去9投稿のカバーで3×3グリッドを生成
├── compare.html                      # ブラウザで4案を横並び比較
├── sample_content.json               # ライフ系のサンプルコンテンツ
├── sample_content_menu.json          # メニュー系（ブライダル）のサンプル
├── sample_bg/                        # ★ MIKIさん提供の背景写真をここへ（gitignore）
├── fonts/                            # 任意：明朝・手書きフォント追加用（gitignore）
└── output/                           # 生成結果（gitignore）
```

## MIKIさんへ：背景写真の配置

`design_lab/sample_bg/` に下記カテゴリを目安に **10〜15枚** ドロップしてください
（JPG/PNG・縦長か正方形が望ましい）。

| カテゴリ | 用途 | 枚数目安 |
|---|---|---|
| サロン内インテリア（広めの構図） | カバー・テキスト系の背景 | 3〜4枚 |
| 施術小物の静物（オイル瓶・タオル・花・キャンドル等） | リスト・テキスト系 | 3〜4枚 |
| 花・植物のクローズアップ | 雑誌風カバー・差し込み | 2〜3枚 |
| テクスチャ素材（リネン・大理石・木目） | ベージュ系・モノクロ系の背景 | 2〜3枚 |
| ブライダル系（ドレス・ヴェール・ブーケ等／任意） | ブライダル投稿の比較用 | 1〜2枚 |

ファイル名は何でもOK。`sample_content.json` の `slides[].filename` と一致させるか、
こちらでファイル名を再割り当てします。

**写真がまだ無い状態でも `python3 design_lab/render_all.py` は動きます**
（クリーム地のプレースホルダー背景でレイアウト確認可能）。

## 使い方

```bash
# 1) 全4案 × 2テーマ（ライフ／メニュー）の代表4スライドを描画
python3 design_lab/render_all.py

# 2) 過去9件分のカバーで3×3グリッドを生成
python3 design_lab/grid_preview.py

# 3) ブラウザで比較
python3 -m http.server 8000
# → http://localhost:8000/design_lab/compare.html
```

### 一部だけ再描画したい時

```bash
# 案Aのライフ系だけ
python3 design_lab/render_all.py --variant a --content lifestyle

# 案Cのグリッドだけ
python3 design_lab/grid_preview.py --variant c
```

## 既存システムへの影響

`generate_carousel.py` / `create_post.py` / `backgrounds/` / `generated/` /
`content.json` / `.github/workflows/` には**一切影響しない**。
`design_lab/` は完全に独立しており、本番投稿パイプラインとは分離されている。

`.gitignore` で `output/`・`sample_bg/`・追加フォントは Git 管理外。

## 採用案の決定後

方向性が決まったら、本番 `generate_carousel.py` に最小差分で反映する別タスクで
対応する（このサンドボックスは保持しても削除してもよい）。
