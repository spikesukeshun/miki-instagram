"""Variant C — くすみベージュ・親密

Concept:
- 配色：ベージュ(#E8DDD0) × 焦茶(#3E2F25) × ローズグレー差し色
- 葉書風カバー：写真は上1/3だけ覗き、下に大きな余白
- 手書き風サインフォントでMIKIの一言を添える（親密感）
- グリッド：全カバーが同じベージュ地で並ぶと「シリーズもの」に見える
"""
from PIL import Image, ImageDraw

from . import _base as B

NAME = "variant_c_beige"
LABEL = "案C：くすみベージュ×手書き（親密）"

BEIGE = (232, 221, 208, 255)
BEIGE_DEEP = (215, 200, 184, 255)
DARK = (62, 47, 37, 255)
ROSE = (170, 122, 122, 255)


def _safe_script(size: int, text: str = "MIKI"):
    """Use a script font when the target text is ASCII-only, otherwise fall
    back to serif so Japanese characters render correctly."""
    return B.get_script_or_serif(size, text)


def _stamp_bg(img, photo_ratio=0.34):
    """葉書風：上に写真の一部、下にベージュ大余白。"""
    img = B.crop_center(img.convert("RGB"))
    photo_h = int(B.H * photo_ratio)
    out = Image.new("RGBA", (B.W, B.H), BEIGE)
    out.paste(img.crop((0, 0, B.W, photo_h)), (0, 0))
    return out


