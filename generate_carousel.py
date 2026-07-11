"""カルーセル画像生成（案A：雑誌風・明朝・余白主義）

設計指針：
- 写真ゾーン（上）+ クリーム帯（下）の2分割レイアウト
- タイトルは明朝（serif）、本文・補足は sans-serif
- パレット: CREAM(250,246,241) × INK(43,37,34) × GOLD(184,148,90)
- 旧来の PINK/DARK/ゴールド二重枠は廃止

content.json の任意フィールド：
- focus_y          : 0.0〜1.0（写真クロップの縦位置。0=上端優先, 0.5=中央, 1=下端優先）
- photo_h_ratio    : cover の写真ゾーン高さ比率（default 0.55）
- slide_photo_h_ratio : text/list/cta の写真ゾーン高さ比率（default 0.35、0で写真なし）
- kicker           : cover 上部の小見出し（任意・大文字推奨）

呼び出し元：
- create_post.py:8           from generate_carousel import generate_with_slides
"""
import unicodedata
from PIL import Image, ImageDraw, ImageFont
import os


def normalize_text(text: str) -> str:
    """Unicode NFC正規化＋フォントで描画できない可能性のある文字を除去"""
    text = unicodedata.normalize("NFC", text)
    return text.encode("utf-8", errors="ignore").decode("utf-8")


OUTPUT_DIR = "generated"
BACKGROUNDS_DIR = "backgrounds"
ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
os.makedirs(OUTPUT_DIR, exist_ok=True)

W, H = 1080, 1350  # 4:5 縦長サイズ

# ---------------------------------------------------------------------------
# 案A パレット
# ---------------------------------------------------------------------------
CREAM = (250, 246, 241, 255)
INK = (43, 37, 34, 255)
GOLD = (184, 148, 90, 255)


# CLI 動作確認用のサンプル（実運用では create_post.py 経由で content.json から渡される）
SLIDES = [
    {
        "filename": "slide1.jpg",
        "type": "cover",
        "title": "ブライダルエステを\n始めたきっかけ",
        "tag": "- 読んでみてください -",
    },
    {
        "filename": "slide2.jpg",
        "type": "text",
        "title": "私の原点",
        "text": "美容学校でトータルビューティを\n学んだことが私のすべての原点です。\n\nヘア・メイク・ネイル、そしてエステ。\n女性の美しさを多角的に捉える視点を\n養う中で、\n\n土台となる肌や体、メンタルを整えることが\n全ての美しさの根幹である。\n\nという確信を持ちました。",
    },
    {
        "filename": "slide3.jpg",
        "type": "list",
        "title": "こんなお悩みありませんか？",
        "items": [
            "「エステが初めてで何もわからない」",
            "「いつから始めればいいかわからない」",
            "「検索してもたくさんありすぎる」",
            "「料金が不明確で勧誘が不安」",
        ],
        "footer": "そのお悩み、全部ご相談くださいませ。"
    },
    {
        "filename": "slide4.jpg",
        "type": "text",
        "title": "私自身の経験から",
        "text": "私自身も深く迷いました。\n\nブライダルエステは単に\n外見を整えるだけの場所ではなく、\n\nプロとして確かな技術を提供するのはもちろん、\n花嫁様が抱える小さな不安や迷いに寄り添い、\n\n一番の理解者として、\n支える存在でありたいと思いました。",
    },
    {
        "filename": "slide5.jpg",
        "type": "text",
        "title": "MIKIの想い",
        "text": "これまで多くの花嫁様を\n施術させていただく中で、\n\nお体や肌が変わっていくと\n自信に満ちた笑顔になっていく姿を\n拝見してきました。\n\nその瞬間に立ち会えることが\n今の私の最大の喜びです。",
    },
    {
        "filename": "slide6.jpg",
        "type": "cta",
        "title": "MIKI指名  初回限定20%OFF\n（VIPコースのみ）",
        "body": "美容と健康に興味がある。\n素直に自分と向き合える。\nそんな花嫁様、ぜひ会いに来てください",
        "subtitle": "ご予約・ご相談はDMからお気軽にどうぞ",
    },
    {
        "filename": "slide8.jpg",
        "type": "raw",
    },
    {
        "filename": "slide7.jpg",
        "type": "raw",
    },
]


