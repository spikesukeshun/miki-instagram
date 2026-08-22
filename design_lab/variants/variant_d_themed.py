"""Variant D — テーマ別カラーパレット

Concept:
- スライドの slide["kicker"] / 親 content の menu でパレットを切り替える
- ライフ系  : クリーム × 墨
- メニュー系: 白 × 金箔
- ブライダル系: オフホワイト × シャンパンゴールド
- 構造（上下のベージュ帯）は揃え、色レイヤーで「これは何の話か」が一目で分かる
- グリッド：3パターンが規則的に混ざる → 「ちゃんと運用されているアカウント」感
"""
from PIL import Image, ImageDraw

from . import _base as B

NAME = "variant_d_themed"
LABEL = "案D：テーマ別カラーパレット"


PALETTES = {
    "lifestyle": {
        "paper": (250, 244, 234, 255),
        "ink":   (44, 36, 30, 255),
        "accent":(166, 122, 70, 255),
        "label": "LIFE",
    },
    "menu": {
        "paper": (252, 250, 246, 255),
        "ink":   (35, 30, 28, 255),
        "accent":(184, 148, 80, 255),
        "label": "MENU",
    },
    "bridal": {
        "paper": (252, 248, 244, 255),
        "ink":   (50, 42, 36, 255),
        "accent":(206, 178, 130, 255),  # シャンパンゴールド
        "label": "BRIDAL",
    },
}

DEFAULT_KEY = "lifestyle"


def _palette(slide):
    key = slide.get("kicker") or slide.get("_palette") or DEFAULT_KEY
    return PALETTES.get(key, PALETTES[DEFAULT_KEY])


def _frame(img, palette):
    """上下に細いカラーバンドを敷いた共通フレーム。"""
    img = B.crop_center(img.convert("RGB")).convert("RGBA")
    paper = palette["paper"]
    # 上に小さめ・下に大きめの帯
    img = B.paste_band(img, 0, 90, paper)
    img = B.paste_band(img, B.H - 90, 90, paper)
    return img