def generate_cover(img, slide):
    img = _stamp_bg(img, photo_ratio=0.36)
    draw = ImageDraw.Draw(img)

    # 写真とベージュの境にローズの細線
    draw.line([(0, int(B.H * 0.36)), (B.W, int(B.H * 0.36))],
              fill=ROSE, width=2)

    title_font = B.get_serif(96)
    tag_font = B.get_serif(34)
    title = B.normalize_text(slide.get("title", ""))
    tag = B.normalize_text(slide.get("tag", ""))
    tag_band_font = _safe_script(46, tag)  # 日本語なら明朝、英語なら手書き

    # サブタイトル（手書き風 — 日本語の場合は明朝にフォールバック）
    if tag:
        B.draw_centered(draw, tag, tag_band_font, int(B.H * 0.36) + 70, B.W, ROSE)

    # タイトル（中央、明朝大）
    title_h = B.measure_lines(title_font, title, line_gap=18)
    y = int(B.H * 0.55) - title_h // 2
    B.draw_multiline_centered(draw, title, title_font, y, B.W, DARK, line_gap=18)

    # 装飾の細線（タイトル下）
    bottom_y = B.H - 130
    draw.line([(B.W // 2 - 30, bottom_y), (B.W // 2 + 30, bottom_y)],
              fill=DARK, width=1)

    # MIKIの署名風（最下部）
    sign_font = _safe_script(36)
    B.draw_centered(draw, "MIKI", sign_font, B.H - 90, B.W, DARK)

    return img.convert("RGB")


def _slide_paper(img):
    return Image.new("RGBA", (B.W, B.H), BEIGE)


def generate_text_slide(img, slide):
    img = _slide_paper(img)
    draw = ImageDraw.Draw(img)

    title_font = B.get_serif(50)
    body_font = B.get_sans(34)
    LINE_H = 58

    title = B.normalize_text(slide.get("title", ""))
    body = B.normalize_text(slide.get("text", ""))

    title_h = B.measure_lines(title_font, title, line_gap=12)
    body_lines = body.split("\n")
    body_h = len(body_lines) * LINE_H
    block_h = title_h + 40 + 80 + body_h
    start_y = (B.H - block_h) // 2

    end_title_y = B.draw_multiline_centered(draw, title, title_font, start_y,
                                            B.W, DARK, line_gap=12)
    # 細い波形装飾の代わりにローズ短線（中央に短く）
    draw.line([(B.W // 2 - 40, end_title_y + 22), (B.W // 2 + 40, end_title_y + 22)],
              fill=ROSE, width=2)

    y = end_title_y + 80
    for line in body_lines:
        if line:
            bbox = body_font.getbbox(line)
            x = (B.W - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, font=body_font, fill=DARK)
        y += LINE_H

    return img.convert("RGB")


def generate_list_slide(img, slide):
    img = _slide_paper(img)
    draw = ImageDraw.Draw(img)

    title_font = B.get_serif(50)
    item_font = B.get_sans(38)
    bullet_font = B.get_serif(40)
    footer_font = B.get_sans(28)
    ITEM_H = 110

    title = B.normalize_text(slide.get("title", ""))
    items = [B.normalize_text(it) for it in slide.get("items", [])]
    footer = B.normalize_text(slide.get("footer", "")) if slide.get("footer") else ""

    title_h = B.measure_lines(title_font, title, line_gap=12)
    block_h = title_h + 40 + 60 + len(items) * ITEM_H + (60 if footer else 0)
    start_y = (B.H - block_h) // 2

    end_title_y = B.draw_multiline_centered(draw, title, title_font, start_y,
                                            B.W, DARK, line_gap=12)
    draw.line([(B.W // 2 - 40, end_title_y + 22), (B.W // 2 + 40, end_title_y + 22)],
              fill=ROSE, width=2)

    y = end_title_y + 70
    for it in items:
        # 中央揃え＋小さな・記号（焦茶）
        bullet = "・"
        item_bbox = item_font.getbbox(it)
        item_w = item_bbox[2] - item_bbox[0]
        bullet_bbox = bullet_font.getbbox(bullet)
        bullet_w = bullet_bbox[2] - bullet_bbox[0]
        gap = 10
        total = bullet_w + gap + item_w
        x = (B.W - total) // 2
        draw.text((x, y - 4), bullet, font=bullet_font, fill=ROSE)
        draw.text((x + bullet_w + gap, y), it, font=item_font, fill=DARK)
        y += ITEM_H

    if footer:
        B.draw_centered(draw, footer, footer_font, y, B.W, DARK)

    return img.convert("RGB")


def generate_cta_slide(img, slide):
    img = _slide_paper(img)
    draw = ImageDraw.Draw(img)

    title_font = B.get_serif(46)
    body_font = B.get_sans(32)
    sub_font = B.get_sans(28)
    script_font = _safe_script(50)

    title = B.normalize_text(slide.get("title", ""))
    body = B.normalize_text(slide.get("body", ""))
    subtitle = B.normalize_text(slide.get("subtitle", ""))

    title_h = B.measure_lines(title_font, title, line_gap=12)
    body_lines = body.split("\n")
    body_h = len(body_lines) * 52
    sub_lines = subtitle.split("\n")
    sub_h = len(sub_lines) * 42
    block_h = title_h + 40 + 60 + body_h + 50 + sub_h + 60
    start_y = (B.H - block_h) // 2

    end_title_y = B.draw_multiline_centered(draw, title, title_font, start_y,
                                            B.W, DARK, line_gap=12)
    draw.line([(B.W // 2 - 40, end_title_y + 22), (B.W // 2 + 40, end_title_y + 22)],
              fill=ROSE, width=2)

    y = end_title_y + 70
    for line in body_lines:
        if line:
            bbox = body_font.getbbox(line)
            x = (B.W - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, font=body_font, fill=DARK)
        y += 52

    y += 30
    for line in sub_lines:
        if line:
            B.draw_centered(draw, line, sub_font, y, B.W, ROSE)
        y += 42

    # 末尾に手書きMIKI署名
    B.draw_centered(draw, "— MIKI", script_font, y + 30, B.W, DARK)

    return img.convert("RGB")


GENERATORS = {
    "cover": generate_cover,
    "text": generate_text_slide,
    "list": generate_list_slide,
    "cta": generate_cta_slide,
}
