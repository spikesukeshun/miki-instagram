"""Variant B — モノクロ・ミニマル

Concept:
- 写真をモノクロ化（軽くセピア寄せ）→ ギャラリー感
- 文字色は墨黒。アクセントは深いボルドー1色のみ
- カバー：左寄せタイトル＋ 大きな番号（"01"）を装飾に使う
- グリッドが「写真集」のように揃う方向
"""
from PIL import Image, ImageDraw

from . import _base as B

NAME = "variant_b_monochrome"
LABEL = "案B：モノクロ＋差し色（ミニマル）"

INK = (28, 25, 22, 255)
PAPER = (250, 248, 244, 255)
ACCENT = (122, 38, 50, 255)  # 深いボルドー


def _mono_bg(img):
    img = B.crop_center(img.convert("RGB"))
    img = B.to_grayscale_with_warmth(img, sepia=0.18)
    return img.convert("RGBA")


def generate_cover(img, slide):
    img = _mono_bg(img)

    # 左下に縦書き風の太い余白＝白帯を敷く
    band_h = int(B.H * 0.42)
    band_y = B.H - band_h
    img = B.paste_band(img, band_y, band_h, (250, 248, 244, 240))
    draw = ImageDraw.Draw(img)

    title_font = B.get_serif(98)
    kicker_font = B.get_sans(26)
    tag_font = B.get_sans(28)
    number_font = B.get_serif(220)

    title = B.normalize_text(slide.get("title", ""))
    kicker = B.normalize_text(slide.get("kicker", "")).upper()
    tag = B.normalize_text(slide.get("tag", ""))

    # 巨大な番号（写真エリア内・左上の装飾）— 写真の上に直接置く
    pad = 80
    if kicker:
        # 写真エリアの右上に薄く配置（半透明白でうっすら）
        num = "N°01"
        num_font_small = B.get_serif(40)
        draw.text((B.W - pad - 110, 80), num, font=num_font_small, fill=ACCENT)
        # その下に細線
        draw.line([(B.W - pad - 110, 130), (B.W - pad - 50, 130)],
                  fill=ACCENT, width=2)

    # KICKER (top of band)
    y = band_y + 50
    if kicker:
        draw.text((pad, y), kicker, font=kicker_font, fill=ACCENT)
        # 細いボルドー線
        draw.line([(pad, y + 38), (pad + 60, y + 38)], fill=ACCENT, width=2)
        y += 70

    # TITLE 左寄せ
    for line in title.split("\n"):
        if line:
            draw.text((pad, y), line, font=title_font, fill=INK)
        bbox = title_font.getbbox(line or "あ")
        y += (bbox[3] - bbox[1]) + 12

    # TAG 右下
    if tag:
        bbox = tag_font.getbbox(tag)
        tw = bbox[2] - bbox[0]
        draw.text((B.W - pad - tw, B.H - 70), tag, font=tag_font, fill=INK)

    return img.convert("RGB")


def _slide_paper(img):
    """全面ペーパー地（写真は使わない、ミニマル）。"""
    base = Image.new("RGBA", (B.W, B.H), PAPER)
    return base


def generate_text_slide(img, slide):
    img = _slide_paper(img)
    draw = ImageDraw.Draw(img)

    title_font = B.get_serif(54)
    body_font = B.get_sans(34)
    LINE_H = 56

    title = B.normalize_text(slide.get("title", ""))
    body = B.normalize_text(slide.get("text", ""))

    title_h = B.measure_lines(title_font, title, line_gap=12)
    body_lines = body.split("\n")
    body_h = len(body_lines) * LINE_H
    block_h = title_h + 40 + 100 + body_h
    start_y = (B.H - block_h) // 2

    # タイトル左寄せ
    pad = 90
    y = start_y
    for line in title.split("\n"):
        if line:
            draw.text((pad, y), line, font=title_font, fill=INK)
        bbox = title_font.getbbox(line or "あ")
        y += (bbox[3] - bbox[1]) + 12

    # ボルドー短線
    draw.line([(pad, y + 8), (pad + 60, y + 8)], fill=ACCENT, width=3)
    y += 80

    # 本文左寄せ
    for line in body_lines:
        if line:
            draw.text((pad, y), line, font=body_font, fill=INK)
        y += LINE_H

    return img.convert("RGB")


def generate_list_slide(img, slide):
    img = _slide_paper(img)
    draw = ImageDraw.Draw(img)

    title_font = B.get_serif(50)
    item_font = B.get_sans(38)
    num_font = B.get_serif(44)
    footer_font = B.get_sans(28)
    ITEM_H = 130

    title = B.normalize_text(slide.get("title", ""))
    items = [B.normalize_text(it) for it in slide.get("items", [])]
    footer = B.normalize_text(slide.get("footer", "")) if slide.get("footer") else ""

    title_h = B.measure_lines(title_font, title, line_gap=12)
    block_h = title_h + 40 + 50 + len(items) * ITEM_H + (60 if footer else 0)
    start_y = (B.H - block_h) // 2

    pad = 90
    y = start_y
    for line in title.split("\n"):
        if line:
            draw.text((pad, y), line, font=title_font, fill=INK)
        bbox = title_font.getbbox(line or "あ")
        y += (bbox[3] - bbox[1]) + 12

    draw.line([(pad, y + 12), (pad + 60, y + 12)], fill=ACCENT, width=3)
    y += 60

    for i, it in enumerate(items):
        num = f"{i+1:02d}"
        draw.text((pad, y - 6), num, font=num_font, fill=ACCENT)
        # 縦線
        draw.line([(pad + 90, y + 4), (pad + 90, y + 50)], fill=INK, width=1)
        draw.text((pad + 110, y), it, font=item_font, fill=INK)
        y += ITEM_H

    if footer:
        y += 10
        draw.text((pad, y), footer, font=footer_font, fill=ACCENT)

    return img.convert("RGB")


def generate_cta_slide(img, slide):
    img = _slide_paper(img)
    draw = ImageDraw.Draw(img)

    title_font = B.get_serif(46)
    body_font = B.get_sans(32)
    sub_font = B.get_sans(26)

    title = B.normalize_text(slide.get("title", ""))
    body = B.normalize_text(slide.get("body", ""))
    subtitle = B.normalize_text(slide.get("subtitle", ""))

    title_h = B.measure_lines(title_font, title, line_gap=12)
    body_lines = body.split("\n")
    body_h = len(body_lines) * 50
    sub_lines = subtitle.split("\n")
    sub_h = len(sub_lines) * 38
    block_h = title_h + 40 + 60 + body_h + 60 + 40 + sub_h
    start_y = (B.H - block_h) // 2

    pad = 90
    y = start_y
    for line in title.split("\n"):
        if line:
            draw.text((pad, y), line, font=title_font, fill=INK)
        bbox = title_font.getbbox(line or "あ")
        y += (bbox[3] - bbox[1]) + 12

    draw.line([(pad, y + 12), (pad + 60, y + 12)], fill=ACCENT, width=3)
    y += 60

    for line in body_lines:
        if line:
            draw.text((pad, y), line, font=body_font, fill=INK)
        y += 50

    y += 30
    # 短線
    draw.line([(pad, y), (pad + 40, y)], fill=ACCENT, width=2)
    y += 30
    for line in sub_lines:
        if line:
            draw.text((pad, y), line, font=sub_font, fill=ACCENT)
        y += 38

    return img.convert("RGB")


GENERATORS = {
    "cover": generate_cover,
    "text": generate_text_slide,
    "list": generate_list_slide,
    "cta": generate_cta_slide,
}
