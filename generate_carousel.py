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
import math
import unicodedata
from PIL import Image, ImageDraw, ImageFont, ImageOps
import os

from review_post import MOSAIC_TILE_COUNT


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

# list スライドを list_marker="bullet" にしたときの点の半径
BULLET_R = 7


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
        "title": "MIKI指名  Instagram限定20%OFF\n（VIPコースのみ）",
        "body": "美容と健康に興味がある。\n素直に自分と向き合える。\nそんな花嫁様、ぜひ会いに来てください",
        "subtitle": "コースの流れとご料金は\nプロフィールのリンクにまとめています\n気になる方はのぞいてみてください",
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
    # 合成前の最後の入口。create_post.py を通さずここへ来る背景
    # （generate_carousel.py 単体実行・手置きの背景・末尾固定の slide8/slide7）でも
    # EXIF の回転を画素へ反映させる。orientation なしの画像では実質そのまま。
    return ImageOps.exif_transpose(Image.open(path)).convert("RGBA")


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

    has_title = bool(title.strip())
    title_h = measure_lines(title_font, title, line_gap=12)
    body_lines = body.split("\n")
    body_h = len(body_lines) * LINE_H
    # タイトルがある時のみタイトル高さ＋区切り線＋余白を確保。
    # タイトルが空（画像側に見出しがある場合）は本文のみを帯中央に配置し、
    # 宙に浮いた区切り線が出ないようにする。
    block_h = (title_h + 30 + 1 + 80 + body_h) if has_title else body_h

    # content_h を渡して photo zone を必要なら自動縮小（本文オーバーフロー防止）
    img, band_y, band_h = _slide_frame(img, slide, content_h=block_h)
    draw = ImageDraw.Draw(img)

    # 万一 block_h > band_h でも上方向にはみ出さないようクランプ
    start_y = band_y + max(0, (band_h - block_h) // 2)

    if has_title:
        end_title_y = draw_multiline_centered(draw, title, title_font, start_y,
                                              W, INK, line_gap=12)
        rule_y = end_title_y + 18
        _hairline(draw, rule_y)
        # 区切り線から本文まで 70px（旧 100px から狭めて全体バランス調整）
        y = rule_y + 70
    else:
        y = start_y

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

    # 行頭マーカーは明朝・GOLD、本文は sans・INK、横並び 1 行。
    # マーカー・本文とも全項目で同じ x に揃える（行ごとに中央寄せすると
    # 左端がガタつくため）。ブロック全体を中央に置いて左揃えを実現する。
    # list_marker="bullet" で 01/02… の連番ではなく点の箇条書きにする
    # （順序のない並びに番号を振ると「順番がある」誤読を招くため）。
    use_bullet = str(slide.get("list_marker", "number")).lower() == "bullet"
    num_font = get_serif(34)
    gap = 28
    if use_bullet:
        nums = []
        num_w = BULLET_R * 2
    else:
        nums = [f"{i+1:02d}" for i in range(len(items))]
        num_w = max((num_font.getbbox(n)[2] - num_font.getbbox(n)[0]) for n in nums) if nums else 0
    item_w = max((item_font.getbbox(it)[2] - item_font.getbbox(it)[0]) for it in items) if items else 0
    x = max(24, (W - (num_w + gap + item_w)) // 2)
    item_x = x + num_w + gap

    y = rule_y + 50
    for idx, it in enumerate(items):
        if use_bullet:
            # 本文の実描画範囲（ink box）の中央に点を合わせる。数字を並べる
            # ときと違い、点は1つしかないので行ごとに高さがズレると目立つ。
            top, bottom = item_font.getbbox(it)[1], item_font.getbbox(it)[3]
            cy = y + (top + bottom) / 2
            draw.ellipse([x, cy - BULLET_R, x + BULLET_R * 2, cy + BULLET_R],
                         fill=GOLD)
        else:
            draw.text((x, y + 8), nums[idx], font=num_font, fill=GOLD)
        draw.text((item_x, y), it, font=item_font, fill=INK)
        y += ITEM_H

    if footer:
        _hairline(draw, y, x1=W // 2 - 60, x2=W // 2 + 60, width=2)
        draw_centered(draw, footer, footer_font, y + 22, W, GOLD)

    return img.convert("RGB")


def generate_price_slide(img, slide):
    """料金表（左右2カラム＋縦の区切り線）。
    写真ゾーンが左右にコースを並べた画像のとき、その真下に各コースの料金が
    縦に揃うようにする。columns は最大2つ。

    slide 例:
      "type": "price",
      "title": "料金のご案内",
      "top_note": "全て税込",
      "columns": [{"label": "スペシャル", "lines": ["平日 15,800円", "土日祝 16,800円"]}, ...],
      "notes": ["指名料 ＋1,000円", ...]
    """
    title_font = get_serif(54)
    label_font = get_serif(34)
    price_font = get_sans(40)
    note_font = get_sans(30)
    top_note_font = get_sans(28)
    PRICE_H = 58
    NOTE_H = 46

    title = normalize_text(slide.get("title", ""))
    top_note = normalize_text(slide.get("top_note", "")) if slide.get("top_note") else ""
    columns = slide.get("columns", [])[:2]
    notes = [normalize_text(n) for n in slide.get("notes", [])]

    highlight = slide.get("highlight")
    # 実描画に合わせた高さ（ラベル行 46px ＋ 価格行まわり 94px）
    hl_h = (94 + (46 if highlight.get("label") else 0)) if highlight else 0

    has_title = bool(title.strip())
    max_lines = max([len(c.get("lines", [])) for c in columns], default=0)
    title_h = measure_lines(title_font, title, line_gap=12)
    col_h = 46 + max_lines * PRICE_H          # ラベル＋価格行
    block_h = ((title_h + 28 + 1 if has_title else 0)
               + (66 if top_note else 8) + 26
               + col_h + hl_h + (36 + len(notes) * NOTE_H if notes else 0))

    img, band_y, band_h = _slide_frame(img, slide, content_h=block_h)
    draw = ImageDraw.Draw(img)
    start_y = band_y + max(0, (band_h - block_h) // 2)

    # タイトルが空（画像側に見出しがある場合）は区切り線も出さない
    if has_title:
        end_title_y = draw_multiline_centered(draw, title, title_font, start_y,
                                              W, INK, line_gap=12)
        rule_y = end_title_y + 18
        _hairline(draw, rule_y)
        y = rule_y + 26
    else:
        y = start_y + 26

    if top_note:
        # 縦の区切り線と同じ中心軸に載るため、カラムとの間隔を広めに取る
        draw_centered(draw, top_note, top_note_font, y, W, GOLD)
        y += 66
    else:
        y += 8

    def _at_center(text, font, yy, cx, fill):
        b = font.getbbox(text)
        draw.text((cx - (b[2] - b[0]) // 2 - b[0], yy), text, font=font, fill=fill)

    # 左右カラム（中心 x）。写真ゾーンの左右分割と揃える。
    # 1カラムのときは中央寄せ（タイトル・注記と軸を揃えるため）。
    centers = [int(W * 0.27), int(W * 0.73)] if len(columns) == 2 else [W // 2]
    col_top = y
    for ci, col in enumerate(columns):
        cx = centers[ci] if ci < len(centers) else W // 2
        label = normalize_text(col.get("label", ""))
        cy = col_top
        if label:
            _at_center(label, label_font, cy, cx, GOLD)
        cy += 46
        for ln in col.get("lines", []):
            _at_center(normalize_text(ln), price_font, cy, cx, INK)
            cy += PRICE_H

    # 縦の区切り線（2カラムのときのみ）
    if len(columns) == 2:
        vx = W // 2
        draw.line([(vx, col_top - 4), (vx, col_top + col_h - 8)], fill=GOLD, width=2)

    y = col_top + col_h

    # 割引の強調ブロック（定価に取り消し線＋割引後価格）
    if highlight:
        y += 26
        hl_label = normalize_text(highlight.get("label", ""))
        if hl_label:
            draw_centered(draw, hl_label, note_font, y, W, GOLD)
            y += 46
        strike = normalize_text(highlight.get("strike", ""))
        final = normalize_text(highlight.get("price", ""))
        s_font = get_sans(36)
        f_font = get_sans(52)
        MUTED = (150, 138, 126, 255)
        sb = s_font.getbbox(strike) if strike else (0, 0, 0, 0)
        fb = f_font.getbbox(final) if final else (0, 0, 0, 0)
        sw, fw = sb[2] - sb[0], fb[2] - fb[0]
        gap = 26 if (strike and final) else 0
        x = (W - (sw + gap + fw)) // 2
        if strike:
            sy = y + 12
            draw.text((x - sb[0], sy), strike, font=s_font, fill=MUTED)
            mid = sy + (sb[1] + sb[3]) // 2
            draw.line([(x - 4, mid), (x + sw + 4, mid)], fill=MUTED, width=3)
        if final:
            draw.text((x + sw + gap - fb[0], y), final, font=f_font, fill=GOLD)
        y += 68

    if notes:
        y += 36
        for n in notes:
            draw_centered(draw, n, note_font, y, W, INK)
            y += NOTE_H

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
# 案B: 全面写真レイアウト（frame / phrase）
# ---------------------------------------------------------------------------
# 案A（上=写真ゾーン＋下=クリーム帯の2分割）とは別系統の、写真を全面に敷いて
# その上に文字を置く型。案Aの「例外」ではなく、並立する第2の型として扱う。
# rules/carousel-design.md が廃止と書いている旧 PINK / DARK テーマとは別物で、
# あれは「クリーム帯の代わりに濃色パネルを敷く」案。こちらは写真そのものが面になる。
#
# 白文字の可読性はシャドウではなくスクリム（下端から立ち上がる暗い帯）で作る。
# 「テキストのシャドウは全てなし」（rules/carousel-design.md）を案Bでも守るため。
SCRIM_RGB = (18, 14, 12)     # 黒よりは温かい、INK より暗い
SCRIM_MIN_ALPHA = 86         # 暗い写真でも最低これだけは沈める（文字の輪郭を出す）
SCRIM_MAX_ALPHA = 228        # 濃さの上限（写真を殺しきらないための安全弁）
SCRIM_TARGET_LUMA = 92       # 白文字が確実に読める、沈めた後の背景の明るさ
# 面積の小さい非常に明るい点（キャンドルの炎・窓・泡・金具の反射）は
# 90%点の測定をすり抜ける。実際 candle.jpg は 90%点が116しかないのに
# 炎が残り、沈めた後も174あった（＝そこに重なった文字だけ消える）。
# そこで上側のパーセンタイルも見て、必要ならさらに濃くする。
SCRIM_HIGHLIGHT_PERCENTILE = 0.995
SCRIM_HIGHLIGHT_TARGET = 150
# ここまで濃い帯が必要になった写真は、読めはするが全体が沈んで写真が死ぬ。
# 「沈めても読めない」は二段測定で起きなくなった（必要値の最大は173で
# SCRIM_MAX_ALPHA に届かない）ので、警告するのは可読性ではなく見栄えの方。
SCRIM_HEAVY_ALPHA = 150


def _region_luma(img: Image.Image, box, percentile: float = 0.90) -> float:
    """box 内の輝度の上位パーセンタイル（既定90%点）を返す。

    平均を使ってはいけない。白文字が飛ぶのは「領域の平均が明るい時」ではなく
    「文字が載るところに明るい部分がある時」で、平均だと左右の暗い部分に
    引っ張られて明るい箇所を見落とす（浴槽の白い泡の上で実際に起きた）。
    """
    region = img.convert("L").crop(box)
    hist = region.histogram()
    total = sum(hist)
    if total == 0:
        return 0.0
    threshold = total * percentile
    running = 0
    for value, count in enumerate(hist):
        running += count
        if running >= threshold:
            return float(value)
    return 255.0


def scrim_alpha_for(img: Image.Image, box) -> int:
    """box の明るさを実測して、白文字が読めるまで沈めるのに要る不透明度を返す。

    写真の明るさは1枚ごとに違う。固定値にすると、暗い写真では帯が濃すぎて
    写真が死に、明るい写真（泡・白いタオル・窓）では文字が飛ぶ。
    実際に測ってから決める。
    """
    scrim_luma = (0.299 * SCRIM_RGB[0] + 0.587 * SCRIM_RGB[1] + 0.114 * SCRIM_RGB[2])

    def _needed(luma: float, target: float) -> int:
        if luma <= target:
            return SCRIM_MIN_ALPHA
        ratio = (luma - target) / max(1.0, luma - scrim_luma)
        return round(ratio * 255)

    # 面全体の明るさ（90%点）と、小さく明るい点（99.5%点）の両方を見て、
    # 濃い方を採る。前者だけだと炎や反射がすり抜け、後者だけだと
    # 暗い写真に強すぎる帯がかかる。
    body = _needed(_region_luma(img, box), SCRIM_TARGET_LUMA)
    spot = _needed(_region_luma(img, box, SCRIM_HIGHLIGHT_PERCENTILE),
                   SCRIM_HIGHLIGHT_TARGET)
    return int(max(SCRIM_MIN_ALPHA, min(SCRIM_MAX_ALPHA, max(body, spot))))


def paste_bottom_scrim(img: Image.Image, height: int, fade: int,
                       max_alpha: int) -> Image.Image:
    """下端から height px の帯を重ねる。

    帯の上端 fade px で 0 から max_alpha まで立ち上げ、その下は max_alpha を保つ。
    こうすると文字が載る領域は一様に沈み、帯の上端は写真に溶けて境目が出ない。
    """
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    w, h = img.size
    height = max(0, min(h, int(height)))
    if height == 0:
        return img
    fade = max(1, min(height, int(fade)))

    # 1px 幅で作ってから横に伸ばす（行ごとのループを1回で済ませる）
    mask = Image.new("L", (1, height))
    for y in range(height):
        if y < fade:
            t = (y + 1) / fade
            # smoothstep。両端で傾きが0になるので、帯の上端も
            # 「立ち上がりが終わって一定になる点」も横線として見えない。
            # 二乗カーブだと後者で傾きが急に0になり、そこに筋が出た。
            mask.putpixel((0, y), int(max_alpha * t * t * (3.0 - 2.0 * t)))
        else:
            mask.putpixel((0, y), max_alpha)
    mask = mask.resize((w, height), Image.BILINEAR)
    scrim = Image.new("RGBA", (w, height), SCRIM_RGB + (0,))
    scrim.putalpha(mask)
    img.alpha_composite(scrim, (0, h - height))
    return img


def _block_width(font, lines) -> int:
    """複数行の中で最も横に長い行の幅（px）"""
    widths = []
    for line in lines:
        if not line:
            continue
        bbox = font.getbbox(line)
        widths.append(bbox[2] - bbox[0])
    return max(widths) if widths else 0


# 案Bで写真の上に置く文字の、左右の最小余白
PHOTO_TEXT_SIDE_MARGIN = 72
# 案B版CTAの文字のかたまりが、画面の上端から最低これだけ離れていること
PHOTO_CTA_TOP_MARGIN = 72
NOTE_FONT_SIZE = 46
NOTE_LINE_GAP = 16


def _fit_phrase_font(phrase: str, w: int = W, h: int = H):
    """phrase を指定の改行のまま収める、いちばん大きいフォントと行間を返す。

    縮めきっても入らなければ ValueError。ここで描くと draw_centered の x が
    負になって左右が切れた画像が、例外も警告もなく出来上がる。
    描画（generate_phrase_slide）と事前検査（validate_photo_text）で同じ計算を使う。
    """
    lines = phrase.split("\n")
    max_w = w - 96 * 2
    max_h = int(h * 0.46)
    size = 160
    while size >= 58:
        font = get_serif(size)
        gap = int(size * 0.26)
        if (_block_width(font, lines) <= max_w
                and measure_lines(font, phrase, line_gap=gap) <= max_h):
            return font, gap
        size -= 6
    raise ValueError(
        f"phrase が長すぎて収まりません: {phrase!r}\n"
        f"  案Bは1枚1文節です。短く割るか、\\n で改行を足してください"
        f"（自動折り返しはしません）。"
    )


def _check_note_fits(note: str, w: int = W):
    """frame の note が左右に収まるか。収まらなければ ValueError。"""
    font = get_sans(NOTE_FONT_SIZE)
    width = _block_width(font, note.split("\n"))
    limit = w - PHOTO_TEXT_SIDE_MARGIN * 2
    if width > limit:
        raise ValueError(
            f"note が長すぎて収まりません（幅 {width}px / 上限 {limit}px）: {note!r}\n"
            f"  \\n で改行を足してください（自動折り返しはしません）。"
        )
    return font


def _cta_photo_layout(slide: dict, w: int = W, h: int = H) -> dict:
    """案B版CTAの文字の寸法と位置を決め、画面に収まるか確かめる。

    描画（generate_cta_photo_slide）と事前検査（validate_photo_text）が
    同じ値を使うので、「検査は通ったのに描くとはみ出す」が起きない。
    """
    title_font = get_serif(56)
    body_font = get_sans(36)
    sub_font = get_sans(30)

    title = normalize_text(slide.get("title", ""))
    body = normalize_text(slide.get("body", ""))
    subtitle = normalize_text(slide.get("subtitle", ""))
    body_lines = body.split("\n")
    sub_lines = subtitle.split("\n")

    # subtitle の最終行には 💌 が付くので、その分も幅に入れる
    widest = max(_block_width(title_font, title.split("\n")),
                 _block_width(body_font, body_lines),
                 _block_width(sub_font, sub_lines) + sub_font.size + 12)
    limit = w - PHOTO_TEXT_SIDE_MARGIN * 2
    if widest > limit:
        raise ValueError(
            f"案B版CTAの文字が左右に収まりません（最大幅 {widest}px / 上限 {limit}px）。\n"
            f"  タイトルは改行版（CTA_REQUIRED_TITLE_ALT）を使い、本文は短く改行してください。"
        )

    # 描画と同じ積み方で高さを出す（タイトル → 罫 → 本文 → 短い罫 → subtitle）
    title_h = measure_lines(title_font, title, line_gap=14)
    block_h = (title_h + 14 + 18 + 50 + 60 * len(body_lines)
               + 20 + 30 + 48 * (len(sub_lines) - 1) + sub_font.size)
    bottom_margin = 96
    block_top = h - bottom_margin - block_h
    if block_top < PHOTO_CTA_TOP_MARGIN:
        raise ValueError(
            f"案B版CTAの文字が縦に収まりません（上端 {block_top}px）。本文の行数を減らしてください。"
        )
    return {
        "title_font": title_font, "body_font": body_font, "sub_font": sub_font,
        "title": title, "body_lines": body_lines, "sub_lines": sub_lines,
        "widest": widest, "block_top": block_top, "block_h": block_h,
    }


def validate_photo_text(slide: dict) -> None:
    """案Bの文字が画像に収まるかを、画像を読む前に確かめる。

    create_post.py が背景を1枚も落とす前に呼ぶ。描画の時点で気づくと、
    Drive からのダウンロードや generated/ の削除が済んだ後に止まることになる。
    """
    stype = slide.get("type")
    if stype == "phrase":
        phrase = normalize_text(slide.get("phrase") or "")
        if not phrase.strip():
            raise ValueError("phrase 型のスライドに phrase がありません")
        _fit_phrase_font(phrase)
    elif stype == "frame":
        note = normalize_text(slide.get("note") or "")
        if note.strip():
            _check_note_fits(note)
    elif stype == "cta" and slide.get("layout") == "photo":
        _cta_photo_layout(slide)
    elif stype == "tile":
        # 1枚ずつでも最小サイズで収まるか見ておく。全区画で共通のサイズは
        # その最小値以上になるので、ここを通れば mosaic_font() も通る。
        mosaic_font([_mosaic_word(slide)])


def _lay_scrim(canvas: Image.Image, text_top: int, block_h: int, widest: int,
               pad: int) -> Image.Image:
    """文字のかたまりの下に、明るさを実測して決めた濃さのスクリムを敷く。"""
    w, h = canvas.size
    solid_top = max(0, text_top - pad)
    # 明るさは「文字が実際に載る幅」だけで測る。画面の全幅で測ると、
    # 文字の無い左右の暗い部分に薄められて、中央の明るさを見落とす。
    x0 = max(0, (w - widest) // 2 - pad)
    x1 = min(w, (w + widest) // 2 + pad)
    alpha = scrim_alpha_for(canvas, (x0, solid_top, x1, h))
    if alpha > SCRIM_HEAVY_ALPHA:
        # 明るい写真では普通に起きる（読めなくなるわけではない）。
        # ただ帯の存在感が増すので、仕上がりを目で見るべき1枚として知らせる。
        print(f"    ⚠ 文字の下が明るいため、帯を濃く敷いています（不透明度 {alpha}/255）。"
              f"帯の境目と写真の見え方を目視で確認してください。")

    # 立ち上がり（fade）は文字の上端より「上」で終わらせる。
    # 帯の高さに対する割合で決めると、fade が文字の位置まで食い込んで
    # 上の行が半透明部分に載り、そこだけ白飛びする。
    # 帯が濃いほど立ち上がりを長く取る。明るい写真で濃い帯を短く立ち上げると、
    # 写真の上に灰色の箱が乗ったように見える（白いドレスや浜辺の写真で実際にそうなった）。
    fade_len = max(150, int(block_h * 0.45), int(alpha * 1.8))
    band_top = max(0, solid_top - fade_len)
    return paste_bottom_scrim(canvas, h - band_top, fade=solid_top - band_top,
                              max_alpha=alpha)


def _draw_over_photo(canvas: Image.Image, text: str, font, gap: int,
                     bottom_margin: int) -> Image.Image:
    """全面写真の下部に、スクリムを敷いてから白文字を中央揃えで置く。"""
    w, h = canvas.size
    block_h = measure_lines(font, text, line_gap=gap)
    text_top = h - bottom_margin - block_h
    widest = _block_width(font, text.split("\n"))
    canvas = _lay_scrim(canvas, text_top, block_h, widest, pad=max(24, gap))
    draw = ImageDraw.Draw(canvas)
    draw_multiline_centered(draw, text, font, text_top, w,
                            (255, 255, 255, 255), line_gap=gap)
    return canvas


def generate_frame_slide(img: Image.Image, slide: dict) -> Image.Image:
    """パラパラ漫画の1コマ。全面写真で、原則として文字を置かない。

    note を書いた時だけ下端に小さく重ねる（参考にした投稿が1枚目にだけ
    「ドットを押さえてスクロール」と入れていたのと同じ役割）。
    """
    canvas = crop_center_with_focus(img, float(slide.get("focus_y", 0.5))).convert("RGBA")

    note = normalize_text(slide.get("note") or "")
    if not note.strip():
        return canvas.convert("RGB")

    font = _check_note_fits(note, canvas.size[0])
    canvas = _draw_over_photo(canvas, note, font, gap=NOTE_LINE_GAP, bottom_margin=88)
    return canvas.convert("RGB")


def generate_cta_photo_slide(img: Image.Image, slide: dict) -> Image.Image:
    """案B版のCTA。全面写真＋スクリムの上に、案Aと同じ構成の文字を置く。

    案Bの投稿（flipbook / phrase）は全面写真が続くので、最後の1枚だけ
    クリーム帯になると質感が切り替わってしまう。構成（タイトル → 罫 →
    本文 → 短い罫 → subtitle＋💌）は案Aを踏襲する。
    文字は subtitle も含めて白。案Aの subtitle は金色だが、スクリムは白文字が
    読める明るさに合わせて敷くので、金色では明るい写真でコントラストが足りない
    （LP への唯一の導線がそこだけ読めなくなる）。金色は罫だけに残す。
    """
    canvas = crop_center_with_focus(img, float(slide.get("focus_y", 0.5))).convert("RGBA")
    w, h = canvas.size
    lay = _cta_photo_layout(slide, w, h)
    block_top = lay["block_top"]

    canvas = _lay_scrim(canvas, block_top, lay["block_h"], lay["widest"], pad=40)
    draw = ImageDraw.Draw(canvas)
    white = (255, 255, 255, 255)

    end_title_y = draw_multiline_centered(draw, lay["title"], lay["title_font"],
                                          block_top, w, white, line_gap=14)
    rule_y = end_title_y + 18
    _hairline(draw, rule_y)

    y = rule_y + 50
    for line in lay["body_lines"]:
        if line:
            draw_centered(draw, line, lay["body_font"], y, w, white)
        y += 60

    y += 20
    _hairline(draw, y, x1=w // 2 - 50, x2=w // 2 + 50, width=2)
    y += 30

    # subtitle の最終行に 💌 を自動付与するのは案Aと同じ（SKILL.md が
    # 「絵文字を数える時は勘定に入れる」と書いている挙動を変えない）
    emoji_font = get_emoji_font(30)
    sub_lines = lay["sub_lines"]
    last_idx = len(sub_lines) - 1
    for i, line in enumerate(sub_lines):
        if line:
            if i == last_idx and "💌" not in line:
                draw_with_emoji_suffix(draw, line, "💌", lay["sub_font"], emoji_font,
                                       y, w, white)
            else:
                draw_centered(draw, line, lay["sub_font"], y, w, white)
        y += 48

    return canvas.convert("RGB")


# CTA の layout に書いてよい値。省略時は案A（クリーム帯）。
VALID_CTA_LAYOUTS = {"photo"}


def _cta_dispatch(img: Image.Image, slide: dict) -> Image.Image:
    """CTAスライドの見た目を案A／案Bで切り替える。

    型を `cta` のまま保つのが要点。review_post.py の CTA固定文言チェック・
    check_lp_guidance()・末尾CTA検査はすべて type == "cta" を見ているので、
    別の型にすると予約導線の機械チェックが一斉に効かなくなる。
    """
    layout = slide.get("layout")
    if layout is not None and layout not in VALID_CTA_LAYOUTS:
        # "Photo" などの打ち間違いを案A扱いにすると、案Bの投稿の最後だけ
        # クリーム帯に白もやの質感で出てしまう。黙って進ませない。
        raise ValueError(f"cta の layout=\"{layout}\" は不正です（\"photo\" のみ・省略で案A）")
    if layout == "photo":
        return generate_cta_photo_slide(img, slide)
    return generate_cta_slide(img, slide)


def generate_phrase_slide(img: Image.Image, slide: dict) -> Image.Image:
    """全面写真＋日本語の文節ひとつ。スワイプすると文が組み上がる型。

    自動折り返しはしない。改行は content.json 側で \n を入れる
    （既存のタイトル・本文と同じ約束）。文字サイズだけは、指定された改行の
    まま収まるところまでコードが自動で落とす。
    """
    canvas = crop_center_with_focus(img, float(slide.get("focus_y", 0.5))).convert("RGBA")

    phrase = normalize_text(slide.get("phrase") or "")
    if not phrase.strip():
        raise ValueError("phrase 型のスライドに phrase がありません")

    font, gap = _fit_phrase_font(phrase, *canvas.size)
    canvas = _draw_over_photo(canvas, phrase, font, gap=gap, bottom_margin=132)
    return canvas.convert("RGB")


# ---------------------------------------------------------------------------
# 案B: mosaic（9分割・積み上げ）
#   画面を3×3に割り、1枚めくるごとに区画が1つ埋まる。区画ごとに別の写真と
#   文節1つを置き、9枚目で写真9枚と一文がそろう（Red Bull の投稿形式）。
# ---------------------------------------------------------------------------
MOSAIC_GRID = math.isqrt(MOSAIC_TILE_COUNT)
MOSAIC_TILE_W, MOSAIC_TILE_H = W // MOSAIC_GRID, H // MOSAIC_GRID
MOSAIC_TILE_PAD = 16
MOSAIC_FONT_MAX = 104
MOSAIC_FONT_MIN = 64          # これ未満でないと収まらない文節は「大きい文字」にならないので止める
MOSAIC_SHADOW_RGB = (24, 20, 18)
MOSAIC_SHADOW_OFFSET_RATIO = 0.045
MOSAIC_BOTTOM_GAP = 6         # 区画の下端余白（MOSAIC_TILE_PAD）に足す、文字の最下点までのすき間

# 区画数が平方数でない・キャンバスが割り切れないと、区画が画面外に貼られても気づけない
assert MOSAIC_GRID ** 2 == MOSAIC_TILE_COUNT, "MOSAIC_TILE_COUNT は平方数にする"
assert W % MOSAIC_GRID == 0 and H % MOSAIC_GRID == 0, "キャンバスが区画数で割り切れない"


def _mosaic_word_width(font, word: str) -> int:
    bb = font.getbbox(word)
    return bb[2] - bb[0]


def _mosaic_word(slide: dict) -> str:
    word = normalize_text(slide.get("phrase") or "").strip()
    if not word:
        raise ValueError("tile 型のスライドに phrase がありません")
    if "\n" in word:
        # 区画は小さいので2行にすると文字が区画の半分を覆う。1文節1行に限る。
        raise ValueError(f"tile 型の phrase は1行にしてください（改行なし）: 「{word}」")
    return word


def _mosaic_fits(font, word: str) -> bool:
    return _mosaic_word_width(font, word) <= MOSAIC_TILE_W - MOSAIC_TILE_PAD * 2


def mosaic_font(words: list):
    """全区画で同じ文字サイズにする。いちばん長い文節が収まる最大のサイズ。

    区画ごとにサイズを変えると、文がそろった9枚目で字の大きさがばらつく。
    """
    # 最小サイズは必ず試す（validate_photo_text は最小サイズで収まるかだけを見ているので、
    # 刻み幅の都合で最小サイズを飛ばすと、そこを通った文節がここで止まってしまう）
    for size in list(range(MOSAIC_FONT_MAX, MOSAIC_FONT_MIN, -2)) + [MOSAIC_FONT_MIN]:
        font = get_sans(size)
        if all(_mosaic_fits(font, w) for w in words):
            return font
    raise ValueError(
        f"tile の文節が区画に収まりません（{MOSAIC_FONT_MIN}px でもはみ出す）: "
        f"{' / '.join(w for w in words if not _mosaic_fits(get_sans(MOSAIC_FONT_MIN), w))}\n"
        f"  文節を短く割り直してください（1区画の目安は全角4文字まで）。"
    )


def mosaic_baseline(font, words: list) -> int:
    """全区画で共通のベースライン（y）。

    区画ごとに文字の最下点で下ぞろえすると、字形（「ー」や「ぐ」など）で
    ベースラインが数px上下し、そろった時に横一列の文字がガタつく。
    いちばん下に出る字が下端余白に収まる位置で、全区画のベースラインをそろえる。
    """
    lowest = max(font.getbbox(w, anchor="ls")[3] for w in words)
    return MOSAIC_TILE_H - MOSAIC_TILE_PAD - MOSAIC_BOTTOM_GAP - lowest


def _mosaic_tile(img: Image.Image, slide: dict, font, baseline: int) -> Image.Image:
    """区画1つ分の写真に文節を載せる。

    【例外】案Bのシャドウ禁止（rules/carousel-design.md）はこの型だけ外している
    （2026-09-23 ユーザー指定）。区画は写真ごとに明るさがばらばらで、
    スクリムを区画ごとに敷くと9枚目に帯の濃淡が並んで見えるため、白＋影で統一する。
    """
    tile = crop_center_with_focus(img, float(slide.get("focus_y", 0.5)),
                                  size=(MOSAIC_TILE_W, MOSAIC_TILE_H)).convert("RGB")
    word = _mosaic_word(slide)
    bb = font.getbbox(word, anchor="ls")
    x = (MOSAIC_TILE_W - (bb[2] - bb[0])) // 2 - bb[0]
    off = max(2, int(font.size * MOSAIC_SHADOW_OFFSET_RATIO))
    draw = ImageDraw.Draw(tile)
    draw.text((x + off, baseline + off), word, font=font, fill=MOSAIC_SHADOW_RGB, anchor="ls")
    draw.text((x, baseline), word, font=font, fill=(255, 255, 255), anchor="ls")
    return tile


class _MosaicBuilder:
    """tile スライドを順に受け取り、それまでの区画を積み上げた1枚を返す。

    generate_with_slides() の generators 辞書に bound method として入る
    （他の型と同じ (bg, slide) の呼び出し形のまま、前の区画を覚えておくため）。
    """

    def __init__(self, slides: list):
        words = [_mosaic_word(s) for s in slides if s.get("type") == "tile"]
        self.font = mosaic_font(words) if words else None
        self.baseline = mosaic_baseline(self.font, words) if words else None
        self.tiles = []

    def add(self, img: Image.Image, slide: dict) -> Image.Image:
        if len(self.tiles) >= MOSAIC_TILE_COUNT:
            raise ValueError(f"tile は{MOSAIC_TILE_COUNT}枚までです")
        self.tiles.append(_mosaic_tile(img, slide, self.font, self.baseline))
        canvas = Image.new("RGB", (W, H), CREAM[:3])
        for n, tile in enumerate(self.tiles):
            row, col = divmod(n, MOSAIC_GRID)
            canvas.paste(tile, (col * MOSAIC_TILE_W, row * MOSAIC_TILE_H))
        return canvas


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
        "price": generate_price_slide,
        "cta": _cta_dispatch,
        "raw": generate_raw,
        # 案B（全面写真レイアウト）
        "frame": generate_frame_slide,
        "phrase": generate_phrase_slide,
        "tile": _MosaicBuilder(slides).add,
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
