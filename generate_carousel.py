import unicodedata
from PIL import Image, ImageDraw, ImageFont
import os


def normalize_text(text: str) -> str:
    """Unicode NFC正規化＋フォントで描画できない可能性のある文字を除去"""
    text = unicodedata.normalize("NFC", text)
    # サロゲートペアなど壊れた文字を除去
    return text.encode("utf-8", errors="ignore").decode("utf-8")

OUTPUT_DIR = "generated"
BACKGROUNDS_DIR = "backgrounds"
os.makedirs(OUTPUT_DIR, exist_ok=True)

W, H = 1080, 1350  # 4:5 縦長サイズ

# スライドの内容定義
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
        raise FileNotFoundError(f"背景画像が見つかりません: {path}\nbackgrounds/フォルダに {filename} を置いてください")
    return Image.open(path).convert("RGBA")


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
    img = img.crop((left, top, left + target_w, top + target_h))
    return img


def get_font(size: int):
    font_paths = [
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
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                continue
    return ImageFont.load_default()


def get_emoji_font(size: int):
    """絵文字フォントを取得（macOS: Apple Color Emoji / Linux: NotoColorEmoji）"""
    emoji_font_paths = [
        "/System/Library/Fonts/Apple Color Emoji.ttc",   # macOS
        "/System/Library/Fonts/AppleColorEmoji.ttf",     # macOS (別パス)
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",  # Linux
        "/usr/share/fonts/noto/NotoColorEmoji.ttf",           # Linux (別パス)
    ]
    for path in emoji_font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                continue
    return None


def draw_with_emoji_suffix(draw, text, suffix_emoji, font, emoji_font, y, img_width, fill):
    """テキスト本文を中央揃えで描画し、末尾に絵文字を追加する。
    絵文字フォントが利用可能な場合は絵文字を別フォントで描画する。"""
    # テキスト部分の幅
    main_bbox = font.getbbox(text)
    main_w = main_bbox[2] - main_bbox[0]
    main_h = main_bbox[3] - main_bbox[1]

    # 絵文字部分の幅
    if emoji_font is not None:
        try:
            emo_bbox = emoji_font.getbbox(suffix_emoji)
            emo_w = emo_bbox[2] - emo_bbox[0]
        except Exception:
            emo_w = main_h  # 高さを幅の目安に
    else:
        emo_w = main_h

    total_w = main_w + 8 + emo_w  # 8px gap
    start_x = (img_width - total_w) // 2

    # テキスト本文（シャドウ付き）
    draw.text((start_x + 2, y + 2), text, font=font, fill=(0, 0, 0, 60))
    draw.text((start_x, y), text, font=font, fill=fill)

    # 絵文字
    emoji_x = start_x + main_w + 8
    if emoji_font is not None:
        try:
            draw.text((emoji_x, y), suffix_emoji, font=emoji_font, fill=fill, embedded_color=True)
        except TypeError:
            draw.text((emoji_x, y), suffix_emoji, font=emoji_font, fill=fill)
    else:
        draw.text((emoji_x, y), suffix_emoji, font=font, fill=fill)

    return main_h


def add_overlay(img: Image.Image, opacity: int = 130) -> Image.Image:
    overlay = Image.new("RGBA", img.size, (255, 255, 255, opacity))
    return Image.alpha_composite(img, overlay)


def draw_centered(draw, text, font, y, img_width, fill):
    bbox = font.getbbox(text)
    w = bbox[2] - bbox[0]
    x = (img_width - w) // 2
    draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, 60))
    draw.text((x, y), text, font=font, fill=fill)
    return bbox[3] - bbox[1]


def _calc_title_h(font, title_text, line_gap=10):
    """タイトルの実際の高さを計算（複数行対応）"""
    lines = title_text.split("\n")
    total = 0
    for line in lines:
        ref = line if line else "あ"
        bbox = font.getbbox(ref)
        total += (bbox[3] - bbox[1]) + line_gap
    return total


def _draw_title(draw, title_text, font, y_start, img_width, fill, line_gap=10):
    """複数行タイトルを中央揃えで描画し、最終行の下端y座標を返す"""
    lines = title_text.split("\n")
    y = y_start
    for line in lines:
        if line:
            h = draw_centered(draw, line, font, y, img_width, fill)
        else:
            bbox = font.getbbox("あ")
            h = bbox[3] - bbox[1]
        y += h + line_gap
    return y


