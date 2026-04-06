import json
import os
import random
import urllib.parse
from datetime import datetime

import requests
from groq import Groq
from dotenv import load_dotenv

from generate_carousel import generate_with_slides
from register_post import register

load_dotenv()

INSTAGRAM_API_BASE = "https://graph.instagram.com/v19.0"

SYSTEM_PROMPT = """あなたはエステティシャンMIKIのInstagram投稿コンテンツ担当です。
テーマを受け取り、カルーセル投稿のスライド内容・キャプション・ハッシュタグを生成してください。

## MIKIについて
- Instagram: @estmiki
- エステティシャン・リラクゼーションサロンオーナー
- 専門: ブライダルエステ・ご褒美エステ
- 名前の表記はMIKI（大文字）
- ※キャプション・スライドにサロン名は記載しない（MIKI個人への予約導線を優先する）

## ブランドメッセージ
- 土台となる肌・体・メンタルを整えることが全ての美しさの根幹
- 丁寧・温かみがある・押し付けがましくない文体
- CTAは「MIKI指名 初回限定20%OFF」「DMからご相談」

## ターゲット
- 20代後半〜40代の女性
- バリキャリ・正社員・平日休み（美容・ホテル・アパレル・飲食業界など）
- 美容好き・素直・ダイエットに成功したことがない

## 投稿スタイル（重要）
- キャプションの冒頭は「MIKIです。」で始める
- キャプション末尾に必ずCTAを入れる
- キャプションは必ずテーマに即した内容で書く（テンプレートをそのまま使わない）
- 文章の長さ：1000〜1500文字程度（段落は短く区切り、読みやすさを優先）
- 絵文字は控えめに・要所のみ使用
- **後述の「MIKIの実際の過去投稿」を必ず参照し、MIKIの文体・言い回し・テンポを捉えて書くこと**
- スタイル（自分語り・情報提供・共感訴求など）はテーマに応じてAIが判断する（固定ではない）

## カルーセルスライドのルール
- スライド数: 5〜8枚をコンテンツに応じてAIが最適な枚数を判断する
  （末尾2枚はシステムが自動追加するので含めない）
- filenameは "bg01.jpg" "bg02.jpg" ... と連番で指定する
- スライドタイプと必須フィールド:

cover（表紙）:
  {"filename": "bg01.jpg", "type": "cover", "title": "タイトル（改行は\\nで）", "tag": "- サブタイトル -", "bg_strategy": "reuse|generate", "reuse_index": 番号}

text（テキスト）:
  {"filename": "bg02.jpg", "type": "text", "title": "セクションタイトル", "text": "本文（改行は\\nで）", "bg_strategy": "reuse|generate", "reuse_index": 番号}

list（リスト）:
  {"filename": "bg03.jpg", "type": "list", "title": "タイトル", "items": ["項目1", "項目2", ...], "footer": "締めの一言（省略可）", "bg_strategy": "reuse|generate", "reuse_index": 番号}

cta（コールトゥアクション）:
  {"filename": "bgN.jpg", "type": "cta", "title": "MIKI指名  初回限定20%OFF", "body": "本文（改行は\\nで）", "subtitle": "ご予約・ご相談はDMからお気軽にどうぞ", "bg_strategy": "reuse|generate", "reuse_index": 番号}

## bg_strategyの判断基準
各スライドに bg_strategy を必ず指定してください。
- "reuse": 過去画像をそのまま背景として使用（雰囲気がほぼ合う場合）。reuse_indexで番号指定。
- "edit": 過去画像をベースにPIL加工して使用（雰囲気は合うが少し調整したい場合）。reuse_indexで番号指定。
  - textスライド: ブラー + 明度アップ（文字が読みやすいよう加工）
  - coverスライド: 彩度・コントラスト調整
  - listスライド: ブラー + 軽い暗化
  - ctaスライド: 半透明ホワイトオーバーレイ
- "generate": テーマに特化した新しい画像が必要な場合（表紙や印象的な場面に推奨）
過去投稿画像が利用可能な場合は、テーマに合うものを積極的に reuse/edit で活用してください。
reuse_indexは利用可能な過去画像リストの番号（0始まり）を指定。範囲外の番号は指定しないこと。

## ハッシュタグ候補
ブライダルエステ系: #ブライダルエステ #ブライダルエステ東京 #ブライダルエステ体験 #プレ花嫁2026 #大人花嫁 #東京花嫁 #六本木エステ
ご褒美エステ系: #ご褒美エステ #ご褒美時間 #自分へのご褒美 #大人の女性 #六本木エステ #リラクゼーション
アラサー・アラフォー系: #アラサー美容 #アラフォー美容 #大人の肌ケア #30代美容 #40代美容 #六本木エステ
サロン紹介系: #六本木エステ #エステ体験 #プライベートサロン

※「#AMRTA」「#AMRTA六本木」などサロン名タグは絶対に使用しないこと

## 出力形式
必ずJSONのみを返してください。説明文は不要です。

{
  "slides": [...],
  "caption": "キャプション全文（テーマに即した内容・1000〜1500文字）",
  "hashtags": "#タグ1 #タグ2 ...",
  "memo": "このコンテンツの概要メモ＋MIKIへの予約が来やすくなるための提案（エンゲージメント・CTA改善案など）",
  "bg_prompt": "generate指定スライド用の背景画像生成プロンプト（英語、例: Japanese esthetic salon, soft pink, elegant woman relaxing, luxury spa）"
}
"""

