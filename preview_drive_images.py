"""Drive のテーマフォルダの画像を1枚のコンタクトシートに並べて目視確認する。

背景に使う写真は、ファイル名だけでは実写かバナー加工物か判別できない。
とくに bridal フォルダには Instagram 書き出しのグラフィック（AMRTA名の透かし・
顧客レビュー画面のスクショなど）が実写に混ざっている。
「このフォルダには使える写真が無い」と判断してAI生成に逃げる前に、必ずこれで
実物を見ること（2026-08-13 の投稿は、この確認を省いた結果6枚すべてAI生成になった）。

Usage:
    python3 preview_drive_images.py bridal
    python3 preview_drive_images.py menu --limit 60
    python3 preview_drive_images.py bridal --filter 参考

出力: drive_preview_<theme>.png（Read で開いて中身を見る）
      画像の下にファイル名が入るので、そのまま reuse_filename に写せる。
"""
import argparse
import os
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # HEIC が開けないだけで他は動く
    pass

from drive_manager import THEME_NAMES, list_drive_images, download_drive_image

CELL = 340
LABEL_H = 34
COLS = 5


def _label_font():
    for p in ("/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
              "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, 15)
            except Exception:
                pass
    return ImageFont.load_default()


def build_sheet(theme: str, limit: int, name_filter: str) -> str:
    files = list_drive_images(theme)
    if name_filter:
        files = [f for f in files if name_filter in f["name"]]
    if not files:
        print(f"該当画像がありません（theme={theme}, filter={name_filter!r}）")
        return ""
    files = files[:limit]

    tiles = []
    with tempfile.TemporaryDirectory() as tmp:
        for f in files:
            dest = os.path.join(tmp, f["id"])
            if not download_drive_image(f["id"], dest):
                continue
            try:
                im = Image.open(dest).convert("RGB")
            except Exception as e:
                print(f"  開けないためスキップ: {f['name']} ({e})")
                continue
            im.thumbnail((CELL - 10, CELL - 10), Image.LANCZOS)
            tiles.append((im, f["name"]))

        if not tiles:
            print("表示できる画像がありませんでした")
            return ""

        rows = (len(tiles) + COLS - 1) // COLS
        sheet = Image.new("RGB", (COLS * CELL, rows * (CELL + LABEL_H)), (255, 255, 255))
        draw = ImageDraw.Draw(sheet)
        font = _label_font()
        for i, (im, name) in enumerate(tiles):
            cx, cy = (i % COLS) * CELL, (i // COLS) * (CELL + LABEL_H)
            sheet.paste(im, (cx + (CELL - im.size[0]) // 2, cy + (CELL - im.size[1]) // 2))
            draw.text((cx + 6, cy + CELL + 6), name[:38], fill=(0, 0, 0), font=font)

        out = f"drive_preview_{theme}.png"
        sheet.save(out)

    print(f"\n{len(tiles)}枚を {out} に出力しました（Read で開いて目視確認してください）")
    print("透かし・文字入りバナー・露出過多のものを外してから reuse_filename を決めること。")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Driveテーマフォルダの画像を目視確認する")
    parser.add_argument("theme", choices=sorted(THEME_NAMES), help="Driveフォルダのキー")
    parser.add_argument("--limit", type=int, default=40, help="表示枚数の上限（default 40）")
    parser.add_argument("--filter", default="", help="ファイル名の部分一致で絞り込む（例: 参考）")
    args = parser.parse_args()

    sys.exit(0 if build_sheet(args.theme, args.limit, args.filter) else 1)
