# 【別セクション宛】Before/After 投稿の差し替え依頼

## 背景
スケジュール組のセクションでは、通常の **8 枚構成**（カバー / 本文 6 枚 / CTA / プロフィール）の
カルーセルデザインで投稿を作成している。
**「Before/After（BA）」をテーマにした投稿のみ**、本文に当たる
**2〜6 枚目（5 枚）** を専用デザインに差し替えたい。

> ⚠ 本番カルーセルのスライドインデックスと、experiments/before_after 側の
> `content_ba.json` のスライドインデックスは **オフセットが違う**。本番の 2 枚目 ＝
> BA 側 slide[1]（type=`video_passthrough`）に対応する。詳細は下表参照。

## 適用ルール（インデックス対応）

| 本番カルーセル | 担当 | BA 側 `content_ba.json` の該当 slide |
|---|---|---|
| 1 枚目（表紙） | 既存パイプライン | （使わない。BA 側 `slide[0]=ba_cover` は試作用） |
| 2 枚目 | **BA**：動画＋クリーム色フレーム | `slide[1]` `video_passthrough` |
| 3 枚目 | **BA**：暗背景の text_overlay | `slide[2]` `ba_text_overlay` |
| 4 枚目 | **BA**：grid_compare | `slide[3]` `ba_grid_compare` |
| 5 枚目 | **BA**：duration（左右 BA + 周期説明） | `slide[4]` `ba_duration` |
| 6 枚目 | **BA**：MIKI エステの 3 つのポイント | `slide[5]` `ba_points` |
| 7 枚目（CTA） | 既存パイプライン | — |
| 8 枚目（プロフィール） | 既存パイプライン | — |

## 呼び出し方

スケジュール側で投稿テーマごとに **動的に content_ba.json を組み立て**、
`generate_ba_carousel.py` を CLI 呼び出しするのが想定フロー。

```bash
# テーマ別に content を組み立てて保存
python -m experiments.before_after.generate_ba_carousel \
    --content path/to/themed_content_ba.json \
    --output-dir path/to/themed_output_dir
# --dry-run（既定）：generated/ に画像 5 枚 + 動画 1 本を出力するだけ
# --publish：Instagram Graph API へ実投稿（ba_02 video_url が必須）
```

スケジュール内から関数として呼びたい場合：

```python
from experiments.before_after.generate_ba_carousel import main as ba_generate

# argv 経由でしか動かないので argparse 互換で渡す
import sys
sys.argv = ["ba", "--content", "themed_content_ba.json",
            "--output-dir", "out_ba"]
ba_generate()
```

その後、**本番 1 / 7 / 8 枚目を既存パイプラインで生成 → BA 出力 5 枚と
連結 → `post_ba_mixed.py` 系のミックスドカルーセル投稿** に渡す。

## 動画フレーム指定（2 枚目）

`video_passthrough` slide の任意フィールド：

| フィールド | 推奨値 | 説明 |
|---|---|---|
| `frame_width` | `30` | px 単位。0 でフレームなし（pass-through） |
| `frame_color` | `"#F6F1F1"` | CREAM。サロンのトーンに合わせる |
| `video_url` | `null`（dry-run 時） | `--publish` 時は Drive 公開 URL を埋める |

`video_url` の作り方：Drive にアップロード → 共有設定を「リンクを知っている人」→
`https://drive.google.com/uc?export=download&id=<FILE_ID>` 形式に組み直して指定。

## 6 枚目の使い回し（テンプレート）

`templates/miki_3_points.json` に「MIKI エステの 3 つのポイント」スライド定義を保管。
他のテーマ（BA 以外）でも 3 つのポイント枠を出したいときは流用可能。

### 流用手順

1. テンプレ読み込み：

   ```python
   import json, copy
   with open("experiments/before_after/templates/miki_3_points.json") as f:
       tpl = json.load(f)["slide"]
   ```

2. 画像 3 枚（`point2.jpg` / `miki.jpg` / `sky.jpg`）を流用先の assets ディレクトリへコピー。
   重複を避けたいなら専用サブディレクトリを切る（推奨：`assets/miki_3_points/`）。

3. テンプレ内の image パスを書き換え。例：

   ```python
   slide = copy.deepcopy(tpl)
   for it, name in zip(slide["items"], ["point2.jpg", "miki.jpg", "sky.jpg"]):
       it["image"] = f"assets/miki_3_points/{name}"
   ```

4. スケジュール側 `content_*.json` の slides 配列に挿入。

## 失敗時の見方

- `ffmpeg でフレーム付与に失敗しました` という RuntimeError が出たら、メッセージに
  ffmpeg の stderr が含まれる。コーデック非対応・破損ファイルが主因。
- `video_passthrough.video_url（公開 URL）が必要` のエラーは `--publish` 時のみ。
  Drive アップロード後に `video_url` を埋めて再実行。

## 参照元（ファイル）

- 生成スクリプト：`experiments/before_after/generate_ba_carousel.py`
- スライド合成ロジック：`experiments/before_after/ba_helpers.py`
- スライド定義サンプル：`experiments/before_after/content_ba.json`
- 投稿スクリプト（mixed carousel）：`experiments/before_after/post_ba_mixed.py`
- 6 枚目テンプレ：`experiments/before_after/templates/miki_3_points.json`