BRIDAL_ADDON = """
## ブライダルエステ専用情報
- MIKIは自身も花嫁経験があり、それがブライダルエステを始めた原点
- 花嫁様の不安・迷いに寄り添う「一番の理解者」でありたいという姿勢
- これらはブライダルエステの投稿にのみ反映すること（一般エステには適用しない）
"""


def fetch_instagram_posts(limit: int = 30) -> list:
    """Meta Graph APIで過去の投稿を取得（キャプション・いいね数・画像URL含む）"""
    access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    account_id = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    if not access_token or not account_id:
        print("  Instagram APIトークンまたはアカウントIDが未設定のためスキップ")
        return []

    url = f"{INSTAGRAM_API_BASE}/{account_id}/media"
    params = {
        "fields": "id,caption,like_count,media_type,media_url,timestamp",
        "limit": limit,
        "access_token": access_token,
    }
    try:
        res = requests.get(url, params=params, timeout=30)
        data = res.json()
        if "error" in data:
            print(f"  過去投稿取得失敗: {data['error'].get('message', data['error'])}")
            return []
        posts = data.get("data", [])
        posts.sort(key=lambda p: p.get("like_count", 0), reverse=True)
        print(f"  {len(posts)}件の過去投稿を取得")
        return posts
    except Exception as e:
        print(f"  過去投稿取得失敗: {e}")
        return []


def fetch_carousel_image_urls(post_id: str) -> list:
    """カルーセル投稿の子画像URLリストを取得"""
    access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    url = f"{INSTAGRAM_API_BASE}/{post_id}/children"
    params = {"fields": "media_url", "access_token": access_token}
    try:
        res = requests.get(url, params=params, timeout=30)
        children = res.json().get("data", [])
        return [c["media_url"] for c in children if "media_url" in c]
    except Exception:
        return []


def collect_available_images(posts: list) -> list:
    """過去投稿から画像URL一覧を作成（Groqへの参考情報として使用）"""
    available = []
    for post in posts:
        media_type = post.get("media_type", "")
        caption_snippet = (post.get("caption") or "")[:60].replace("\n", " ")
        like_count = post.get("like_count", 0)

        if media_type == "IMAGE":
            url = post.get("media_url")
            if url:
                available.append({
                    "url": url,
                    "like_count": like_count,
                    "caption_snippet": caption_snippet,
                })
        elif media_type == "CAROUSEL_ALBUM":
            urls = fetch_carousel_image_urls(post["id"])
            for u in urls:
                available.append({
                    "url": u,
                    "like_count": like_count,
                    "caption_snippet": caption_snippet,
                })
    return available


