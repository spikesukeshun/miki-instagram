"""Shared utilities for design_lab variants.

This is a self-contained copy of the helpers from generate_carousel.py — kept
deliberately separate so the sandbox cannot affect the production pipeline.
Variants import only from this module (and PIL).
"""
from __future__ import annotations  # Python 3.9 互換（PEP 604 union syntax）

import os
import unicodedata
from PIL import Image, ImageFont

W, H = 1080, 1350  # 4:5 vertical (Instagram carousel)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    return text.encode("utf-8", errors="ignore").decode("utf-8")


# ---- Fonts -----------------------------------------------------------------

# Variants may opt for a serif/mincho title and a sans body. We probe a few
# common locations so the same code works on macOS and the GitHub Actions
# Linux runner. Local custom fonts can be dropped into design_lab/fonts/.
_LAB_FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "fonts")

SANS_PATHS = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]

SERIF_PATHS = [
    os.path.join(_LAB_FONT_DIR, "NotoSerifJP-Bold.otf"),
    os.path.join(_LAB_FONT_DIR, "NotoSerifJP-Regular.otf"),
    os.path.join(_LAB_FONT_DIR, "ShipporiMincho-Bold.otf"),
    "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc",
    "/Library/Fonts/Hiragino Mincho ProN.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
]

SCRIPT_PATHS = [
    os.path.join(_LAB_FONT_DIR, "DancingScript-Regular.ttf"),
    "/System/Library/Fonts/Supplemental/Apple Chancery.ttf",
    "/Library/Fonts/Apple Chancery.ttf",
]


def _try_load(paths, size):
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return None


def get_sans(size: int):
    f = _try_load(SANS_PATHS, size)
    return f or ImageFont.load_default()


def get_serif(size: int):
    """Return a serif/mincho font; falls back to sans if no serif is available."""
    f = _try_load(SERIF_PATHS, size)
    return f or get_sans(size)


def get_script(size: int):
    """Return a script/handwriting font; falls back to serif if unavailable."""
    f = _try_load(SCRIPT_PATHS, size)
    return f or get_serif(size)


def has_cjk(text: str) -> bool:
    """True if text contains any CJK character (script fonts can't render these)."""
    for ch in text:
        cp = ord(ch)
        if (0x3040 <= cp <= 0x30FF or  # hiragana / katakana
            0x4E00 <= cp <= 0x9FFF or  # CJK unified
            0xFF00 <= cp <= 0xFFEF):   # halfwidth/fullwidth forms
            return True
    return False


def get_script_or_serif(size: int, text: str):
    """Pick a script font for ASCII-only text, otherwise fall back to serif so
    Japanese strings stay readable instead of rendering as tofu boxes."""
    return get_serif(size) if has_cjk(text) else get_script(size)


# ---- Image helpers ---------------------------------------------------------