def generate_cover(img, slide):
    palette = _palette(slide)
    img = B.crop_center(img.convert("RGB")).convert("RGBA")

    # 上下のカラーバンド
    band_h_top = 160
    band_h_bot = int(B.H * 0.5)
    img = B.paste_band(img, 0, band_h_top, palette["paper"])
    img = B.paste_band(img, B.H - band_h_bot, band_h_bot, palette["paper"])

    draw = ImageDraw.Draw(img)
    label_font = B.get_sans(28)
    title_font = B.get_serif(106)
    tag_font = B.get_serif(34)

    # 上：パレットラベル
    label = palette["label"]
    B.draw_centered(draw, label, label_font, 60, B.W, palette["accent"])
    # 下に細線
    draw.line([(B.W // 2 - 30, 102), (B.W // 2 + 30, 102)],
              fill=palette["accent"], width=2)

    # 下バンド：タイトル中央
    title = B.normalize_text(slide.get("title", ""))
    tag = B.normalize_text(slide.get("tag", ""))

    band_top = B.H - band_h_bot
    title_h = B.measure_lines(title_font, title, line_gap=18)
    title_y = band_top + (band_h_bot - title_h - 80) // 2
    B.draw_multiline_centered(draw, title, title_font, title_y, B.W,
                              palette["ink"], line_gap=18)

    if tag:
        B.draw_centered(draw, tag, tag_font, B.H - 90, B.W, palette["accent"])

    return img.convert("RGB")


def _content_palette(slide):
    """text/list/cta は親 content から渡された palette を優先。
    sample_content.json の menu フィールドで判定。"""
    return _palette(slide)


def _common_layout(img, slide, palette, title, body=None, items=None,
                   footer=None, body_font_size=34, line_h=58):
    img = _frame(img, palette)
    # paper を全面薄く
    img = B.paste_band(img, 0, B.H, (palette["paper"][0], palette["paper"][1],
                                     palette["paper"][2], 230))
    return img


def generate_text_slide(img, slide):
    palette = _content_palette(slide)
    img = B.crop_center(img.convert("RGB")).convert("RGBA")
    # 全面 paper 半透明（写真は奥に）
    img = B.paste_band(img, 0, B.H, (palette["paper"][0], palette["paper"][1],
                                     palette["paper"][2], 235))
    # 上下にラインバンド
    img = B.paste_band(img, 0, 70, palette["paper"])
    img = B.paste_band(img, B.H - 70, 70, palette["paper"])
    draw = ImageDraw.Draw(img)

    title_font = B.get_serif(54)
    body_font = B.get_sans(34)
    label_font = B.get_sans(22)
    LINE_H = 58

    title = B.normalize_text(slide.get("title", ""))
    body = B.normalize_text(slide.get("text", ""))

    # 上：ラベル
    B.draw_centered(draw, palette["label"], label_font, 25, B.W, palette["accent"])

    title_h = B.measure_lines(title_font, title, line_gap=12)
    body_lines = body.split("\n")
    body_h = len(body_lines) * LINE_H
    block_h = title_h + 30 + 80 + body_h
    start_y = (B.H - block_h) // 2

    end_title_y = B.draw_multiline_centered(draw, title, title_font, start_y,
                                            B.W, palette["ink"], line_gap=12)
    draw.line([(B.W // 2 - 40, end_title_y + 20), (B.W // 2 + 40, end_title_y + 20)],
              fill=palette["accent"], width=2)

    y = end_title_y + 80
    for line in body_lines:
        if line:
            bbox = body_font.getbbox(line)
            x = (B.W - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, font=body_font, fill=palette["ink"])
        y += LINE_H

    return img.convert("RGB")


def generate_list_slide(img, slide):
    palette = _content_palette(slide)
    img = B.crop_center(img.convert("RGB")).convert("RGBA")
    img = B.paste_band(img, 0, B.H, (palette["paper"][0], palette["paper"][1],
                                     palette["paper"][2], 235))
    img = B.paste_band(img, 0, 70, palette["paper"])
    img = B.paste_band(img, B.H - 70, 70, palette["paper"])
    draw = ImageDraw.Draw(img)

    title_font = B.get_serif(50)
    item_font = B.get_sans(40)
    label_font = B.get_sans(22)
    footer_font = B.get_sans(28)
    ITEM_H = 110

    title = B.normalize_text(slide.get("title", ""))
    items = [B.normalize_text(it) for it in slide.get("items", [])]
    footer = B.normalize_text(slide.get("footer", "")) if slide.get("footer") else ""

    B.draw_centered(draw, palette["label"], label_font, 25, B.W, palette["accent"])

    title_h = B.measure_lines(title_font, title, line_gap=12)
    block_h = title_h + 40 + 60 + len(items) * ITEM_H + (60 if footer else 0)
    start_y = (B.H - block_h) // 2

    end_title_y = B.draw_multiline_centered(draw, title, title_font, start_y,
                                            B.W, palette["ink"], line_gap=12)
    draw.line([(B.W // 2 - 40, end_title_y + 20), (B.W // 2 + 40, end_title_y + 20)],
              fill=palette["accent"], width=2)

    y = end_title_y + 60
    for i, it in enumerate(items):
        marker = "◆"
        marker_font = B.get_sans(22)
        marker_bbox = marker_font.getbbox(marker)
        marker_w = marker_bbox[2] - marker_bbox[0]
        item_bbox = item_font.getbbox(it)
        item_w = item_bbox[2] - item_bbox[0]
        gap = 22
        total = marker_w + gap + item_w
        x = (B.W - total) // 2
        draw.text((x, y + 16), marker, font=marker_font, fill=palette["accent"])
        draw.text((x + marker_w + gap, y), it, font=item_font, fill=palette["ink"])
        y += ITEM_H

    if footer:
        B.draw_centered(draw, footer, footer_font, y, B.W, palette["accent"])

    return img.convert("RGB")


def generate_cta_slide(img, slide):
    palette = _content_palette(slide)
    img = B.crop_center(img.convert("RGB")).convert("RGBA")
    img = B.paste_band(img, 0, B.H, (palette["paper"][0], palette["paper"][1],
                                     palette["paper"][2], 235))
    img = B.paste_band(img, 0, 70, palette["paper"])
    img = B.paste_band(img, B.H - 70, 70, palette["paper"])
    draw = ImageDraw.Draw(img)

    title_font = B.get_serif(46)
    body_font = B.get_sans(32)
    sub_font = B.get_sans(28)
    label_font = B.get_sans(22)

    title = B.normalize_text(slide.get("title", ""))
    body = B.normalize_text(slide.get("body", ""))
    subtitle = B.normalize_text(slide.get("subtitle", ""))

    B.draw_centered(draw, palette["label"], label_font, 25, B.W, palette["accent"])

    title_h = B.measure_lines(title_font, title, line_gap=12)
    body_lines = body.split("\n")
    body_h = len(body_lines) * 52
    sub_lines = subtitle.split("\n")
    sub_h = len(sub_lines) * 42
    block_h = title_h + 40 + 60 + body_h + 60 + sub_h
    start_y = (B.H - block_h) // 2

    end_title_y = B.draw_multiline_centered(draw, title, title_font, start_y,
                                            B.W, palette["ink"], line_gap=12)
    draw.line([(B.W // 2 - 40, end_title_y + 20), (B.W // 2 + 40, end_title_y + 20)],
              fill=palette["accent"], width=2)

    y = end_title_y + 70
    for line in body_lines:
        if line:
            bbox = body_font.getbbox(line)
            x = (B.W - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, font=body_font, fill=palette["ink"])
        y += 52

    y += 30
    for line in sub_lines:
        if line:
            B.draw_centered(draw, line, sub_font, y, B.W, palette["accent"])
        y += 42

    return img.convert("RGB")


GENERATORS = {
    "cover": generate_cover,
    "text": generate_text_slide,
    "list": generate_list_slide,
    "cta": generate_cta_slide,
}