def gold_border(draw, w=W, h=H):
    draw.rectangle([20, 20, w-20, h-20], outline=(212, 175, 55, 255), width=5)
    draw.rectangle([34, 34, w-34, h-34], outline=(212, 175, 55, 160), width=2)


def add_text_bg(img, y, height, color=(255, 255, 255, 180)):
    """テキストの背後に半透明の帯を追加"""
    band = Image.new("RGBA", (W, height), color)
    img.paste(band, (0, y), band)
    return img


def generate_cover(img, slide):
    img = crop_center(img)
    img = add_overlay(img, 80)
    draw = ImageDraw.Draw(img)
    gold_border(draw)

    font_tag = get_font(36)
    font_title = get_font(66)

    PINK = (100, 30, 60, 255)
    GOLD = (160, 120, 30, 255)

    # タグの背景帯（上から1/6あたり）
    TAG_BAND_Y, TAG_BAND_H = 175, 65
    img = add_text_bg(img, TAG_BAND_Y, TAG_BAND_H, (255, 240, 245, 200))
    draw = ImageDraw.Draw(img)

    # タグ（帯の中央に配置）
    tag_text = normalize_text(slide["tag"])
    tag_bbox = font_tag.getbbox(tag_text)
    tag_h = tag_bbox[3] - tag_bbox[1]
    tag_y = TAG_BAND_Y + (TAG_BAND_H - tag_h) // 2
    draw_centered(draw, tag_text, font_tag, tag_y, W, GOLD)

    # タイトルの背景帯（縦中央より少し上）
    TITLE_BAND_Y, TITLE_BAND_H = 490, 230
    img = add_text_bg(img, TITLE_BAND_Y, TITLE_BAND_H, (255, 245, 248, 210))
    draw = ImageDraw.Draw(img)

    # タイトル（帯内で垂直中央配置）
    title_text = normalize_text(slide["title"])
    title_h = _calc_title_h(font_title, title_text, line_gap=15)
    y = TITLE_BAND_Y + (TITLE_BAND_H - title_h) // 2
    _draw_title(draw, title_text, font_title, y, W, PINK, line_gap=15)

    return img.convert("RGB")


def generate_text_slide(img, slide):
    img = crop_center(img)
    img = add_overlay(img, 80)
    img = add_text_bg(img, 80, H - 160, (255, 248, 250, 210))
    draw = ImageDraw.Draw(img)
    gold_border(draw)

    font_title = get_font(48)
    font_text = get_font(36)
    LINE_H = 58
    PINK = (100, 30, 60, 255)
    DARK = (50, 20, 40, 255)

    title_text = normalize_text(slide["title"])
    body_text = normalize_text(slide["text"])

    # タイトルの実際の高さを計算（複数行対応）
    title_h = _calc_title_h(font_title, title_text)
    lines = body_text.split("\n")
    content_h = len(lines) * LINE_H
    # 合計高さ: タイトル + 区切り線余白(20) + 区切り線(2) + 本文上余白(100) + 本文
    total_h = title_h + 20 + 2 + 100 + content_h
    start_y = (H - total_h) // 2

    # タイトル（複数行対応）
    after_title_y = _draw_title(draw, title_text, font_title, start_y, W, PINK)

    # 区切り線（タイトル末尾から20px下）
    line_y = after_title_y + 20
    draw.line([(150, line_y), (930, line_y)], fill=(212, 175, 55, 220), width=2)

    # 本文（区切り線から100px下）
    y = line_y + 100
    for line in lines:
        if line:
            bbox = font_text.getbbox(line)
            w = bbox[2] - bbox[0]
            x = (W - w) // 2
            draw.text((x, y), line, font=font_text, fill=DARK)
        y += LINE_H

    return img.convert("RGB")