def crop_center(img: Image.Image, size=(W, H)) -> Image.Image:
    target_w, target_h = size
    orig_w, orig_h = img.size
    scale = max(target_w / orig_w, target_h / orig_h)
    new_w = int(orig_w * scale)
    new_h = int(orig_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def crop_center_with_focus(img: Image.Image, focus_y: float = 0.5,
                           size=(W, H)) -> Image.Image:
    """4:5にクロップする際、focus_y(0.0=写真の上端を残す〜1.0=下端を残す)で
    被写体の縦位置を可変にする。0.5 で従来の crop_center() と同じ中央クロップ。"""
    target_w, target_h = size
    orig_w, orig_h = img.size
    scale = max(target_w / orig_w, target_h / orig_h)
    new_w = int(orig_w * scale)
    new_h = int(orig_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    max_top = max(0, new_h - target_h)
    fy = max(0.0, min(1.0, focus_y))
    top = int(max_top * fy)
    return img.crop((left, top, left + target_w, top + target_h))


def paste_gradient_band(img: Image.Image, y_top: int, height: int,
                        color_rgb, fade_top_px: int | None = None,
                        alpha: int = 245) -> Image.Image:
    """y_top から height px の縦範囲を color_rgb で塗る。上端 fade_top_px 分は
    アルファ 0→alpha のグラデーション、それ以下は solid alpha。
    fade_top_px=None なら height の 1/3 を自動でフェード領域にする。
    タイトル可読性を保ちつつ、その上の写真を「徐々に消す」見せ方にできる。"""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    if fade_top_px is None:
        fade_top_px = height // 3
    fade_top_px = max(0, min(fade_top_px, height))
    w = img.size[0]
    alpha_col = Image.new("L", (1, height), alpha)
    for row in range(fade_top_px):
        t = row / max(1, fade_top_px - 1)
        alpha_col.putpixel((0, row), int(alpha * t))
    alpha_band = alpha_col.resize((w, height), Image.NEAREST)
    rgb_band = Image.new("RGB", (w, height), color_rgb)
    r_ch, g_ch, b_ch = rgb_band.split()
    band = Image.merge("RGBA", (r_ch, g_ch, b_ch, alpha_band))
    img.alpha_composite(band, (0, y_top))
    return img


def to_grayscale_with_warmth(img: Image.Image, sepia: float = 0.0) -> Image.Image:
    """Desaturate to monochrome, optionally warming with a sepia tint (0-1)."""
    gray = img.convert("L").convert("RGB")
    if sepia <= 0:
        return gray
    warm = Image.new("RGB", gray.size, (210, 185, 155))
    return Image.blend(gray, warm, min(max(sepia, 0.0), 1.0))


def measure_lines(font, text: str, line_gap: int = 10) -> int:
    """Total pixel height of a multi-line block."""
    lines = text.split("\n")
    total = 0
    for line in lines:
        ref = line if line else "あ"
        bbox = font.getbbox(ref)
        total += (bbox[3] - bbox[1]) + line_gap
    return total - line_gap if total else 0


def draw_centered(draw, text, font, y, img_width, fill, shadow=None):
    bbox = font.getbbox(text)
    w = bbox[2] - bbox[0]
    x = (img_width - w) // 2
    if shadow:
        sx, sy, sfill = shadow
        draw.text((x + sx, y + sy), text, font=font, fill=sfill)
    draw.text((x, y), text, font=font, fill=fill)
    return bbox[3] - bbox[1]


def draw_multiline_centered(draw, text, font, y_start, img_width, fill,
                            line_gap: int = 10, shadow=None):
    y = y_start
    for line in text.split("\n"):
        if line:
            h = draw_centered(draw, line, font, y, img_width, fill, shadow=shadow)
        else:
            bbox = font.getbbox("あ")
            h = bbox[3] - bbox[1]
        y += h + line_gap
    return y


def paste_band(img: Image.Image, y: int, height: int, color) -> Image.Image:
    """Paste a horizontal band of given color/alpha onto an RGBA image."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    band = Image.new("RGBA", (img.size[0], height), color)
    img.alpha_composite(band, (0, y))
    return img


# ---- Background loading ----------------------------------------------------

SAMPLE_BG_DIR = os.path.join(os.path.dirname(__file__), "..", "sample_bg")


def load_sample_bg(filename: str) -> Image.Image:
    """Load a sample background. If the file is missing we synthesise a soft
    placeholder so variants can still render before MIKI provides assets."""
    path = os.path.join(SAMPLE_BG_DIR, filename)
    if os.path.exists(path):
        return Image.open(path).convert("RGBA")
    return _placeholder_bg(filename)


def _placeholder_bg(filename: str) -> Image.Image:
    """Generate a neutral cream/grey gradient placeholder so layouts are
    visible even when sample_bg/ is empty. The hash of the filename varies the
    tone so different slides look distinct."""
    h = abs(hash(filename)) % 5
    palettes = [
        ((245, 238, 228), (228, 215, 198)),  # cream
        ((232, 221, 208), (210, 195, 178)),  # beige
        ((238, 234, 228), (215, 208, 198)),  # ivory
        ((230, 225, 218), (205, 198, 188)),  # greige
        ((242, 236, 226), (220, 208, 192)),  # warm sand
    ]
    top, bot = palettes[h]
    img = Image.new("RGB", (W, H), bot)
    for y in range(H):
        t = y / H
        r = int(top[0] * (1 - t) + bot[0] * t)
        g = int(top[1] * (1 - t) + bot[1] * t)
        b = int(top[2] * (1 - t) + bot[2] * t)
        for x in range(0, W, 4):  # stripe sample for speed
            img.putpixel((x, y), (r, g, b))
    return img.resize((W, H)).convert("RGBA")