def load_background(filename: str) -> Image.Image:
    """backgrounds/フォルダから背景画像を読み込む"""
    path = os.path.join(BACKGROUNDS_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"背景画像が見つかりません: {path}\n"
            f"backgrounds/フォルダに {filename} を置いてください")
    return Image.open(path).convert("RGBA")


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------
def crop_center(img: Image.Image, size=(W, H)) -> Image.Image:
    """アスペクト比を保ちながら中央クロップ（歪みなし）"""
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
    """4:5 にクロップする際、focus_y(0.0=写真の上端を残す〜1.0=下端を残す)で
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


def paste_band(img: Image.Image, y: int, height: int, color) -> Image.Image:
    """指定位置に色帯を alpha_composite する。color は (r,g,b,a) RGBA。"""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    band = Image.new("RGBA", (img.size[0], height), color)
    img.alpha_composite(band, (0, y))
    return img


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------
_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

SANS_PATHS = [
    # macOS
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode MS.ttf",
    # Linux (Ubuntu / GitHub Actions: fonts-noto-cjk)
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
]

SERIF_PATHS = [
    # プロジェクト同梱（あれば優先）
    os.path.join(_FONT_DIR, "NotoSerifJP-Bold.otf"),
    os.path.join(_FONT_DIR, "NotoSerifJP-Regular.otf"),
    os.path.join(_FONT_DIR, "ShipporiMincho-Bold.otf"),
    # macOS
    "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc",
    "/Library/Fonts/Hiragino Mincho ProN.ttc",
    # Linux
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJKjp-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSerifCJK-Regular.ttc",
]


def _try_load(paths, size):
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return None


def get_font(size: int):
    """サンセリフ（ヒラギノ角ゴ／Noto Sans CJK）を返す。後方互換のため残す。"""
    f = _try_load(SANS_PATHS, size)
    return f or ImageFont.load_default()


def get_sans(size: int):
    """get_font のエイリアス（変数名で意図を明示）"""
    return get_font(size)


def get_serif(size: int):
    """明朝（ヒラギノ明朝／Noto Serif CJK／プロジェクト同梱フォント）を返す。
    見つからなければサンセリフにフォールバック。"""
    f = _try_load(SERIF_PATHS, size)
    return f or get_sans(size)


def get_emoji_font(size: int):
    """絵文字フォントを取得（macOS: Apple Color Emoji / Linux: NotoColorEmoji）。

    Apple Color Emoji は bitmap フォントで固定サイズ（20/32/64/96/160）にしか
    対応していないため、要求サイズが非対応なら最も近い対応サイズに自動スナップする。
    NotoColorEmoji は基本的にどのサイズでもロード可能。"""
    emoji_font_paths = [
        "/System/Library/Fonts/Apple Color Emoji.ttc",
        "/System/Library/Fonts/AppleColorEmoji.ttf",
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        "/usr/share/fonts/noto/NotoColorEmoji.ttf",
    ]
    # Apple Color Emoji がサポートする bitmap サイズ
    SUPPORTED_BITMAP_SIZES = [20, 32, 64, 96, 160]

    for path in emoji_font_paths:
        if not os.path.exists(path):
            continue
        # まず要求サイズで試す
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
        # ダメなら最も近い bitmap サイズにスナップして再試行
        nearest = min(SUPPORTED_BITMAP_SIZES, key=lambda s: abs(s - size))
        try:
            return ImageFont.truetype(path, nearest)
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Text drawing helpers
# ---------------------------------------------------------------------------
def draw_centered(draw, text, font, y, img_width, fill, shadow=None):
    """1行テキストを中央揃えで描画。shadow=(dx,dy,fill) を渡すと影付き。"""
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
    """複数行テキストを中央揃えで描画し、最終行下端のy座標を返す。"""
    y = y_start
    for line in text.split("\n"):
        if line:
            h = draw_centered(draw, line, font, y, img_width, fill, shadow=shadow)
        else:
            bbox = font.getbbox("あ")
            h = bbox[3] - bbox[1]
        y += h + line_gap
    return y


def measure_lines(font, text: str, line_gap: int = 10) -> int:
    """複数行テキストブロックの合計高さ（pixel）"""
    lines = text.split("\n")
    total = 0
    for line in lines:
        ref = line if line else "あ"
        bbox = font.getbbox(ref)
        total += (bbox[3] - bbox[1]) + line_gap
    return total - line_gap if total else 0


def measure_widest_line(font, text: str) -> int:
    """複数行テキストの最大行幅（pixel）"""
    widest = 0
    for line in text.split("\n"):
        if not line:
            continue
        bbox = font.getbbox(line)
        widest = max(widest, bbox[2] - bbox[0])
    return widest


def paste_title_bubble(canvas, slide, title, title_font,
                       title_top_y, title_bottom_y, band_y,
                       size=200, gap=22):
    """中央揃えタイトルの右脇に丸型バブル画像（assets/<bubble>）を合成する。

    slide["bubble"] にファイル名（例 "miki_bubble_ring.png"）が指定された時のみ動作。
    透過PNG（金枠の円形カットアウト）を想定し、タイトルの縦中央に合わせて配置する。
    キャンバス右端・写真境界（band_y）からはみ出さないようクランプする。"""
    bubble_name = os.path.basename(slide.get("bubble") or "")
    if not bubble_name:
        return
    path = os.path.join(ASSETS_DIR, bubble_name)
    if not os.path.exists(path):
        print(f"  ⚠ バブル画像が見つかりません: {path}")
        return

    with Image.open(path) as im:
        bubble = im.convert("RGBA")
    # 非正方形でも歪まないよう、中央を正方形にクロップしてから縮小
    bw, bh = bubble.size
    if bw != bh:
        s = min(bw, bh)
        left, top = (bw - s) // 2, (bh - s) // 2
        bubble = bubble.crop((left, top, left + s, top + s))
    bubble = bubble.resize((size, size), Image.LANCZOS)

    title_w = measure_widest_line(title_font, title)
    title_right = (W + title_w) // 2  # 中央揃えタイトルの右端
    # 右マージンを最優先で画面内に収める（タイトルが長い場合は多少被ってもよい）
    x = min(title_right + gap, W - size - 24)
    x = max(x, 24)

    cy = (title_top_y + title_bottom_y) // 2
    y = cy - size // 2
    y = max(y, band_y + 8)             # 写真境界より下に収める
    y = min(y, H - size - 8)           # 下端からはみ出さない

    canvas.paste(bubble, (int(x), int(y)), bubble)


def draw_with_emoji_suffix(draw, text, suffix_emoji, font, emoji_font, y,
                           img_width, fill, shadow=None):
    """テキスト本文を中央揃えで描画し、末尾に絵文字を別フォントで追加する。

    案A の `generate_cta_slide` から subtitle 最終行の 💌 自動付与に使用。
    shadow=(dx, dy, sfill) を渡すと影付き、デフォルト None で案A の余白主義に合わせて
    シャドウなし。PIL の embedded_color にも対応（Apple Color Emoji / NotoColorEmoji）。"""
    main_bbox = font.getbbox(text)
    main_w = main_bbox[2] - main_bbox[0]
    main_h = main_bbox[3] - main_bbox[1]

    if emoji_font is not None:
        try:
            emo_bbox = emoji_font.getbbox(suffix_emoji)
            emo_w = emo_bbox[2] - emo_bbox[0]
        except Exception:
            emo_w = main_h
    else:
        emo_w = main_h

    total_w = main_w + 8 + emo_w
    start_x = (img_width - total_w) // 2

    if shadow:
        sx, sy, sfill = shadow
        draw.text((start_x + sx, y + sy), text, font=font, fill=sfill)
    draw.text((start_x, y), text, font=font, fill=fill)

    emoji_x = start_x + main_w + 8
    if emoji_font is not None:
        try:
            draw.text((emoji_x, y), suffix_emoji, font=emoji_font, fill=fill,
                      embedded_color=True)
        except TypeError:
            draw.text((emoji_x, y), suffix_emoji, font=emoji_font, fill=fill)
    else:
        draw.text((emoji_x, y), suffix_emoji, font=font, fill=fill)

    return main_h


# ---------------------------------------------------------------------------
# Slide generators (案A：雑誌風・明朝・余白主義)
# ---------------------------------------------------------------------------
def _hairline(draw, y, x1=120, x2=W - 120, fill=GOLD, width=1):
    """ゴールドのヘアライン罫（雑誌の細罫）"""
    draw.line([(x1, y), (x2, y)], fill=fill, width=width)


def generate_cover(img, slide):
    """カバー：写真エリア（上 photo_h_ratio）と クリーム帯（下）に明確に分割。
    focus_y で被写体の縦位置を調整できる（0.0=上端、0.5=中央、1.0=下端）。"""
    photo_h_ratio = float(slide.get("photo_h_ratio", 0.55))
    focus_y = float(slide.get("focus_y", 0.5))

    photo_h = int(H * photo_h_ratio)  # 例: 0.55 → 743
    photo = crop_center_with_focus(img, focus_y=focus_y,
                                   size=(W, photo_h)).convert("RGBA")

    canvas = Image.new("RGBA", (W, H), CREAM)
    canvas.paste(photo, (0, 0))
    draw = ImageDraw.Draw(canvas)

    band_y = photo_h
    # 写真と帯の境界に細いゴールドライン（雑誌の罫線）
    draw.line([(0, band_y), (W, band_y)], fill=GOLD, width=2)

    title_font = get_serif(110)
    kicker_font = get_sans(28)
    tag_font = get_serif(32)

    kicker = normalize_text(slide.get("kicker", "")).upper()
    title = normalize_text(slide.get("title", ""))
    tag = normalize_text(slide.get("tag", ""))

    inner_y = band_y + 36

    if kicker:
        draw_centered(draw, kicker, kicker_font, inner_y, W, GOLD)
        inner_y += 50
        _hairline(draw, inner_y + 6, x1=W // 2 - 30, x2=W // 2 + 30, width=2)
        inner_y += 28

    title_h = measure_lines(title_font, title, line_gap=14)
    bottom_reserve = 84 if tag else 40
    available_h = (H - bottom_reserve) - inner_y
    title_y = inner_y + max(0, (available_h - title_h) // 2)
    draw_multiline_centered(draw, title, title_font, title_y, W, INK,
                            line_gap=14)

    if tag:
        draw_centered(draw, tag, tag_font, H - 56, W, INK)

    return canvas.convert("RGB")


def _slide_frame(img, slide, default_ratio=0.35, content_h=0,
                 min_band_padding=80, drop_photo_below_ratio=0.10):
    """text/list/cta スライドの背景を組み立てる。

    上 slide_photo_h_ratio に写真エリア、下にクリーム帯。slide_photo_h_ratio=0
    で写真なし純クリーム。focus_y で被写体の縦位置を調整可能。

    content_h を渡すと、本文ブロックがクリーム帯に収まるよう photo zone を
    自動縮小する（本文が写真エリアに食い込むのを防止）。さらに必要 photo_h が
    drop_photo_below_ratio を下回る場合は写真を完全に省略して全面クリーム化する
    （極端に薄いスリット写真は見栄えが悪いため）。"""
    requested_ratio = float(slide.get("slide_photo_h_ratio", default_ratio))
    requested_ratio = max(0.0, min(0.6, requested_ratio))

    if content_h > 0:
        # 本文 + 上下マージン分は確保 → photo zone はそれ以外の領域に収める
        max_photo_h = max(0, H - (content_h + min_band_padding))
        max_ratio = max_photo_h / H
        ratio = min(requested_ratio, max_ratio)
        # 残りスペースが極端に小さければ写真を諦めて全面クリーム化
        if 0 < ratio < drop_photo_below_ratio:
            ratio = 0.0
    else:
        ratio = requested_ratio

    canvas = Image.new("RGBA", (W, H), CREAM)
    if ratio > 0 and img is not None:
        focus_y = float(slide.get("focus_y", 0.5))
        photo_h = int(H * ratio)
        photo = crop_center_with_focus(img, focus_y=focus_y,
                                       size=(W, photo_h)).convert("RGBA")
        canvas.paste(photo, (0, 0))
        draw = ImageDraw.Draw(canvas)
        draw.line([(0, photo_h), (W, photo_h)], fill=GOLD, width=2)
        band_y = photo_h
    else:
        band_y = 0
    band_h = H - band_y
    return canvas, band_y, band_h


def generate_text_slide(img, slide):
    title_font = get_serif(56)
    body_font = get_sans(34)
    LINE_H = 56

    title = normalize_text(slide.get("title", ""))
    body = normalize_text(slide.get("text", ""))

    title_h = measure_lines(title_font, title, line_gap=12)
    body_lines = body.split("\n")
    body_h = len(body_lines) * LINE_H
    block_h = title_h + 30 + 1 + 80 + body_h

    # content_h を渡して photo zone を必要なら自動縮小（本文オーバーフロー防止）
    img, band_y, band_h = _slide_frame(img, slide, content_h=block_h)
    draw = ImageDraw.Draw(img)

    # 万一 block_h > band_h でも上方向にはみ出さないようクランプ
    start_y = band_y + max(0, (band_h - block_h) // 2)

    end_title_y = draw_multiline_centered(draw, title, title_font, start_y,
                                          W, INK, line_gap=12)
    rule_y = end_title_y + 18
    _hairline(draw, rule_y)

    # 区切り線から本文まで 70px（旧 100px から狭めて全体バランス調整）
    y = rule_y + 70
    for line in body_lines:
        if line:
            bbox = body_font.getbbox(line)
            x = (W - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, font=body_font, fill=INK)
        y += LINE_H

    return img.convert("RGB")


def generate_list_slide(img, slide):
    title_font = get_serif(54)
    item_font = get_sans(40)
    footer_font = get_sans(30)
    ITEM_H = 110

    title = normalize_text(slide.get("title", ""))
    items = [normalize_text(it) for it in slide.get("items", [])]
    footer = normalize_text(slide.get("footer", "")) if slide.get("footer") else ""

    title_h = measure_lines(title_font, title, line_gap=12)
    block_h = title_h + 28 + 1 + 50 + len(items) * ITEM_H + (50 if footer else 0)

    # content_h を渡して photo zone を必要なら自動縮小（本文オーバーフロー防止）
    img, band_y, band_h = _slide_frame(img, slide, content_h=block_h)
    draw = ImageDraw.Draw(img)

    # 万一 block_h > band_h でも上方向にはみ出さないようクランプ
    start_y = band_y + max(0, (band_h - block_h) // 2)

    end_title_y = draw_multiline_centered(draw, title, title_font, start_y,
                                          W, INK, line_gap=12)
    # タイトル右脇にバブル画像（任意）。slide["bubble"] 指定時のみ。
    paste_title_bubble(img, slide, title, title_font, start_y, end_title_y, band_y)
    rule_y = end_title_y + 18
    _hairline(draw, rule_y)

    y = rule_y + 50
    for i, it in enumerate(items):
        # 番号は明朝・GOLD、本文は sans・INK、横並び 1 行
        num = f"{i+1:02d}"
        num_font = get_serif(34)
        num_bbox = num_font.getbbox(num)
        num_w = num_bbox[2] - num_bbox[0]
        item_bbox = item_font.getbbox(it)
        item_w = item_bbox[2] - item_bbox[0]
        gap = 28
        total = num_w + gap + item_w
        x = (W - total) // 2
        draw.text((x, y + 8), num, font=num_font, fill=GOLD)
        draw.text((x + num_w + gap, y), it, font=item_font, fill=INK)
        y += ITEM_H

    if footer:
        _hairline(draw, y, x1=W // 2 - 60, x2=W // 2 + 60, width=2)
        draw_centered(draw, footer, footer_font, y + 22, W, GOLD)

    return img.convert("RGB")


def generate_cta_slide(img, slide):
    title_font = get_serif(50)
    body_font = get_sans(34)
    sub_font = get_sans(28)

    title = normalize_text(slide.get("title", ""))
    body = normalize_text(slide.get("body", ""))
    subtitle = normalize_text(slide.get("subtitle", ""))

    title_h = measure_lines(title_font, title, line_gap=12)
    body_lines = body.split("\n")
    body_h = len(body_lines) * 56
    sub_lines = subtitle.split("\n")
    sub_h = len(sub_lines) * 44
    block_h = title_h + 28 + 1 + 60 + body_h + 50 + 1 + 40 + sub_h

    # content_h を渡して photo zone を必要なら自動縮小（本文オーバーフロー防止）
    img, band_y, band_h = _slide_frame(img, slide, content_h=block_h)
    draw = ImageDraw.Draw(img)

    # 万一 block_h > band_h でも上方向にはみ出さないようクランプ
    start_y = band_y + max(0, (band_h - block_h) // 2)

    end_title_y = draw_multiline_centered(draw, title, title_font, start_y,
                                          W, INK, line_gap=12)
    rule_y = end_title_y + 18
    _hairline(draw, rule_y)

    y = rule_y + 50
    for line in body_lines:
        if line:
            bbox = body_font.getbbox(line)
            x = (W - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, font=body_font, fill=INK)
        y += 56

    y += 30
    _hairline(draw, y, x1=W // 2 - 50, x2=W // 2 + 50, width=2)
    y += 30

    # subtitle: 最終行に 💌 が含まれていなければ自動付与（旧仕様の継承）
    emoji_font = get_emoji_font(28)
    last_idx = len(sub_lines) - 1
    for i, line in enumerate(sub_lines):
        if line:
            if i == last_idx and "💌" not in line:
                draw_with_emoji_suffix(draw, line, "💌", sub_font, emoji_font,
                                       y, W, GOLD)
            else:
                draw_centered(draw, line, sub_font, y, W, GOLD)
        y += 44

    return img.convert("RGB")


def generate_raw(img, _slide):
    """画像をそのまま使用（文字なし）— slide7/slide8 用、デザイン変更対象外"""
    return crop_center(img).convert("RGB")


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------
def generate_all():
    generate_with_slides(SLIDES)


def generate_with_slides(slides: list):
    """カスタムSLIDESで画像生成（create_post.py から呼ばれる）"""
    print("カルーセル画像を生成中...")
    generators = {
        "cover": generate_cover,
        "text": generate_text_slide,
        "list": generate_list_slide,
        "cta": generate_cta_slide,
        "raw": generate_raw,
    }

    for i, slide in enumerate(slides, 1):
        print(f"  {i}/{len(slides)}枚目を生成中...")
        bg = load_background(slide["filename"])
        result = generators[slide["type"]](bg, slide)
        output_path = os.path.join(OUTPUT_DIR, f"carousel_{i:02d}.jpg")
        result.save(output_path, "JPEG", quality=95)
        print(f"  保存: {output_path}")

    print(f"\n完了！{OUTPUT_DIR}/ フォルダに{len(slides)}枚保存されました")


if __name__ == "__main__":
    generate_all()