def generate_list_slide(img, slide):
    img = crop_center(img)
    img = add_overlay(img, 80)
    img = add_text_bg(img, 80, H - 160, (255, 248, 250, 210))
    draw = ImageDraw.Draw(img)
    gold_border(draw)

    font_title = get_font(46)
    font_item = get_font(42)
    font_footer = get_font(34)
    ITEM_H = 140
    PINK = (100, 30, 60, 255)
    DARK = (50, 20, 40, 255)

    title_text = normalize_text(slide["title"])

    # タイトルの実際の高さを計算（複数行対応）
    title_h = _calc_title_h(font_title, title_text)
    # 合計高さ: タイトル + 区切り線余白(20) + 区切り線(2) + 項目上余白(45) + 項目 + フッター
    total_h = title_h + 20 + 2 + 45 + len(slide["items"]) * ITEM_H + (60 if "footer" in slide else 0)
    start_y = (H - total_h) // 2

    # タイトル（複数行対応）
    after_title_y = _draw_title(draw, title_text, font_title, start_y, W, PINK)

    # 区切り線（タイトル末尾から20px下）
    line_y = after_title_y + 20
    draw.line([(100, line_y), (980, line_y)], fill=(212, 175, 55, 220), width=2)

    # 項目（区切り線から45px下、中央揃え）
    y = line_y + 45
    for item in slide["items"]:
        item_text = normalize_text(item)
        bbox = font_item.getbbox(item_text)
        iw = bbox[2] - bbox[0]
        ix = (W - iw) // 2
        draw.text((ix, y), item_text, font=font_item, fill=DARK)
        y += ITEM_H

    if "footer" in slide:
        draw.line([(100, y), (980, y)], fill=(212, 175, 55, 220), width=2)
        draw_centered(draw, normalize_text(slide["footer"]), font_footer, y + 15, W, PINK)

    return img.convert("RGB")


def generate_cta_slide(img, slide):
    img = crop_center(img)
    img = add_overlay(img, 80)
    img = add_text_bg(img, 80, H - 160, (255, 248, 250, 215))
    draw = ImageDraw.Draw(img)
    gold_border(draw)

    font_title = get_font(44)
    font_body = get_font(34)
    font_sub = get_font(32)
    PINK = (100, 30, 60, 255)
    DARK = (50, 20, 40, 255)

    title_text = normalize_text(slide["title"])
    body_lines = normalize_text(slide["body"]).split("\n")

    # タイトルの実際の高さを計算（複数行対応）
    title_h = _calc_title_h(font_title, title_text)
    # 合計高さ: タイトル + 区切り線余白(20) + 区切り線(2) + 本文上余白(60) + 本文 + 区切り線余白(60) + サブタイトル
    total_h = title_h + 20 + 2 + 60 + len(body_lines) * 62 + 60 + 55
    start_y = (H - total_h) // 2

    # タイトル（複数行対応）
    after_title_y = _draw_title(draw, title_text, font_title, start_y, W, PINK)

    # 区切り線（タイトル末尾から20px下）
    line_y = after_title_y + 20
    draw.line([(150, line_y), (930, line_y)], fill=(212, 175, 55, 220), width=2)

    # 本文（区切り線から60px下）
    y = line_y + 60
    for line in body_lines:
        line = normalize_text(line)
        if line:
            bbox = font_body.getbbox(line)
            w = bbox[2] - bbox[0]
            x = (W - w) // 2
            draw.text((x, y), line, font=font_body, fill=DARK)
        y += 62

    draw.line([(150, y + 20), (930, y + 20)], fill=(212, 175, 55, 220), width=2)

    y += 50
    subtitle_lines = normalize_text(slide["subtitle"]).split("\n")
    emoji_font = get_emoji_font(32)
    for i, line in enumerate(subtitle_lines):
        is_last = (i == len(subtitle_lines) - 1)
        # 最後の行のみ 💌 を自動付与（まだ含まれていない場合）
        if is_last and "💌" not in line:
            draw_with_emoji_suffix(draw, line, "💌", font_sub, emoji_font, y, W, PINK)
        else:
            draw_centered(draw, line, font_sub, y, W, PINK)
        y += 55

    return img.convert("RGB")


def crop_top(img: Image.Image, size=(W, H)) -> Image.Image:
    """上を優先してクロップ（上部のテキストが切れない）"""
    target_w, target_h = size
    orig_w, orig_h = img.size
    scale = max(target_w / orig_w, target_h / orig_h)
    new_w = int(orig_w * scale)
    new_h = int(orig_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    img = img.crop((left, 0, left + target_w, target_h))
    return img


def generate_raw(img, _slide):
    """画像をそのまま使用（文字なし）"""
    return crop_center(img).convert("RGB")


def generate_all():
    generate_with_slides(SLIDES)


def generate_with_slides(slides: list):
    """カスタムSLIDESで画像生成（修正処理用）"""
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
