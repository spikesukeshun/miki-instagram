"""Variant A — 雑誌風・明朝・余白主義

Concept:
- 金二重枠を撤廃。装飾は余白そのもの
- カバーは「写真上半分／タイトル下半分」の二分割。タイトルは明朝で大きく
- 全スライドの下1/3にクリーム帯 → グリッドに並ぶと帯が揃って秩序が出る
- パレット: クリーム(#FAF6F1) × 墨(#2B2522) × アクセント金(#B8945A)
"""
from PIL import Image, ImageDraw

from . import _base as B

NAME = "variant_a_magazine"
LABEL = "案A：明朝・余白主義（雑誌風）"

CREAM = (250, 246, 241, 255)
INK = (43, 37, 34, 255)
GOLD = (184, 148, 90, 255)
CREAM_BAND = (250, 246, 241, 245)


def _bottom_band(img, height_ratio=0.36):
    h = int(B.H * height_ratio)
    y = B.H - h
    return B.paste_band(img, y, h, CREAM_BAND), y, h


def _hairline(draw, y, x1=120, x2=B.W - 120, fill=GOLD, width=1):
    draw.line([(x1, y), (x2, y)], fill=fill, width=width)


def generate_cover(img, slide):
    """カバー：写真エリア（上 photo_h_ratio）と クリーム帯（下）に明確に分割。
    写真は写真エリアのアスペクト比（1080×photo_h）にフィットさせるため、4:5
    クロップで失う情報が出ない。focus_y で縦のフォーカス位置を調整できる。"""
    photo_h_ratio = float(slide.get("photo_h_ratio", 0.55))
    focus_y = float(slide.get("focus_y", 0.5))

    photo_h = int(B.H * photo_h_ratio)         # ≈ 743
    photo = B.crop_center_with_focus(img, focus_y=focus_y,
                                     size=(B.W, photo_h)).convert("RGBA")

    canvas = Image.new("RGBA", (B.W, B.H), CREAM)
    canvas.paste(photo, (0, 0))
    draw = ImageDraw.Draw(canvas)

    band_y = photo_h
    band_h = B.H - band_y                       # ≈ 607

    # 写真と帯の境界に細いゴールドライン（雑誌の罫線）
    draw.line([(0, band_y), (B.W, band_y)], fill=GOLD, width=2)

    title_font = B.get_serif(110)
    kicker_font = B.get_sans(28)
    tag_font = B.get_serif(32)

    kicker = B.normalize_text(slide.get("kicker", "")).upper()
    title = B.normalize_text(slide.get("title", ""))
    tag = B.normalize_text(slide.get("tag", ""))

    inner_y = band_y + 36

    if kicker:
        B.draw_centered(draw, kicker, kicker_font, inner_y, B.W, GOLD)
        inner_y += 50
        _hairline(draw, inner_y + 6, x1=B.W // 2 - 30, x2=B.W // 2 + 30, width=2)
        inner_y += 28

    title_h = B.measure_lines(title_font, title, line_gap=14)
    bottom_reserve = 84 if tag else 40
    available_h = (B.H - bottom_reserve) - inner_y
    title_y = inner_y + max(0, (available_h - title_h) // 2)
    B.draw_multiline_centered(draw, title, title_font, title_y, B.W, INK,
                              line_gap=14)

    if tag:
        B.draw_centered(draw, tag, tag_font, B.H - 56, B.W, INK)

    return canvas.convert("RGB")


def _slide_frame(img, slide, default_ratio=0.35):
    """text/list/cta スライドの背景。上 photo_h_ratio に写真エリア、下にクリーム帯。
    slide['slide_photo_h_ratio'] = 0 で写真なし純クリームスライド。
    slide['focus_y'] で被写体の縦位置を調整（0.0=上端、0.5=中央、1.0=下端）。"""
    ratio = float(slide.get("slide_photo_h_ratio", default_ratio))
    ratio = max(0.0, min(0.6, ratio))
    canvas = Image.new("RGBA", (B.W, B.H), CREAM)
    if ratio > 0 and img is not None:
        focus_y = float(slide.get("focus_y", 0.5))
        photo_h = int(B.H * ratio)
        photo = B.crop_center_with_focus(img, focus_y=focus_y,
                                         size=(B.W, photo_h)).convert("RGBA")
        canvas.paste(photo, (0, 0))
        draw = ImageDraw.Draw(canvas)
        draw.line([(0, photo_h), (B.W, photo_h)], fill=GOLD, width=2)
        band_y = photo_h
    else:
        band_y = 0
    band_h = B.H - band_y
    return canvas, band_y, band_h


def generate_text_slide(img, slide):
    img, band_y, band_h = _slide_frame(img, slide)
    draw = ImageDraw.Draw(img)

    title_font = B.get_serif(56)
    body_font = B.get_sans(34)
    LINE_H = 56

    title = B.normalize_text(slide.get("title", ""))
    body = B.normalize_text(slide.get("text", ""))

    title_h = B.measure_lines(title_font, title, line_gap=12)
    body_lines = body.split("\n")
    body_h = len(body_lines) * LINE_H
    block_h = title_h + 30 + 1 + 80 + body_h
    start_y = band_y + (band_h - block_h) // 2

    end_title_y = B.draw_multiline_centered(draw, title, title_font, start_y,
                                            B.W, INK, line_gap=12)
    rule_y = end_title_y + 18
    _hairline(draw, rule_y)

    y = rule_y + 70
    for line in body_lines:
        if line:
            bbox = body_font.getbbox(line)
            x = (B.W - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, font=body_font, fill=INK)
        y += LINE_H

    return img.convert("RGB")


def generate_list_slide(img, slide):
    img, band_y, band_h = _slide_frame(img, slide)
    draw = ImageDraw.Draw(img)

    title_font = B.get_serif(54)
    item_font = B.get_sans(40)
    footer_font = B.get_sans(30)
    ITEM_H = 110

    title = B.normalize_text(slide.get("title", ""))
    items = [B.normalize_text(it) for it in slide.get("items", [])]
    footer = B.normalize_text(slide.get("footer", "")) if slide.get("footer") else ""

    title_h = B.measure_lines(title_font, title, line_gap=12)
    block_h = title_h + 28 + 1 + 50 + len(items) * ITEM_H + (50 if footer else 0)
    start_y = band_y + (band_h - block_h) // 2

    end_title_y = B.draw_multiline_centered(draw, title, title_font, start_y,
                                            B.W, INK, line_gap=12)
    rule_y = end_title_y + 18
    _hairline(draw, rule_y)

    y = rule_y + 50
    for i, it in enumerate(items):
        # number
        num = f"{i+1:02d}"
        num_font = B.get_serif(34)
        num_bbox = num_font.getbbox(num)
        num_w = num_bbox[2] - num_bbox[0]
        item_bbox = item_font.getbbox(it)
        item_w = item_bbox[2] - item_bbox[0]
        gap = 28
        total = num_w + gap + item_w
        x = (B.W - total) // 2
        draw.text((x, y + 8), num, font=num_font, fill=GOLD)
        draw.text((x + num_w + gap, y), it, font=item_font, fill=INK)
        y += ITEM_H

    if footer:
        _hairline(draw, y, x1=B.W // 2 - 60, x2=B.W // 2 + 60, width=2)
        B.draw_centered(draw, footer, footer_font, y + 22, B.W, GOLD)

    return img.convert("RGB")


def generate_cta_slide(img, slide):
    img, band_y, band_h = _slide_frame(img, slide)
    draw = ImageDraw.Draw(img)

    title_font = B.get_serif(50)
    body_font = B.get_sans(34)
    sub_font = B.get_sans(28)

    title = B.normalize_text(slide.get("title", ""))
    body = B.normalize_text(slide.get("body", ""))
    subtitle = B.normalize_text(slide.get("subtitle", ""))

    title_h = B.measure_lines(title_font, title, line_gap=12)
    body_lines = body.split("\n")
    body_h = len(body_lines) * 56
    sub_lines = subtitle.split("\n")
    sub_h = len(sub_lines) * 44
    block_h = title_h + 28 + 1 + 60 + body_h + 50 + 1 + 40 + sub_h
    start_y = band_y + (band_h - block_h) // 2

    end_title_y = B.draw_multiline_centered(draw, title, title_font, start_y,
                                            B.W, INK, line_gap=12)
    rule_y = end_title_y + 18
    _hairline(draw, rule_y)

    y = rule_y + 50
    for line in body_lines:
        if line:
            bbox = body_font.getbbox(line)
            x = (B.W - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, font=body_font, fill=INK)
        y += 56

    y += 30
    _hairline(draw, y, x1=B.W // 2 - 50, x2=B.W // 2 + 50, width=2)
    y += 30

    for line in sub_lines:
        if line:
            B.draw_centered(draw, line, sub_font, y, B.W, GOLD)
        y += 44

    return img.convert("RGB")


GENERATORS = {
    "cover": generate_cover,
    "text": generate_text_slide,
    "list": generate_list_slide,
    "cta": generate_cta_slide,
}
