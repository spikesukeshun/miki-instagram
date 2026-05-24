"""Before/After カルーセル試作の共通ヘルパー。

generate_carousel.py の純粋関数を import で再利用する。
本流の generate_carousel.py / instagram_api.py には一切手を入れない。
"""
from __future__ import annotations

import os
import sys

# リポジトリルートを sys.path に追加（generate_carousel.py を import するため）
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from PIL import Image, ImageDraw, ImageFont, ImageFilter  # noqa: E402

from generate_carousel import (  # noqa: E402
    W,
    H,
    normalize_text,
    crop_center,
    get_font,
)

# --- スライド type 集合（generate_ba_carousel と post_ba_mixed の両方で参照） ---
IMAGE_SLIDE_TYPES = frozenset({
    "ba_split",
    "ba_cover",
    "ba_text_overlay",
    "ba_grid_compare",
    "ba_duration",
    "ba_points",
    "ba_cta",
})
VIDEO_SLIDE_TYPES = frozenset({"video_passthrough"})

# --- 既存（compose_ba_split / draw_speech_bubble 用） ---
PINK = (100, 30, 60, 255)
WHITE = (255, 255, 255, 255)

# --- variant_a_magazine カラーパレット（design_lab/variants/variant_a_magazine.py から移植） ---
CREAM = (250, 246, 241, 255)
CREAM_BAND = (250, 246, 241, 245)
INK = (43, 37, 34, 255)
GOLD = (184, 148, 90, 255)  # variant_a の金（既存の (212,175,55) より落ち着いた色）
GOLD_LIGHT = (200, 175, 130, 255)
DARK_OVERLAY = (28, 25, 22, 200)  # text_overlay 用の暗背景

# --- 明朝フォント探索パス（design_lab/variants/_base.py から移植） ---
SERIF_PATHS = [
    "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc",
    "/Library/Fonts/Hiragino Mincho ProN.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJKjp-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSerifCJK-Regular.ttc",
]


def get_serif_font(size: int):
    """明朝フォントを取得（macOS: ヒラギノ明朝 / Linux: Noto Serif CJK）。
    見つからない場合は既存 get_font（角ゴ）にフォールバック。"""
    for path in SERIF_PATHS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return get_font(size)


def _resolve_color(name_or_tuple, default=GOLD):
    if isinstance(name_or_tuple, (tuple, list)):
        return tuple(name_or_tuple)
    if name_or_tuple == "gold":
        return GOLD
    if name_or_tuple == "white":
        return WHITE
    if name_or_tuple == "pink":
        return PINK
    return default