def download_image(url: str, filename: str) -> bool:
    """指定URLから画像をbackgrounds/にダウンロード"""
    path = os.path.join("backgrounds", filename)
    try:
        res = requests.get(url, timeout=60)
        if res.status_code == 200 and len(res.content) > 10000:
            with open(path, "wb") as f:
                f.write(res.content)
            return True
    except Exception:
        pass
    return False


def apply_edit_effect(img_path: str, slide_type: str) -> None:
    """PILで画像を加工してスライド種別に合った背景に仕上げる"""
    from PIL import Image, ImageFilter, ImageEnhance
    img = Image.open(img_path).convert("RGB")
    img = img.resize((1080, 1350), Image.LANCZOS)

    if slide_type in ("text", "list"):
        img = img.filter(ImageFilter.GaussianBlur(radius=8))
        img = ImageEnhance.Brightness(img).enhance(1.3)
    elif slide_type == "cover":
        img = ImageEnhance.Color(img).enhance(1.2)
        img = ImageEnhance.Contrast(img).enhance(1.1)
    elif slide_type == "cta":
        overlay = Image.new("RGBA", img.size, (255, 255, 255, 80))
        img = img.convert("RGBA")
        img = Image.alpha_composite(img, overlay).convert("RGB")

    img.save(img_path, "JPEG", quality=90)


def generate_pollinations(bg_prompt: str, filename: str) -> bool:
    """Pollinations.aiで背景画像を1枚生成してbackgrounds/に保存"""
    full_prompt = f"{bg_prompt}, soft light, elegant, minimal background, no text, no watermark, photography"
    encoded = urllib.parse.quote(full_prompt)
    seed = random.randint(1000, 99999)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1350&nologo=true&seed={seed}"
    path = os.path.join("backgrounds", filename)
    try:
        res = requests.get(url, timeout=120)
        if res.status_code == 200 and len(res.content) > 10000:
            with open(path, "wb") as f:
                f.write(res.content)
            return True
    except Exception:
        pass
    return False


def resolve_backgrounds(slides: list, available_images: list, bg_prompt: str) -> None:
    """各スライドのbg_strategyに従って背景ファイルを決定しfilenameを更新"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    generate_count = 0

    print("\n背景画像を準備中...")
    for i, slide in enumerate(slides):
        strategy = slide.get("bg_strategy", "generate")
        reuse_index = slide.get("reuse_index", 0)
        filename = f"bg_{timestamp}_{i+1:02d}.jpg"

        if strategy == "reuse" and available_images and reuse_index < len(available_images):
            img = available_images[reuse_index]
            print(f"  スライド{i+1}: 過去投稿を転用（いいね{img['like_count']}件）")
            success = download_image(img["url"], filename)
            if success:
                slide["filename"] = filename
                continue
            print(f"    → ダウンロード失敗、Pollinations.aiで代替生成")

        elif strategy == "edit" and available_images and reuse_index < len(available_images):
            img_info = available_images[reuse_index]
            print(f"  スライド{i+1}: 過去投稿をPIL加工して使用（いいね{img_info['like_count']}件）")
            success = download_image(img_info["url"], filename)
            if success:
                apply_edit_effect(os.path.join("backgrounds", filename), slide.get("type", "text"))
                slide["filename"] = filename
                continue
            print(f"    → ダウンロード失敗、Pollinations.aiで代替生成")

        # generate または reuse失敗時
        generate_count += 1
        print(f"  スライド{i+1}: Pollinations.aiで生成中...")
        success = generate_pollinations(bg_prompt, filename)
        if success:
            slide["filename"] = filename
        else:
            fallback = f"slide{(i % 6) + 1}.jpg"
            slide["filename"] = fallback
            print(f"    → 生成失敗、フォールバック: {fallback}")


def generate_content(theme: str, menu: str, notes: str = "",
                     past_posts: list = None, available_images: list = None) -> dict:
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    system = SYSTEM_PROMPT
    if "ブライダル" in menu or "花嫁" in theme:
        system += BRIDAL_ADDON

    # 過去の高反応投稿キャプションを文体参考として追加
    if past_posts:
        top_captions = [
            p["caption"] for p in past_posts[:10]
            if p.get("caption") and len(p["caption"]) > 100
        ][:3]
        if top_captions:
            captions_text = "\n\n---\n\n".join(top_captions)
            system += f"""
