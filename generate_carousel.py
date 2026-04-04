from PIL import Image, ImageDraw, ImageFont
from drive_helper import get_file_url
from dotenv import load_dotenv
import os
import requests
from io import BytesIO

load_dotenv()

OUTPUT_DIR = "generated"
os.makedirs(OUTPUT_DIR, exist_ok=True)

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
        "title": "MIKI指名  初回限定20%OFF",
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


def download_image_from_drive(filename: str) -> Image.Image:
    url = get_file_url(filename)
    res = requests.get(url)
    img = Image.open(BytesIO(res.content)).convert("RGBA")
    return img


def crop_center(img: Image.Image, size=(1080, 1080)) -> Image.Image:
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
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/Library/Fonts/Arial Unicode MS.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                continue
    return ImageFont.load_default()


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


def gold_border(draw, size=1080):
    draw.rectangle([20, 20, size-20, size-20], outline=(212, 175, 55, 255), width=5)
    draw.rectangle([34, 34, size-34, size-34], outline=(212, 175, 55, 160), width=2)


def add_text_bg(img, y, height, color=(255, 255, 255, 180)):
    """テキストの背後に半透明の帯を追加"""
    band = Image.new("RGBA", (1080, height), color)
    img.paste(band, (0, y), band)
    return img


def generate_cover(img, slide):
    img = crop_center(img)
    img = add_overlay(img, 80)
    draw = ImageDraw.Draw(img)
    gold_border(draw)

    font_tag = get_font(30)
    font_title = get_font(66)

    PINK = (100, 30, 60, 255)
    GOLD = (160, 120, 30, 255)

    # タグの背景帯
    img = add_text_bg(img, 140, 60, (255, 240, 245, 200))
    draw = ImageDraw.Draw(img)

    # タグ
    draw_centered(draw, slide["tag"], font_tag, 152, 1080, GOLD)

    # タイトルの背景帯
    img = add_text_bg(img, 360, 200, (255, 245, 248, 210))
    draw = ImageDraw.Draw(img)

    # タイトル
    y = 375
    for line in slide["title"].split("\n"):
        h = draw_centered(draw, line, font_title, y, 1080, PINK)
        y += h + 15

    return img.convert("RGB")


def generate_text_slide(img, slide):
    img = crop_center(img)
    img = add_overlay(img, 80)
    img = add_text_bg(img, 80, 920, (255, 248, 250, 210))
    draw = ImageDraw.Draw(img)
    gold_border(draw)

    font_title = get_font(48)
    font_text = get_font(36)
    LINE_H = 58
    PINK = (100, 30, 60, 255)
    DARK = (50, 20, 40, 255)

    # 本文の行数から全体の高さを計算して縦中央に配置
    lines = slide["text"].split("\n")
    title_h = 70  # タイトル＋区切り線のスペース
    content_h = len(lines) * LINE_H
    total_h = title_h + 30 + content_h
    start_y = (1080 - total_h) // 2

    # タイトル
    draw_centered(draw, slide["title"], font_title, start_y, 1080, PINK)
    line_y = start_y + title_h
    draw.line([(150, line_y), (930, line_y)], fill=(212, 175, 55, 220), width=2)

    # 本文
    y = line_y + 30
    for line in lines:
        if line:
            bbox = font_text.getbbox(line)
            w = bbox[2] - bbox[0]
            x = (1080 - w) // 2
            draw.text((x, y), line, font=font_text, fill=DARK)
        y += LINE_H

    return img.convert("RGB")


def generate_list_slide(img, slide):
    img = crop_center(img)
    img = add_overlay(img, 80)
    img = add_text_bg(img, 80, 920, (255, 248, 250, 210))
    draw = ImageDraw.Draw(img)
    gold_border(draw)

    font_title = get_font(46)
    font_item = get_font(33)
    font_footer = get_font(34)
    ITEM_H = 118
    PINK = (100, 30, 60, 255)
    DARK = (50, 20, 40, 255)

    # 全体の高さを計算して縦中央配置
    total_h = 70 + len(slide["items"]) * ITEM_H + (60 if "footer" in slide else 0)
    start_y = (1080 - total_h) // 2

    draw_centered(draw, slide["title"], font_title, start_y, 1080, PINK)
    line_y = start_y + 68
    draw.line([(100, line_y), (980, line_y)], fill=(212, 175, 55, 220), width=2)

    y = line_y + 20
    for item in slide["items"]:
        draw.text((90, y), item, font=font_item, fill=DARK)
        y += ITEM_H

    if "footer" in slide:
        draw.line([(100, y), (980, y)], fill=(212, 175, 55, 220), width=2)
        draw_centered(draw, slide["footer"], font_footer, y + 15, 1080, PINK)

    return img.convert("RGB")


def generate_cta_slide(img, slide):
    img = crop_center(img)
    img = add_overlay(img, 80)
    img = add_text_bg(img, 80, 920, (255, 248, 250, 215))
    draw = ImageDraw.Draw(img)
    gold_border(draw)

    font_title = get_font(44)
    font_body = get_font(34)
    font_sub = get_font(32)
    PINK = (100, 30, 60, 255)
    DARK = (50, 20, 40, 255)

    draw_centered(draw, slide["title"], font_title, 180, 1080, PINK)
    draw.line([(150, 255), (930, 255)], fill=(212, 175, 55, 220), width=2)

    y = 295
    for line in slide["body"].split("\n"):
        if line:
            bbox = font_body.getbbox(line)
            w = bbox[2] - bbox[0]
            x = (1080 - w) // 2
            draw.text((x, y), line, font=font_body, fill=DARK)
        y += 62

    draw.line([(150, y + 20), (930, y + 20)], fill=(212, 175, 55, 220), width=2)

    y += 50
    for line in slide["subtitle"].split("\n"):
        draw_centered(draw, line, font_sub, y, 1080, PINK)
        y += 55

    return img.convert("RGB")


def crop_top(img: Image.Image, size=(1080, 1080)) -> Image.Image:
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
    print("カルーセル画像を生成中...")
    generators = {
        "cover": generate_cover,
        "text": generate_text_slide,
        "list": generate_list_slide,
        "cta": generate_cta_slide,
        "raw": generate_raw,
    }

    for i, slide in enumerate(SLIDES, 1):
        print(f"  {i}/6枚目を生成中...")
        bg = download_image_from_drive(slide["filename"])
        result = generators[slide["type"]](bg, slide)
        output_path = os.path.join(OUTPUT_DIR, f"carousel_{i:02d}.jpg")
        result.save(output_path, "JPEG", quality=95)
        print(f"  保存: {output_path}")

    print(f"\n完了！{OUTPUT_DIR}/ フォルダに6枚保存されました")


if __name__ == "__main__":
    generate_all()