def compose_ba_split(
    before_path: str,
    after_path: str,
    labels: dict | None = None,
    divider: dict | None = None,
    bubble: dict | None = None,
) -> Image.Image:
    """Before/After を縦の境界線で左右分割した 1 スライド画像を生成する。

    Args:
        before_path: Before 画像パス
        after_path: After 画像パス
        labels: {"left": "Before", "right": "After"} （省略可）
        divider: {"color": "gold"|"white"|[r,g,b,a], "width": int}
        bubble: speech bubble オプション（draw_speech_bubble の引数を dict で）
    """
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))

    half_size = (W // 2, H)
    with Image.open(before_path) as bi:
        before_cropped = crop_center(bi.convert("RGBA"), half_size)
    with Image.open(after_path) as ai:
        after_cropped = crop_center(ai.convert("RGBA"), half_size)

    canvas.paste(before_cropped, (0, 0))
    canvas.paste(after_cropped, (W // 2, 0))

    draw = ImageDraw.Draw(canvas)

    # 中央の縦境界線
    div = divider or {"color": "gold", "width": 6}
    div_rgb = _resolve_color(div.get("color", "gold"), GOLD)
    div_width = int(div.get("width", 6))
    cx = W // 2
    draw.rectangle(
        [cx - div_width // 2, 0, cx + div_width // 2, H],
        fill=div_rgb,
    )

    # ラベルバッジ
    if labels:
        _draw_label_badges(canvas, labels)

    # 吹き出し
    if bubble:
        draw_speech_bubble(
            canvas,
            text=bubble.get("text", ""),
            position=bubble.get("position", "bottom-right"),
            style=bubble.get("style"),
        )

    return canvas


def _draw_label_badges(
    canvas: Image.Image,
    labels: dict,
    *,
    font_size: int = 48,
    y: int = 60,
):
    """画像上部に "Before" / "After" の半透明バッジを描く。"""
    font = get_font(font_size)
    draw = ImageDraw.Draw(canvas)
    for side, text in labels.items():
        if not text:
            continue
        text = normalize_text(text)
        bbox = font.getbbox(text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        pad_x = 32
        pad_y = 14
        center_x = W // 4 if side == "left" else 3 * W // 4
        x0 = center_x - (tw // 2) - pad_x
        x1 = center_x + (tw // 2) + pad_x
        y0 = y
        y1 = y + th + pad_y * 2

        # 半透明バッジ
        badge = Image.new("RGBA", (x1 - x0, y1 - y0), (255, 255, 255, 210))
        canvas.paste(badge, (x0, y0), badge)

        # 枠と文字を描き直す（paste で枠は消えないが、テキストは badge の上に描く）
        draw.rounded_rectangle([x0, y0, x1, y1], radius=14, outline=GOLD, width=2)
        tx = center_x - tw // 2
        ty = y + pad_y
        draw.text((tx, ty), text, font=font, fill=PINK)


def wrap_bubble_text(text: str, font, max_width: int) -> list[str]:
    """全角混在テキストを max_width(px) に収まるよう改行する。

    既存の `\\n` は改行として尊重した上で、各行を 1 文字ずつ追加して
    幅を超えたタイミングで改行する単純実装。
    """
    text = normalize_text(text)
    out: list[str] = []
    for raw_line in text.split("\n"):
        if not raw_line:
            out.append("")
            continue
        cur = ""
        for ch in raw_line:
            test = cur + ch
            bbox = font.getbbox(test)
            if (bbox[2] - bbox[0]) > max_width and cur:
                out.append(cur)
                cur = ch
            else:
                cur = test
        if cur:
            out.append(cur)
    return out


def draw_speech_bubble(
    canvas: Image.Image,
    text: str,
    position="bottom-right",
    style: dict | None = None,
):
    """角丸長方形＋三角しっぽの吹き出しを描画する（汎用デザイン版）。

    position:
        プリセット名 "top-left" / "top-right" / "bottom-left" / "bottom-right" / "center"
        または座標 dict {"x": int, "y": int, "anchor": "tl"|"tr"|"bl"|"br"|None}
    style: 形状・色のオプション（dict）
    """
    style = style or {}
    max_width = int(style.get("max_width", 380))
    padding = int(style.get("padding", 22))
    radius = int(style.get("radius", 26))
    font_size = int(style.get("font_size", 38))
    fill = tuple(style.get("fill", (255, 255, 255, 235)))
    outline = tuple(style.get("outline", PINK))
    outline_width = int(style.get("outline_width", 3))
    text_color = tuple(style.get("text_color", PINK))
    tail_size = int(style.get("tail_size", 22))

    font = get_font(font_size)

    lines = wrap_bubble_text(text, font, max_width - padding * 2)
    if not lines:
        lines = [""]

    sample_bbox = font.getbbox("あ")
    line_h = (sample_bbox[3] - sample_bbox[1]) + 8
    text_w = max(
        (font.getbbox(line)[2] - font.getbbox(line)[0]) for line in lines
    )
    text_h = line_h * len(lines)

    box_w = text_w + padding * 2
    box_h = text_h + padding * 2

    margin = 60
    if isinstance(position, str):
        if position == "top-left":
            box_x, box_y, tail_anchor = margin, margin, "bl"
        elif position == "top-right":
            box_x, box_y, tail_anchor = W - box_w - margin, margin, "br"
        elif position == "bottom-left":
            box_x, box_y, tail_anchor = margin, H - box_h - margin, "tl"
        elif position == "bottom-right":
            box_x, box_y, tail_anchor = W - box_w - margin, H - box_h - margin, "tr"
        elif position == "center":
            box_x, box_y, tail_anchor = (W - box_w) // 2, (H - box_h) // 2, None
        else:
            box_x, box_y, tail_anchor = W - box_w - margin, H - box_h - margin, "tr"
    elif isinstance(position, dict):
        box_x = int(position.get("x", margin))
        box_y = int(position.get("y", margin))
        tail_anchor = position.get("anchor")
    else:
        box_x, box_y, tail_anchor = margin, margin, None

    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        [box_x, box_y, box_x + box_w, box_y + box_h],
        radius=radius,
        fill=fill,
        outline=outline,
        width=outline_width,
    )

    # しっぽ（三角形）
    tail_pts = None
    if tail_anchor == "bl":
        tip_x = box_x + box_w // 4
        tail_pts = [
            (tip_x, box_y + box_h),
            (tip_x + tail_size, box_y + box_h),
            (tip_x - tail_size // 2, box_y + box_h + tail_size),
        ]
    elif tail_anchor == "br":
        tip_x = box_x + 3 * box_w // 4
        tail_pts = [
            (tip_x - tail_size, box_y + box_h),
            (tip_x, box_y + box_h),
            (tip_x + tail_size // 2, box_y + box_h + tail_size),
        ]
    elif tail_anchor == "tl":
        tip_x = box_x + box_w // 4
        tail_pts = [
            (tip_x, box_y),
            (tip_x + tail_size, box_y),
            (tip_x - tail_size // 2, box_y - tail_size),
        ]
    elif tail_anchor == "tr":
        tip_x = box_x + 3 * box_w // 4
        tail_pts = [
            (tip_x - tail_size, box_y),
            (tip_x, box_y),
            (tip_x + tail_size // 2, box_y - tail_size),
        ]

    if tail_pts is not None:
        draw.polygon(tail_pts, fill=fill, outline=outline)
        # 親矩形の枠線がしっぽの底辺を縦に切ってしまうので、底辺を fill 色で上塗り
        seg_y = tail_pts[0][1]
        x0 = min(tail_pts[0][0], tail_pts[1][0]) + 1
        x1 = max(tail_pts[0][0], tail_pts[1][0]) - 1
        draw.line([(x0, seg_y), (x1, seg_y)], fill=fill, width=outline_width)

    # テキスト（中央揃え）
    text_y = box_y + padding
    for line in lines:
        bbox = font.getbbox(line)
        lw = bbox[2] - bbox[0]
        cx_text = box_x + box_w // 2 - lw // 2
        draw.text((cx_text, text_y), line, font=font, fill=text_color)
        text_y += line_h


def save_image_jpg(img: Image.Image, output_path: str, quality: int = 92):
    """RGBA → RGB（白背景）に変換して JPEG 保存する。"""
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    img.save(output_path, "JPEG", quality=quality)


# =====================================================================
# variant_a_magazine スタイル（雑誌風・明朝・余白主義）
# 参考投稿 https://www.instagram.com/p/DXsigplk5C_/ をエステ向けに翻案
# =====================================================================


def _draw_centered(draw, text: str, font, y: int, fill, img_w: int = W) -> int:
    """1 行を中央揃えで描画。描画した高さを返す。"""
    text = normalize_text(text)
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (img_w - tw) // 2
    draw.text((x, y), text, font=font, fill=fill)
    return th


def _draw_multiline_centered(
    draw, text: str, font, y_start: int, fill, img_w: int = W, line_gap: int = 12
) -> int:
    """複数行を中央揃えで描画。最終 y を返す。"""
    text = normalize_text(text)
    y = y_start
    for line in text.split("\n"):
        if line:
            bbox = font.getbbox(line)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            x = (img_w - tw) // 2
            draw.text((x, y), line, font=font, fill=fill)
            y += th + line_gap
        else:
            sample = font.getbbox("あ")
            y += (sample[3] - sample[1]) + line_gap
    return y


def _hairline(draw, y: int, x1: int = 120, x2: int = W - 120, fill=GOLD, width: int = 1):
    """variant_a の細い金色罫線。"""
    draw.line([(x1, y), (x2, y)], fill=fill, width=width)


def _wrap_text(text: str, font, max_width: int) -> list[str]:
    """全角混在テキストを max_width(px) で逐次折返し（既存 wrap_bubble_text と同等）。"""
    text = normalize_text(text)
    out: list[str] = []
    for raw in text.split("\n"):
        if not raw:
            out.append("")
            continue
        cur = ""
        for ch in raw:
            test = cur + ch
            bbox = font.getbbox(test)
            if (bbox[2] - bbox[0]) > max_width and cur:
                out.append(cur)
                cur = ch
            else:
                cur = test
        if cur:
            out.append(cur)
    return out


def _open_resized(path: str, target_size: tuple[int, int]) -> Image.Image:
    """画像を target_size に crop_center で揃える。"""
    with Image.open(path) as src:
        return crop_center(src.convert("RGBA"), target_size)


def _open_resized_zoomed(
    path: str,
    target_size: tuple[int, int],
    zoom: float = 1.0,
) -> Image.Image:
    """zoom>1.0 のときは被写体をクローズアップ（全身→頭〜腰のような構図にトリミング）。
    zoom<=1.0 は通常の cover-fit と同じ。
    実装メモ：crop_center は内部で再フィットしてしまうため、先に target アスペクト比へ
    center-crop → zoom>1 なら中央 1/zoom 領域をさらに切り出し → 最後に target に resize、
    という順序で zoom が確実に効くようにしている。"""
    with Image.open(path) as src:
        img = src.convert("RGBA")
        w, h = img.size
        tw, th = target_size

        # 1) target アスペクト比に center-crop
        target_ratio = tw / th
        src_ratio = w / h
        if src_ratio > target_ratio:
            # 横長すぎ → 左右をカット
            new_w = int(h * target_ratio)
            x0 = (w - new_w) // 2
            img = img.crop((x0, 0, x0 + new_w, h))
        elif src_ratio < target_ratio:
            # 縦長すぎ → 上下をカット
            new_h = int(w / target_ratio)
            y0 = (h - new_h) // 2
            img = img.crop((0, y0, w, y0 + new_h))

        # 2) zoom > 1.0 のときは中央 1/zoom の領域だけにクロップ（=被写体クローズアップ）
        if zoom and zoom > 1.0:
            cw, ch = img.size
            inner_w = int(cw / zoom)
            inner_h = int(ch / zoom)
            x0 = (cw - inner_w) // 2
            y0 = (ch - inner_h) // 2
            img = img.crop((x0, y0, x0 + inner_w, y0 + inner_h))

        # 3) target サイズへ resize
        return img.resize(target_size, Image.LANCZOS)


def _circle_crop(img: Image.Image, size: int) -> Image.Image:
    """正方形にクロップして円形にマスクする。"""
    sq = crop_center(img.convert("RGBA"), (size, size))
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse([0, 0, size, size], fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(sq, (0, 0), mask)
    return out


# ---------------------------------------------------------------------
# 1) ba_cover ：参考 1 枚目スタイル
# ---------------------------------------------------------------------

def compose_ba_cover(
    before_path: str,
    after_path: str,
    upper_caption: str = "— 6ヶ月前",
    lower_caption: str = "現在 —",
    sub_text: str = "続く綺麗\n作れていますか？",
    bubble_text: str = "ベースを整えると、ここまで変わります。",
    miki_icon_path: str | None = None,
) -> Image.Image:
    """ベージュ背景 + ずらし配置の Before/After + 上下キャプション + 右上ボックス + 左下吹き出し+MIKI アイコン。"""
    canvas = Image.new("RGBA", (W, H), CREAM)
    draw = ImageDraw.Draw(canvas)

    # === Before（左上寄り）===
    before_box = (80, 200, 80 + 440, 200 + 560)  # 440x560
    before_img = _open_resized(before_path, (440, 560))
    canvas.paste(before_img, (before_box[0], before_box[1]), before_img)
    # 細い金色枠
    draw.rectangle(before_box, outline=GOLD, width=2)
    # 上部キャプション「— 6ヶ月前」
    cap_font = get_serif_font(34)
    cap_text = normalize_text(upper_caption)
    cap_bbox = cap_font.getbbox(cap_text)
    cap_w = cap_bbox[2] - cap_bbox[0]
    draw.text(
        (before_box[0] + (440 - cap_w) // 2, before_box[1] - 56),
        cap_text, font=cap_font, fill=INK,
    )

    # === After（右下寄り、Before より少し大きめ）===
    after_box = (560, 420, 560 + 460, 420 + 580)  # 460x580
    after_img = _open_resized(after_path, (460, 580))
    canvas.paste(after_img, (after_box[0], after_box[1]), after_img)
    draw.rectangle(after_box, outline=GOLD, width=2)
    # 下部キャプション「現在 —」
    cap2_text = normalize_text(lower_caption)
    cap2_bbox = cap_font.getbbox(cap2_text)
    cap2_w = cap2_bbox[2] - cap2_bbox[0]
    draw.text(
        (after_box[0] + (460 - cap2_w) // 2, after_box[3] + 14),
        cap2_text, font=cap_font, fill=INK,
    )

    # === 右上：問いかけボックス ===
    box_x0, box_y0 = 660, 80
    box_x1, box_y1 = box_x0 + 360, box_y0 + 220
    # 半透明 CREAM でテクスチャを残す
    bx_layer = Image.new("RGBA", (box_x1 - box_x0, box_y1 - box_y0), CREAM_BAND)
    canvas.paste(bx_layer, (box_x0, box_y0), bx_layer)
    draw.rounded_rectangle([box_x0, box_y0, box_x1, box_y1], radius=18, outline=GOLD, width=1)
    # 内部テキスト
    sub_font = get_serif_font(30)
    sub_lines = sub_text.split("\n")
    line_h = sub_font.getbbox("あ")[3] - sub_font.getbbox("あ")[1] + 14
    total_h = len(sub_lines) * line_h
    sub_y = box_y0 + (box_y1 - box_y0 - total_h) // 2
    for line in sub_lines:
        line = normalize_text(line)
        bbox = sub_font.getbbox(line)
        lw = bbox[2] - bbox[0]
        draw.text(
            (box_x0 + (box_x1 - box_x0 - lw) // 2, sub_y),
            line, font=sub_font, fill=INK,
        )
        sub_y += line_h

    # === 左下：MIKI アイコン + 吹き出し ===
    icon_size = 130
    icon_x, icon_y = 60, 1140
    if miki_icon_path and os.path.exists(miki_icon_path):
        icon = _circle_crop(Image.open(miki_icon_path), icon_size)
        canvas.paste(icon, (icon_x, icon_y), icon)
        # 円の枠（金）
        draw.ellipse(
            [icon_x, icon_y, icon_x + icon_size, icon_y + icon_size],
            outline=GOLD, width=2,
        )
    else:
        # プレースホルダ：CREAM 円
        draw.ellipse(
            [icon_x, icon_y, icon_x + icon_size, icon_y + icon_size],
            fill=(220, 210, 195, 255), outline=GOLD, width=2,
        )
        ph_font = get_serif_font(28)
        ph_text = "MIKI"
        pb = ph_font.getbbox(ph_text)
        draw.text(
            (icon_x + (icon_size - (pb[2] - pb[0])) // 2,
             icon_y + (icon_size - (pb[3] - pb[1])) // 2 - 4),
            ph_text, font=ph_font, fill=INK,
        )

    # 吹き出し本体（角丸長方形 + 左に三角しっぽ）
    bub_x0 = icon_x + icon_size + 24
    bub_y0 = icon_y - 20
    bub_x1 = W - 60
    bub_y1 = bub_y0 + icon_size + 40
    draw.rounded_rectangle(
        [bub_x0, bub_y0, bub_x1, bub_y1],
        radius=22, fill=(255, 255, 255, 235), outline=GOLD, width=2,
    )
    # 左側に三角しっぽ（アイコンに向く）
    tail = [
        (bub_x0, bub_y0 + 70),
        (bub_x0, bub_y0 + 110),
        (bub_x0 - 20, bub_y0 + 88),
    ]
    draw.polygon(tail, fill=(255, 255, 255, 235), outline=GOLD)
    # しっぽの右端ラインを白で上塗り（rounded_rectangle の枠を消す）
    draw.line(
        [(bub_x0 + 1, bub_y0 + 70 + 1), (bub_x0 + 1, bub_y0 + 110 - 1)],
        fill=(255, 255, 255, 235), width=2,
    )

    # 吹き出し内テキスト：吹き出し領域に収まるまでフォントを段階縮小
    inner_w = (bub_x1 - bub_x0) - 40
    inner_h = (bub_y1 - bub_y0) - 24
    bub_size = 30
    while bub_size >= 22:
        bub_font = get_serif_font(bub_size)
        bub_lines = _wrap_text(bubble_text, bub_font, inner_w)
        bub_line_h = bub_font.getbbox("あ")[3] - bub_font.getbbox("あ")[1] + 12
        bub_total_h = len(bub_lines) * bub_line_h
        if bub_total_h <= inner_h:
            break
        bub_size -= 4
    by = bub_y0 + ((bub_y1 - bub_y0) - bub_total_h) // 2
    for line in bub_lines:
        bbox = bub_font.getbbox(line)
        lw = bbox[2] - bbox[0]
        draw.text(
            (bub_x0 + ((bub_x1 - bub_x0) - lw) // 2, by),
            line, font=bub_font, fill=INK,
        )
        by += bub_line_h

    return canvas


# ---------------------------------------------------------------------
# 2) ba_text_overlay ：参考 3 枚目スタイル
# ---------------------------------------------------------------------

def compose_ba_text_overlay(
    images: list[str],
    top_text: str,
    bottom_text: str,
    *,
    bottom_keywords: str | None = None,  # オプション: ハイライト前の太字行
    layout: str = "horizontal",  # "horizontal" (横並び) or "stacked" (上下2段)
    strip_h: int = 410,  # 画像帯の高さ。広げる＝画像の上下クロップが減る／文字エリアは縮む
) -> Image.Image:
    """画像並び + 上下に暗オーバーレイ + 白の明朝テキスト。
    layout="stacked" のときは画像 2 枚を上下に並べる（横長画像向け）。
    strip_h を 410 より大きくすると画像が target に近いアスペクト比になり
    クロップ量が減る（画像全体が見えやすくなる）。"""
    canvas = Image.new("RGBA", (W, H), INK[:3] + (255,))

    # === 中央：画像帯 ===
    n = len(images)
    if n < 1:
        raise ValueError("ba_text_overlay には画像が 1 枚以上必要")
    # 画像帯を canvas 中央に置く（strip_h=410 のとき strip_y=470 で従来挙動と一致）
    strip_y = (H - strip_h) // 2
    if layout == "stacked" and n == 2:
        # 上下 2 段（横長画像を 2 枚スタック）
        cell_h = strip_h // 2
        for i, p in enumerate(images):
            cell = _open_resized(p, (W, cell_h))
            canvas.paste(cell, (0, strip_y + i * cell_h), cell)
    else:
        # 横並び
        cell_w = W // n
        for i, p in enumerate(images):
            cell = _open_resized(p, (cell_w, strip_h))
            canvas.paste(cell, (i * cell_w, strip_y), cell)

    # 上下に半透明黒オーバーレイ（明確に区切る）
    upper = Image.new("RGBA", (W, strip_y), (28, 25, 22, 240))
    canvas.paste(upper, (0, 0), upper)
    lower = Image.new("RGBA", (W, H - (strip_y + strip_h)), (28, 25, 22, 240))
    canvas.paste(lower, (0, strip_y + strip_h), lower)

    # ストリップにも軽くトーンダウンの黒オーバーレイ
    tone = Image.new("RGBA", (W, strip_h), (0, 0, 0, 60))
    canvas.paste(tone, (0, strip_y), tone)

    draw = ImageDraw.Draw(canvas)

    # === 上部テキスト ===
    title_font = get_serif_font(48)
    title_lines = top_text.split("\n")
    line_h = title_font.getbbox("あ")[3] - title_font.getbbox("あ")[1] + 18
    block_h = len(title_lines) * line_h
    ty = (strip_y - block_h) // 2 + 10
    for line in title_lines:
        line = normalize_text(line)
        bbox = title_font.getbbox(line)
        lw = bbox[2] - bbox[0]
        draw.text(((W - lw) // 2, ty), line, font=title_font, fill=WHITE)
        ty += line_h
    # 下にゴールドの細線
    _hairline(draw, ty + 10, x1=W // 2 - 60, x2=W // 2 + 60, width=2)

    # === 下部テキスト ===
    bottom_y = strip_y + strip_h + 60
    if bottom_keywords:
        kw_font = get_serif_font(50)
        kw_text = normalize_text(bottom_keywords)
        bbox = kw_font.getbbox(kw_text)
        lw = bbox[2] - bbox[0]
        draw.text(
            ((W - lw) // 2, bottom_y),
            kw_text, font=kw_font, fill=WHITE,
        )
        bottom_y += (bbox[3] - bbox[1]) + 36

    body_font = get_serif_font(40)
    for line in bottom_text.split("\n"):
        line = normalize_text(line)
        bbox = body_font.getbbox(line)
        lw = bbox[2] - bbox[0]
        draw.text(((W - lw) // 2, bottom_y), line, font=body_font, fill=WHITE)
        bottom_y += (bbox[3] - bbox[1]) + 16

    return canvas


# ---------------------------------------------------------------------
# 3) ba_grid_compare ：参考 4-5 枚目スタイル
# ---------------------------------------------------------------------

def compose_ba_grid_compare(
    pairs: list[tuple[str, str]],
    title: str = "施術例",
    subtitle: str = "担当したお客様の変化",
) -> Image.Image:
    """2列×N行の Before→After グリッド。各行に金矢印。"""
    if not pairs:
        raise ValueError("ba_grid_compare には pairs が 1 組以上必要")

    canvas = Image.new("RGBA", (W, H), CREAM)
    draw = ImageDraw.Draw(canvas)

    # === ヘッダー ===
    title_font = get_serif_font(42)
    subt_font = get_font(26)
    _hairline(draw, 64, x1=80, x2=W - 80, width=1)
    _draw_centered(draw, title, title_font, 80, INK)
    _hairline(draw, 138, x1=80, x2=W - 80, width=1)
    _draw_centered(draw, subtitle, subt_font, 156, INK)

    # === グリッド ===
    grid_top = 220
    grid_bottom = H - 60
    n_rows = len(pairs)
    row_gap = 18
    row_h = (grid_bottom - grid_top - row_gap * (n_rows - 1)) // n_rows
    cell_w = 410
    arrow_w = 130
    side_margin = (W - cell_w * 2 - arrow_w) // 2

    for i, (b_path, a_path) in enumerate(pairs):
        row_y = grid_top + i * (row_h + row_gap)
        # Before
        b_img = _open_resized(b_path, (cell_w, row_h))
        canvas.paste(b_img, (side_margin, row_y), b_img)
        draw.rectangle(
            [side_margin, row_y, side_margin + cell_w, row_y + row_h],
            outline=GOLD, width=2,
        )
        # After
        a_x = side_margin + cell_w + arrow_w
        a_img = _open_resized(a_path, (cell_w, row_h))
        canvas.paste(a_img, (a_x, row_y), a_img)
        draw.rectangle(
            [a_x, row_y, a_x + cell_w, row_y + row_h],
            outline=GOLD, width=2,
        )
        # 矢印（金）— 先端は After 枠まで 15px 余白を残す
        ax_center = side_margin + cell_w + arrow_w // 2
        ay_center = row_y + row_h // 2
        arrow_pts = [
            (ax_center - 38, ay_center - 22),
            (ax_center + 8, ay_center - 22),
            (ax_center + 8, ay_center - 36),
            (ax_center + 40, ay_center),
            (ax_center + 8, ay_center + 36),
            (ax_center + 8, ay_center + 22),
            (ax_center - 38, ay_center + 22),
        ]
        draw.polygon(arrow_pts, fill=GOLD)

    return canvas


# ---------------------------------------------------------------------
# 4) ba_duration ：参考 6 枚目スタイル
# ---------------------------------------------------------------------

def compose_ba_duration(
    before_path: str,
    after_path: str,
    headline: str = "半年〜1年で\n続く美しさ",
    body: str = "美髪ストレートの周期\n癖の強い方　4ヶ月〜半年（目安）\n弱い方　半年〜1年半（目安）",
    before_label: str = "初回来店時",
    after_label: str = "再来店時",
    image_zoom: float = 1.0,
) -> Image.Image:
    """上半分に Before/After 大きめ + 中央テキスト、下半分に暗背景の説明ボックス。
    image_zoom>1.0 で被写体をクローズアップ（全身→頭〜腰の構図にトリミング）。"""
    canvas = Image.new("RGBA", (W, H), CREAM)

    # === 上半分：Before / After 全幅 ===
    upper_h = 720
    half_w = W // 2
    before_img = _open_resized_zoomed(before_path, (half_w, upper_h), zoom=image_zoom)
    after_img = _open_resized_zoomed(after_path, (half_w, upper_h), zoom=image_zoom)
    canvas.paste(before_img, (0, 0), before_img)
    canvas.paste(after_img, (half_w, 0), after_img)

    # 暗オーバーレイ（中央テキスト読みやすさのため）
    tone = Image.new("RGBA", (W, upper_h), (0, 0, 0, 90))
    canvas.paste(tone, (0, 0), tone)

    draw = ImageDraw.Draw(canvas)

    # 中央ヘッドライン（白の明朝、シャドウ）
    h_font = get_serif_font(58)
    h_lines = headline.split("\n")
    line_h = h_font.getbbox("あ")[3] - h_font.getbbox("あ")[1] + 18
    total = len(h_lines) * line_h
    hy = (upper_h - total) // 2
    for line in h_lines:
        line = normalize_text(line)
        bbox = h_font.getbbox(line)
        lw = bbox[2] - bbox[0]
        x = (W - lw) // 2
        draw.text((x + 2, hy + 2), line, font=h_font, fill=(0, 0, 0, 120))
        draw.text((x, hy), line, font=h_font, fill=WHITE)
        hy += line_h

    # 下部のラベル「初回来店時」「再来店時」（空文字列なら非表示）
    if before_label or after_label:
        lab_font = get_serif_font(34)
        lab_y = upper_h - 70
        for label, x_center in [(before_label, half_w // 2), (after_label, half_w + half_w // 2)]:
            if not label:
                continue
            text = normalize_text(label)
            bbox = lab_font.getbbox(text)
            lw = bbox[2] - bbox[0]
            draw.text((x_center - lw // 2, lab_y), text, font=lab_font, fill=WHITE)

    # === 下半分：暗背景ボックス ===
    box_top = upper_h
    box = Image.new("RGBA", (W, H - box_top), (42, 36, 32, 250))
    canvas.paste(box, (0, box_top), box)

    body_font = get_serif_font(40)
    body_lines = body.split("\n")
    bline_h = body_font.getbbox("あ")[3] - body_font.getbbox("あ")[1] + 26
    btotal = len(body_lines) * bline_h
    by = box_top + ((H - box_top) - btotal) // 2
    for i, line in enumerate(body_lines):
        line = normalize_text(line)
        bbox = body_font.getbbox(line)
        lw = bbox[2] - bbox[0]
        # 1 行目（見出し）はやや大きめ
        if i == 0:
            heading_font = get_serif_font(46)
            hb = heading_font.getbbox(line)
            lw = hb[2] - hb[0]
            draw.text(((W - lw) // 2, by), line, font=heading_font, fill=GOLD_LIGHT)
            by += (hb[3] - hb[1]) + 32
        else:
            draw.text(((W - lw) // 2, by), line, font=body_font, fill=WHITE)
            by += bline_h

    return canvas


# ---------------------------------------------------------------------
# 5) ba_points ：参考 7-8 枚目スタイル
# ---------------------------------------------------------------------

def compose_ba_points(
    title: str,
    items: list[dict],  # [{image, label, heading, body}, ...]
) -> Image.Image:
    """暗背景に「Point1〜3」のレイアウト。各行は左に画像、右にテキスト。"""
    if not items:
        raise ValueError("ba_points には items が 1 件以上必要")

    canvas = Image.new("RGBA", (W, H), (42, 36, 32, 255))
    draw = ImageDraw.Draw(canvas)

    # === ヘッダー ===
    title_font = get_serif_font(56)
    _draw_multiline_centered(draw, title, title_font, 80, WHITE, line_gap=14)
    # 区切りの逆三角（参考画像）
    cx = W // 2
    tri_y = 230
    draw.polygon(
        [(cx - 14, tri_y), (cx + 14, tri_y), (cx, tri_y + 18)],
        fill=GOLD_LIGHT,
    )

    # === ブロック ===
    block_top = 280
    block_bottom = H - 40
    n = len(items)
    block_gap = 24
    block_h = (block_bottom - block_top - block_gap * (n - 1)) // n
    img_w = 290
    img_h = block_h - 20

    # レイアウト：画像 + ギャップ + テキスト で構成されるブロックを横方向中央に揃える
    #   左右の余白が同じになるように image_x を計算する
    gap = 30
    text_w = 480  # テキストの折り返し幅（最長見出し「素直な気持ちを持つこと」+ 余白を確保）
    content_w = img_w + gap + text_w
    image_x = (W - content_w) // 2  # 例：(1080 - 800) // 2 = 140
    text_x = image_x + img_w + gap

    label_font = get_font(22)

    for i, item in enumerate(items):
        by = block_top + i * (block_h + block_gap)
        block_y_end = by + block_h  # この block の下端（次 block と被ってはいけない）
        # 画像
        if item.get("image") and os.path.exists(item["image"]):
            img = _open_resized(item["image"], (img_w, img_h))
            canvas.paste(img, (image_x, by + 10), img)
        else:
            draw.rectangle(
                [image_x, by + 10, image_x + img_w, by + 10 + img_h],
                fill=(70, 60, 52, 255), outline=GOLD_LIGHT, width=1,
            )

        # ラベル（"Point1" など）+ 細線
        label = item.get("label", f"Point{i + 1}")
        draw.text((text_x, by + 8), label, font=label_font, fill=GOLD_LIGHT)
        lab_bbox = label_font.getbbox(label)
        lab_h = lab_bbox[3] - lab_bbox[1]
        line_y = by + 8 + lab_h + 8
        draw.line([(text_x, line_y), (text_x + 200, line_y)], fill=GOLD_LIGHT, width=1)

        # 見出し（明朝）：block 内に収まるサイズに自動縮小
        heading = item.get("heading", "")
        body_text = item.get("body", "")
        head_y = line_y + 22
        text_area_top = head_y
        text_area_bottom = block_y_end - 6  # 余白 6px

        head_size = 38
        body_size = 26
        # 縮小ループ：見出し + 本文の合計高さが block 内に収まるまで段階的に縮める
        for attempt in range(4):
            head_font = get_serif_font(head_size)
            body_font = get_font(body_size)
            head_lines = _wrap_text(heading, head_font, text_w)
            body_lines = _wrap_text(body_text, body_font, text_w)
            head_line_h = head_font.getbbox("あ")[3] - head_font.getbbox("あ")[1] + 8
            body_line_h = body_font.getbbox("あ")[3] - body_font.getbbox("あ")[1] + 10
            total_h = (
                len(head_lines) * head_line_h + 12
                + len(body_lines) * body_line_h
            )
            if text_area_top + total_h <= text_area_bottom:
                break
            head_size -= 4
            body_size -= 2
            if head_size < 26:
                head_size = 26
                body_size = max(20, body_size)
                break

        for hl in head_lines:
            draw.text((text_x, head_y), hl, font=head_font, fill=WHITE)
            head_y += head_line_h

        body_y = head_y + 12
        for bl in body_lines:
            if body_y + body_line_h > text_area_bottom:
                break  # クリッピング：block 外には描かない
            draw.text((text_x, body_y), bl, font=body_font, fill=(220, 215, 205, 255))
            body_y += body_line_h

    return canvas


# ---------------------------------------------------------------------
# 6) ba_cta ：本流の CTA タイトル（CLAUDE.md 恒久ルール）に揃える
# ---------------------------------------------------------------------

def compose_ba_cta(
    title: str = "MIKI指名 初回限定20%OFF\n（VIPコースのみ）",
    body: str = "美容と健康に興味がある。\n素直に自分と向き合える。\nそんな方、ぜひ会いに来てください。",
    subtitle: str = "ご予約・ご相談はDMからお気軽にどうぞ",
    bg_image: str | None = None,
) -> Image.Image:
    """variant_a の cta スタイル。本流ルールに従い、タイトルは恒久固定文言を既定値に。"""
    canvas = Image.new("RGBA", (W, H), CREAM)

    # 上 1/3 に背景写真があれば配置
    photo_h = 0
    if bg_image and os.path.exists(bg_image):
        photo_h = int(H * 0.32)
        photo = _open_resized(bg_image, (W, photo_h))
        canvas.paste(photo, (0, 0), photo)
        # 軽いオーバーレイで上品に
        tone = Image.new("RGBA", (W, photo_h), (250, 246, 241, 60))
        canvas.paste(tone, (0, 0), tone)

    draw = ImageDraw.Draw(canvas)
    if photo_h > 0:
        draw.line([(0, photo_h), (W, photo_h)], fill=GOLD, width=2)

    title_font = get_serif_font(50)
    body_font = get_font(32)
    sub_font = get_font(28)

    band_y = photo_h
    band_h = H - band_y

    # コンテンツの中央寄せ
    title_text = normalize_text(title)
    body_text = normalize_text(body)
    sub_text = normalize_text(subtitle)

    title_lines = title_text.split("\n")
    body_lines = body_text.split("\n")
    sub_lines = sub_text.split("\n")

    title_lh = title_font.getbbox("あ")[3] - title_font.getbbox("あ")[1] + 16
    body_lh = body_font.getbbox("あ")[3] - body_font.getbbox("あ")[1] + 14
    sub_lh = sub_font.getbbox("あ")[3] - sub_font.getbbox("あ")[1] + 10

    block_h = (
        len(title_lines) * title_lh
        + 30 + 60
        + len(body_lines) * body_lh
        + 50 + 30
        + len(sub_lines) * sub_lh
    )
    y = band_y + (band_h - block_h) // 2
    if photo_h > 0:
        # 写真ありの場合は写真下バンド内で +20px のオフセットを加える
        # （写真の存在感とバランスを取るための余白）
        y += 20

    for line in title_lines:
        bbox = title_font.getbbox(line)
        lw = bbox[2] - bbox[0]
        draw.text(((W - lw) // 2, y), line, font=title_font, fill=INK)
        y += title_lh

    y += 18
    _hairline(draw, y, x1=W // 2 - 60, x2=W // 2 + 60, width=2)
    y += 50

    for line in body_lines:
        bbox = body_font.getbbox(line)
        lw = bbox[2] - bbox[0]
        draw.text(((W - lw) // 2, y), line, font=body_font, fill=INK)
        y += body_lh

    y += 30
    _hairline(draw, y, x1=W // 2 - 50, x2=W // 2 + 50, width=2)
    y += 30

    for line in sub_lines:
        bbox = sub_font.getbbox(line)
        lw = bbox[2] - bbox[0]
        draw.text(((W - lw) // 2, y), line, font=sub_font, fill=GOLD)
        y += sub_lh

    return canvas