## MIKIの実際の過去投稿（文体・言い回し・テンポの参考）
以下はMIKIの実際のInstagram投稿キャプションです。
言い回し・文体・特徴・テンポをよく読み、今回のテーマに合わせた内容を生成してください。
内容をそのまま使用したり、似た投稿を作ることはしないこと。

{captions_text}
"""

    # 利用可能な過去画像の一覧をGroqに渡す
    if available_images:
        img_list = "\n".join([
            f"- index {i}: いいね{img['like_count']}件, 内容「{img['caption_snippet']}」"
            for i, img in enumerate(available_images[:20])
        ])
        system += f"""
## 利用可能な過去投稿画像（bg_strategy指定用）
以下の画像が転用可能です。テーマ・雰囲気に合う場合は積極的に活用してください。
（キャプションの内容から画像の雰囲気を判断してください）

{img_list}

各スライドのbg_strategyを "reuse"（転用）または "generate"（新規生成）で指定し、
"reuse"の場合はreuse_indexで上記の番号を指定してください。
"""
    else:
        system += "\n## 注意\n過去投稿画像は取得できませんでした。全スライドbg_strategy=\"generate\"にしてください。\n"

    user_message = f"テーマ: {theme}\nメニュー種別: {menu}"
    if notes:
        user_message += f"\n追加指示: {notes}"

    print("Groq APIでコンテンツを生成中...")
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
        max_tokens=4096,
    )

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def run(theme: str, menu: str, post_datetime: str, notes: str = ""):
    # 過去のInstagram投稿を取得
    print("過去のInstagram投稿を取得中...")
    past_posts = fetch_instagram_posts(limit=30)

    # 過去画像URLを一覧化（Groqへの参考情報 + ダウンロード用）
    available_images = collect_available_images(past_posts) if past_posts else []
    if available_images:
        print(f"  利用可能な過去画像: {len(available_images)}枚")

    # コンテンツ生成（過去キャプションを文体参考、過去画像リストを背景選択参考に）
    result = generate_content(theme, menu, notes, past_posts, available_images)

    num_slides = len(result["slides"])
    print(f"\n生成完了！スライド数: {num_slides}枚")
    print(f"メモ: {result['memo']}")

    # 各スライドの背景をbg_strategyに従って解決
    bg_prompt = result.get("bg_prompt", "Japanese esthetic salon, soft pink, elegant, luxury spa")
    resolve_backgrounds(result["slides"], available_images, bg_prompt)

    # slide8.jpg → slide7.jpg（MIKIプロフィール）を末尾2枚として自動追加
    result["slides"].append({"filename": "slide8.jpg", "type": "raw"})
    result["slides"].append({"filename": "slide7.jpg", "type": "raw"})

    print(f"\n最終スライド数: {len(result['slides'])}枚（末尾2枚はslide8・slide7固定）")

    # 画像生成
    print("\nカルーセル画像を生成中...")
    generate_with_slides(result["slides"])

    # GitHubアップロード＆スプレッドシート登録
    print("\nスプレッドシートに登録中...")
    register(
        post_datetime=post_datetime,
        menu_type=menu,
        caption=result["caption"],
        hashtags=result["hashtags"],
        memo=result["memo"],
    )


if __name__ == "__main__":
    run(
        theme="休みの日に一人でエステに行くことへの背中押し。疲れた体のリセット・リフレッシュ、首・肩・背中の凝りを解消し巡りを良くしてQOL向上",
        menu="ご褒美エステ",  # ブライダルエステ / ご褒美エステ / サロン紹介 など
        post_datetime="2026/04/08 21:00",
        notes="車やスマホも定期メンテが必要なように体も同じ、という実用的な切り口で。一人で行くことへの敷居の低さも伝える。",
    )
