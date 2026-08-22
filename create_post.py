import json
import os
from datetime import datetime

import requests
from groq import Groq

# HEIC画像（MIKIがDriveに追加する参考写真にiPhone由来のHEICが含まれる）を
# Pillowで開けるようにする。pillow-heif未導入の環境でも他形式は動くよう握りつぶす。
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    pass

from generate_carousel import generate_with_slides
from register_post import register
# Driveのテーマ名は review_post.py を正とする（同じ一覧を2か所に持たない）
from review_post import VALID_REUSE_THEMES, EMPTY_REUSE_THEMES
from load_env import load_from_zshrc
load_from_zshrc()

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
- CTAは「MIKI指名 Instagram限定20%OFF（VIPコースのみ）」「DMからご相談」

## ターゲット
- 20代後半〜40代の女性
- バリキャリ・正社員・平日休み（美容・ホテル・アパレル・飲食業界など）
- 美容好き・素直・ダイエットに成功したことがない

## 投稿スタイル（重要）
- キャプション構成（SEO対応・必ず守ること）：
  1. 1〜2行目：主要キーワードを含む導入文（Instagramの検索エンジン最適化のため。テーマに直接関連するキーワードを自然な文として含める）
  2. 3行目以降：「MIKIです。」から本文開始
- キャプション末尾に必ずCTAを入れる
- キャプションは必ずテーマに即した内容で書く（テンプレートをそのまま使わない）
- 文章の長さ：1000〜1500文字程度（段落は短く区切り、読みやすさを優先）
- 絵文字は3〜5個が適切（多すぎは幼稚な印象・少なすぎは固い印象。段落の締めとCTAのみ使用）
- **後述の「MIKIの実際の過去投稿」を必ず参照し、MIKIの文体・言い回し・テンポを捉えて書くこと**
- スタイル（自分語り・情報提供・共感訴求など）はテーマに応じてAIが判断する（固定ではない）

## カルーセルスライドのルール
- スライド数: 5〜6枚をコンテンツに応じてAIが最適な枚数を判断する
  （末尾2枚はシステムが自動追加するので含めない。合計7〜8枚が上限）
- filenameは "bg01.jpg" "bg02.jpg" ... と連番で指定する
- **スライドタイトル（title）にはMIKIを使っても良い（品格のある表現のみ）**
- **スライド本文（text/body フィールド）は一人称を「私」に統一する（MIKIを使わない）**
  - NG: 「MIKIは〜を大切にしています」→ OK: 「私は〜を大切にしています」
- スライドタイプと必須フィールド:

cover（表紙）:
  {"filename": "bg01.jpg", "type": "cover", "title": "タイトル（改行は\\nで）", "tag": "- サブタイトル -", "bg_strategy": "reuse|edit|generate", "reuse_index": 番号}

text（テキスト）:
  {"filename": "bg02.jpg", "type": "text", "title": "セクションタイトル", "text": "本文（改行は\\nで・一人称は「私」）", "bg_strategy": "reuse|edit|generate", "reuse_index": 番号}

list（リスト）:
  {"filename": "bg03.jpg", "type": "list", "title": "タイトル", "items": ["項目1（全角20文字以内）", "項目2", ...], "footer": "締めの一言（省略可）", "bg_strategy": "reuse|edit|generate", "reuse_index": 番号}

cta（コールトゥアクション）:
  {"filename": "bgN.jpg", "type": "cta", "title": "MIKI指名  Instagram限定20%OFF\n（VIPコースのみ）", "body": "本文（改行は\\nで）", "subtitle": "ご予約・ご相談はDMからお気軽にどうぞ", "bg_strategy": "reuse|edit|generate", "reuse_index": 番号}

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
※ reuse/edit には reuse_source を必ず書くこと（"drive" / "instagram"）。
  "drive" の場合は reuse_theme（menu / bridal / lifestyle）と reuse_filename（Driveの実ファイル名）も
  必須で、reuse_index では代用できない（3点セットが欠けると投稿生成は例外で停止する）。

## ハッシュタグ候補
ブライダルエステ系: #ブライダルエステ #ブライダルエステ東京 #ブライダルエステ体験 #プレ花嫁2026 #大人花嫁 #東京花嫁 #六本木エステ
ご褒美エステ系: #ご褒美エステ #ご褒美時間 #自分へのご褒美 #大人の女性 #六本木エステ #リラクゼーション
アラサー・アラフォー系: #アラサー美容 #アラフォー美容 #大人の肌ケア #30代美容 #40代美容 #六本木エステ
サロン紹介系: #六本木エステ #エステ体験 #プライベートサロン

※「#AMRTA」「#AMRTA六本木」などサロン名タグは絶対に使用しないこと

## テキスト品質ルール（必ず守ること）

### 言語
- すべてのテキストは日本語で書くこと。英語・ローマ字・記号（「-」「・」以外）は一切使用しない

### スライド本文の文量・改行ルール
- textスライドの"text"フィールド:
  - 必ず5〜7行（\nで区切る）
  - 1行は自然な文節・文の区切りで改行（1行あたり15〜25文字程度）
  - 短すぎる行（5文字以下）や1語だけの行は絶対に作らない
  - 良い例: "車やスマホは定期メンテナンスが必要なように\n私たちの体も同じ。\n疲れを溜め込むと巡りが悪くなり\n肌荒れ・だるさ・免疫低下につながります。\n定期的にエステでリセットすることが\n体を長く健康に保つ一番の近道です。"

- listスライドの"items": 各項目15〜30文字の完結した文（箇条書きらしい短さ）

- ctaスライドの"body": 2〜4行、読者への具体的な呼びかけ。1行10〜30文字
  - **必ず「〜はMIKIにお任せください。」「〜をMIKIにお任せください。」で締めること（恒久ルール）**
  - 禁止フレーズ（絶対に使わない）: 「MIKIに会いに来てください」「MIKIに会いにきてください」「まずはお気軽にDMでご連絡ください」「お気軽にDMでご連絡ください」
  - subtitleに「ご予約・ご相談はDMからお気軽にどうぞ」があるためbodyに重複させない

### キャプションの書き方
- 段落の区切りは必ず\n\nを使うこと（段落間に空行を入れる）
- 各段落は3〜5文で構成し、完結した内容にする
- 1000〜1500文字程度、全体で7〜10段落程度

### 過去画像のreuse/edit選択
- caption_snippetを必ず確認してから戦略を選ぶこと
- snippet に「死海」「Bath Salt」「商品」「価格」「¥」「セール」が含まれる場合はgenerateを使う
- エステ施術・サロン・リラックス・女性の美容・スパに関連する内容の場合のみreuse/editを選ぶ

## 恒久デザインルール（修正依頼でも絶対に変えないこと）

### 背景画像のルール
- bg_promptには必ず小文字の "no people" を含めること（人物なし・静物・インテリア写真を優先）
- bg_promptにピンク系の色を指定しないこと（pink / magenta / fuchsia / blush / salmon は禁止）。
  white / beige / cream / gold / warm tone を使うこと
- 過激・性的・露骨な肌露出は避けること。ウェディングドレスや適度な露出は問題なし
- 不自然に過激な構図（施術中の肌露出など）は生成しない

### 末尾固定スライド
- 後ろから2枚目: slide8.jpg（固定メニュースライド）
- 最後: slide7.jpg（MIKIプロフィール）
- AIはこれらを slides に含めないこと（システムが自動追加する）

### 投稿全体のスライド上限
- AIが生成するスライドは最大6枚（slide8・slide7と合わせて合計8枚以内）

## 出力形式
必ずJSONのみを返してください。説明文は不要です。

{
  "slides": [...],
  "caption": "キャプション全文（1〜2行目にキーワード導入文、3行目から「MIKIです。」で開始、1000〜1500文字）",
  "hashtags": "#タグ1 #タグ2 ...",
  "alt_text": "画像の中に何が写っていて何が起きているかを短い文章で記載（キーワード羅列NG。例: 白いトリートメントベッドが並ぶ落ち着いた照明のエステルーム）",
  "memo": "このコンテンツの概要メモ＋MIKIへの予約が来やすくなるための提案（エンゲージメント・CTA改善案など）",
  "bg_prompt": "generate指定スライド用の背景画像生成プロンプト（英語、例: Japanese esthetic salon, warm beige, no people, luxury spa interior）"
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


_BAD_BG_KEYWORDS = [
    "死海", "Bath Salt", "bath salt", "期間限定価格", "セール", "値下げ",
    "オーダーメイドコース", "コース料金", "メニュー価格",
]


def collect_available_images(posts: list, menu_type: str = "") -> list:
    """過去投稿から画像URL一覧を作成（Groqへの参考情報として使用）
    明らかに不適切な背景（製品広告・価格キャンペーン）のみ除外する。
    """
    available = []

    for post in posts:
        media_type = post.get("media_type", "")
        caption = post.get("caption") or ""
        caption_snippet = caption[:60].replace("\n", " ")
        like_count = post.get("like_count", 0)

        # 製品広告・価格キャンペーン投稿は除外
        if any(kw in caption for kw in _BAD_BG_KEYWORDS):
            continue

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


def list_reference_images() -> list:
    """「施術・メニュー紹介」フォルダから「参考N」画像を一覧取得する。
    ユーザーが随時追加した参考画像（参考1, 参考2, ...）を動的に検索する。
    Returns: [{"name": "参考1", "id": "..."}, ...]（名前の数値順でソート）
    """
    try:
        from drive_manager import list_drive_images
        all_files = list_drive_images("menu")
        refs = [f for f in all_files if f.get("name", "").startswith("参考")]
        # 数値部分でソート（参考1, 参考2, ... 参考10, ...）
        def _sort_key(f):
            name = f.get("name", "")
            num_part = name.replace("参考", "").split(".")[0]
            try:
                return int(num_part)
            except ValueError:
                return 999
        refs.sort(key=_sort_key)
        if refs:
            print(f"  参考画像: {len(refs)}枚 ({', '.join(f['name'] for f in refs)})")
        else:
            print("  参考画像: なし（Drive「施術・メニュー紹介」フォルダに「参考N」画像を追加してください）")
        return refs
    except Exception as e:
        print(f"  参考画像取得失敗: {e}")
        return []


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
    """PILで画像を加工してスライド種別に合った背景に仕上げる。

    【厳守・再発防止】ユーザーから「画像がぼやける／アスペクト比が変わる」と
    繰り返し指摘されている。以下を絶対に入れないこと:
      - ぼかし（ImageFilter.GaussianBlur）… 写真は鮮明に見せる
      - 1080x1350 への強制 resize … アスペクト比が崩れて被写体が伸びる
    アスペクト比はそのまま保持し、クロップは generate_carousel.py の
    crop_center_with_focus()（cover-fit センタークロップ）に任せる。"""
    from PIL import Image, ImageEnhance
    img = Image.open(img_path).convert("RGB")

    if slide_type in ("text", "list"):
        img = ImageEnhance.Brightness(img).enhance(1.05)
    elif slide_type == "cover":
        img = ImageEnhance.Color(img).enhance(1.2)
        img = ImageEnhance.Contrast(img).enhance(1.1)
    elif slide_type == "cta":
        overlay = Image.new("RGBA", img.size, (255, 255, 255, 80))
        img = img.convert("RGBA")
        img = Image.alpha_composite(img, overlay).convert("RGB")

    img.save(img_path, "JPEG", quality=90)


def generate_image_hf(bg_prompt: str, filename: str, seed: int = None) -> tuple:
    """HF FLUX.1-schnell で背景画像を生成して backgrounds/ に保存
    Returns: (成功したか, 使用したseed)
    """
    from hf_generator import generate_image
    path = os.path.join("backgrounds", filename)
    try:
        _, used_seed = generate_image(prompt=bg_prompt, seed=seed, output_path=path)
        return True, used_seed
    except Exception as e:
        print(f"    HF生成失敗: {e}")
        return False, seed or 0


# reuse / edit のスライドに必須のDrive指定。1つでも欠けたら投稿を作らない。
REQUIRED_DRIVE_REUSE_KEYS = ("reuse_source", "reuse_theme", "reuse_filename")
# reuse_source に書いてよい値。想定外の値は typo として止める。
VALID_REUSE_SOURCES = {"drive", "instagram"}
# bg_strategy に書いてよい値。typo（"reues" 等）はどの分岐にも入らず
# 末尾のHF生成に到達してしまうので、値そのものをここで確定させる。
VALID_BG_STRATEGIES = {"reuse", "edit", "generate", "local"}
# bg_prompt に書いてはいけない色（ピンク系）。white / beige / cream / gold / warm tone を使う。
# "rose"（white roses 等）は実績に正当な用例があるため入れていない。
BANNED_BG_PROMPT_WORDS = ("pink", "ピンク", "magenta", "fuchsia", "blush", "salmon")


def validate_bg_prompt(bg_prompt: str, where: str = "トップレベル") -> str:
    """bg_prompt が恒久ルール（ピンク禁止・no people 必須）を満たすか検証する。

    以前はここに既定値
    "Japanese esthetic salon, soft pink, elegant, luxury spa" を置いていたが、
    これ自体がピンク禁止違反かつ no people 抜けで、bg_prompt の書き忘れを
    ルール違反のまま静かに通してしまっていた。既定値は持たせず、
    content.json の記入漏れとして止める。
    """
    prompt = (bg_prompt or "").strip()
    if not prompt:
        raise ValueError(
            f"{where}の bg_prompt がありません。\n"
            f"  generate に落ちたスライドで使う共通プロンプトなので必ず書いてください。\n"
            f"  ピンク系は指定せず（white / beige / cream / gold / warm tone）、"
            f"\"no people\" を必ず含めること。\n"
            f"  例: Calm white powder room with round mirror vanity, soft natural light, "
            f"no people, high quality photo"
        )
    hit = next((w for w in BANNED_BG_PROMPT_WORDS if w in prompt.lower()), None)
    if hit:
        raise ValueError(
            f"{where}の bg_prompt にピンク系の色指定 '{hit}' が含まれています: {prompt}\n"
            f"  ピンクは禁止です。white / beige / cream / gold / warm tone を使ってください。"
        )
    # 大文字小文字は緩めない。review_post.py:180 が "no people" の完全一致で見ているため、
    # ここで "No People" を通すと create_post は通って校閲だけが ❌ になる食い違いが出る。
    if "no people" not in prompt:
        raise ValueError(
            f"{where}の bg_prompt に \"no people\" がありません: {prompt}\n"
            f"  人物なし（静物・インテリア写真）を指定してください。\n"
            f"  小文字の \"no people\" という文字列そのものを含めること"
            f"（review_post.py が完全一致で見るため \"No People\" は不可）。"
        )
    return prompt


def _may_fall_back_to_generate(slide: dict) -> bool:
    """このスライドが HF生成（generate）に行き着く可能性があるか。

    Drive の reuse / edit は解決に失敗したら例外で止まる（生成へ落ちない）ので False。
    それ以外（generate / local / instagram）は生成に到達しうる。
    """
    return not (slide.get("bg_strategy") in ("reuse", "edit")
                and slide.get("reuse_source") == "drive")


def _validate_reuse_fields(slides: list) -> None:
    """bg_strategy の値と reuse / edit スライドのDrive指定を、画像を1枚も落とす前に検査する。

    1つでも欠けると「静かに別の画像で投稿が完成する」経路に落ちるため、
    content.json の書き間違いとしてここで止める。
      - bg_strategy の typo → どの分岐にも入らず末尾のHF生成に到達
      - reuse_source 欠落 → "instagram" 扱い → 取得が空 → HF生成へ落ちて全スライドAI画像
      - reuse_theme 欠落  → かつては "reward"（Driveに0枚）扱い → 原因の読めないエラー
      - reuse_filename 欠落 → かつては Drive の reuse_index 番目（既定0番）を黙って採用
    """
    for i, slide in enumerate(slides):
        strategy = slide.get("bg_strategy")
        # 打ち間違い（"reues" 等）はどの分岐にも入らず末尾のHF生成に到達するので、
        # 「知らない値ならAI生成」にせず、書き間違いとしてここで止める。
        if strategy is not None and strategy not in VALID_BG_STRATEGIES:
            raise ValueError(
                f"スライド{i+1}: bg_strategy=\"{strategy}\" は不正です"
                f"（{' / '.join(sorted(VALID_BG_STRATEGIES))} のみ・小文字）。\n"
                f"  未知の値はどの分岐にも入らず、黙ってAI生成に落ちます。"
            )
        if strategy not in ("reuse", "edit"):
            continue
        source = slide.get("reuse_source")
        # 値そのものが想定外（"Drive" / typo）だと3点セット検査を素通りして
        # Instagram経路 → HF生成へ落ちるので、値も含めてここで確定させる。
        if source and source not in VALID_REUSE_SOURCES:
            raise ValueError(
                f"スライド{i+1}: reuse_source=\"{source}\" は不正です"
                f"（{' / '.join(sorted(VALID_REUSE_SOURCES))} のみ・小文字）。\n"
                f"  Drive写真を使う場合は \"drive\" を指定してください。"
            )
        required = list(REQUIRED_DRIVE_REUSE_KEYS) if source in (None, "drive") else ["reuse_source"]
        missing = [k for k in required if not slide.get(k)]
        if missing:
            raise ValueError(
                f"スライド{i+1}: bg_strategy=\"{slide['bg_strategy']}\" なのに "
                f"{' / '.join(missing)} がありません。\n"
                f"  reuse_source / reuse_theme / reuse_filename は3点セットで必須です"
                f"（CLAUDE.md「content.json に必須の Drive 指定」）。\n"
                f"    reuse_source: \"drive\"\n"
                f"    reuse_theme:  {' / '.join(sorted(VALID_REUSE_THEMES))}\n"
                f"    reuse_filename: Driveの実ファイル名（大文字小文字・拡張子も一致必須）"
            )

        # テーマ名が不正だと Drive が空リストを返し、「ファイル名が見つかりません」という
        # 原因を取り違えさせるメッセージで止まる（テーマが悪いのにファイル名を疑わせる）。
        theme = slide.get("reuse_theme")
        if source in (None, "drive") and theme not in VALID_REUSE_THEMES:
            empty_note = ("（Drive に0枚のため使用不可）"
                          if theme in EMPTY_REUSE_THEMES else "")
            raise ValueError(
                f"スライド{i+1}: reuse_theme=\"{theme}\" は使えません{empty_note}。\n"
                f"  使えるのは {' / '.join(sorted(VALID_REUSE_THEMES))} のみです。"
            )


def resolve_backgrounds(slides: list, available_images: list, bg_prompt: str,
                        global_seed: int = None) -> int:
    """各スライドのbg_strategyに従って背景ファイルを決定しfilenameを更新
    Returns: 最後に使用したseed（generate時）
    """
    from PIL import Image as _Img
    os.makedirs("backgrounds", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    last_seed = global_seed

    # 1枚もダウンロードする前に全スライドのDrive指定を検査する。ループの中で止めると
    # 「6枚目の記入漏れなのに1〜5枚目は既に backgrounds/ に落ちている」状態になる。
    _validate_reuse_fields(slides)

    print("\n背景画像を準備中...")
    for i, slide in enumerate(slides):
        strategy = slide.get("bg_strategy", "generate")
        # reuse/edit の reuse_source は _validate_reuse_fields() で存在と値を確定済み
        reuse_source = slide.get("reuse_source")
        reuse_index = slide.get("reuse_index", 0)
        filename = f"bg_{timestamp}_{i+1:02d}.jpg"
        path = os.path.join("backgrounds", filename)

        # --- Drive 画像を使用 ---
        if strategy in ("reuse", "edit") and reuse_source == "drive":
            from drive_manager import list_drive_images, download_drive_image
            theme = slide["reuse_theme"]
            drive_files = list_drive_images(theme)
            # reuse_filename は上で必須化済み。reuse_index による暗黙の代替採用はしない
            # （指定漏れを0番目の画像で黙って埋めていたのが従来の事故経路）。
            reuse_filename = slide["reuse_filename"]
            matched_file = next((f for f in drive_files if f["name"] == reuse_filename), None)
            if not matched_file:
                # 指定した写真が無いのに黙って別画像やAI生成へ落とすと、
                # 意図しない画像で投稿が出来上がってしまう。ここで止める。
                raise ValueError(
                    f"スライド{i+1}: Drive [{theme}] に '{reuse_filename}' が見つかりません。\n"
                    f"  ライブのDriveでファイル名を確認してください（大文字小文字・拡張子も一致必須）:\n"
                    f"    /usr/bin/python3 -c \"from drive_manager import list_drive_images; "
                    f"print([x['name'] for x in list_drive_images('{theme}')])\""
                )
            print(f"  スライド{i+1}: Drive画像を使用（{theme}/{matched_file['name']}）")
            if not download_drive_image(matched_file["id"], path):
                raise ValueError(
                    f"スライド{i+1}: Drive [{theme}] の '{reuse_filename}' のダウンロードに失敗しました。\n"
                    f"  AI生成へ自動フォールバックはしません。Drive側を確認してやり直してください。"
                )
            if strategy == "edit":
                apply_edit_effect(path, slide.get("type", "text"))
            else:
                # reuse はそのまま転用（ぼかさない・鮮明に保つ）。
                # HEIC等を確実にJPEGへ正規化するため再保存のみ行う。
                _bg = _Img.open(path).convert("RGB")
                _bg.save(path, "JPEG", quality=90)
            slide["filename"] = filename
            continue

        # --- ローカルファイルを直接使用 ---
        elif strategy == "local":
            import shutil
            local_path = slide.get("local_path", "")
            if local_path and os.path.exists(local_path):
                shutil.copy(local_path, path)
                apply_edit_effect(path, slide.get("type", "text"))
                slide["filename"] = filename
                print(f"  スライド{i+1}: ローカルファイルを使用（{local_path}）")
                continue
            print(f"    → ローカルファイルが見つからない ({local_path})、HFで代替生成")

        # --- Instagram 過去投稿を使用 ---
        # ここで解決できなかった時に黙ってHF生成へ落とすと、2026-08-13 の
        # 「全スライドがAI画像」と同じ経路になる。Drive経路と同じく例外で止める。
        elif strategy in ("reuse", "edit"):
            if not available_images or reuse_index >= len(available_images):
                raise ValueError(
                    f"スライド{i+1}: reuse_source=\"instagram\" の過去画像 "
                    f"reuse_index={reuse_index} を解決できません"
                    f"（取得できた過去画像: {len(available_images)}枚）。\n"
                    f"  AI生成へ自動フォールバックはしません。"
                    f"reuse_source=\"drive\" でDrive写真を指定してください。"
                )
            img_info = available_images[reuse_index]
            print(f"  スライド{i+1}: 過去投稿を転用（いいね{img_info['like_count']}件）")
            if not download_image(img_info["url"], filename):
                raise ValueError(
                    f"スライド{i+1}: 過去投稿画像のダウンロードに失敗しました。\n"
                    f"  AI生成へ自動フォールバックはしません。"
                )
            if strategy == "edit":
                apply_edit_effect(path, slide.get("type", "text"))
            else:
                # reuse はそのまま転用（ぼかさない・鮮明に保つ）。
                _bg = _Img.open(path).convert("RGB")
                _bg.save(path, "JPEG", quality=90)
            slide["filename"] = filename
            continue

        # --- HF で新規生成（generate または上記失敗時） ---
        slide_seed = slide.get("seed") or global_seed
        # スライド個別のbg_promptがあればそちらを優先
        slide_prompt = slide.get("bg_prompt") or bg_prompt
        # 実際に生成へ渡す直前に、そのプロンプト自体もルール適合を確認する
        # （スライド個別 bg_prompt はここで初めて使われるため）。
        slide_prompt = validate_bg_prompt(slide_prompt, where=f"スライド{i+1}")
        print(f"  スライド{i+1}: HFで生成中...")
        success, used_seed = generate_image_hf(slide_prompt, filename, seed=slide_seed)
        if success:
            slide["filename"] = filename
            slide["_bg_generated"] = True  # Drive転用と区別する（Driveへの再アップロード判定用）
            last_seed = used_seed
            if not slide.get("seed"):
                slide["seed"] = used_seed
        else:
            fallback = f"slide{(i % 6) + 1}.jpg"
            slide["filename"] = fallback
            print(f"    → 生成失敗、フォールバック: {fallback}")

    return last_seed


def generate_content(theme: str, menu: str, notes: str = "",
                     past_posts: list = None, available_images: list = None,
                     reference_images: list = None) -> dict:
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

    # 参考画像（「施術・メニュー紹介」フォルダの「参考N」）の情報をGroqに渡す
    if reference_images:
        ref_list = "\n".join([
            f"- 参考{i+1}: ファイル名 \"{f['name']}\" (reuse_source=\"drive\", reuse_theme=\"menu\", reuse_filename=\"{f['name']}\")"
            for i, f in enumerate(reference_images)
        ])
        system += f"""
## 施術・メニュー紹介フォルダの参考画像（優先利用）
以下の画像がDriveの「施術・メニュー紹介」フォルダに入っています。
エステルーム・施術環境・メニューのテイストを参考にした画像です。
背景テイストのピンクが多い傾向があるため、これらのベージュ・ホワイト系の参考画像を優先的に活用してください。

{ref_list}

使用方法:
- reuse: bg_strategy="reuse", reuse_source="drive", reuse_theme="menu", reuse_filename="参考N" (そのまま転用)
- edit: bg_strategy="edit", reuse_source="drive", reuse_theme="menu", reuse_filename="参考N" (PIL加工転用)
- generate時の参考: bg_promptに「〜のような落ち着いたエステルーム空間」と記述して雰囲気を反映
"""
    else:
        system += "\n## 注意\n「施術・メニュー紹介」フォルダの参考画像は現在未登録です。bg_strategy=\"generate\"を使用してください。\n"

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

各スライドのbg_strategyを "reuse"（転用）"edit"（PIL加工転用）"generate"（新規生成）で指定し、
"reuse"/"edit"の場合はreuse_indexで上記の番号を指定してください。
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
    raw = _sanitize_json(raw)
    return json.loads(raw)


def _sanitize_json(raw: str) -> str:
    """JSON文字列内の不正な制御文字をエスケープ（簡易ステートマシン）"""
    import re
    # まず明らかに不要な制御文字を削除
    raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', raw)

    # JSON文字列内の生の改行・タブ・CRをエスケープ
    result = []
    in_string = False
    escape_next = False
    for ch in raw:
        if escape_next:
            result.append(ch)
            escape_next = False
        elif ch == '\\':
            result.append(ch)
            escape_next = True
        elif ch == '"':
            result.append(ch)
            in_string = not in_string
        elif in_string and ch == '\n':
            result.append('\\n')
        elif in_string and ch == '\r':
            result.append('\\r')
        elif in_string and ch == '\t':
            result.append('\\t')
        else:
            result.append(ch)
    return ''.join(result)


def _menu_to_theme(menu: str) -> str:
    """メニュー種別からDriveテーマを推定"""
    if "ブライダル" in menu or "花嫁" in menu:
        return "bridal"
    if "ご褒美" in menu or "自分磨き" in menu or "アラサー" in menu or "アラフォー" in menu:
        return "reward"
    if "施術" in menu or "メニュー" in menu or "コース" in menu:
        return "menu"
    return "lifestyle"


def _upload_backgrounds_to_drive(slides: list, theme: str) -> None:
    """resolve_backgrounds が **新規生成した** bg_*.jpg だけを
    Driveテーマフォルダにアップロードする（OAuth使用）。

    reuse / edit で Drive から落としてきた画像も backgrounds/bg_*.jpg という
    同じ名前になるため、ファイル名だけで判定するとサロンの実写がテーマフォルダに
    重複コピーされ、さらに AI生成画像もサロン写真と見分けがつかない状態で
    フォルダに混ざる。次の投稿がそれを reuse すると「意図しない生成画像の使用」に
    つながるので、resolve_backgrounds が付ける _bg_generated フラグで絞り込む。"""
    import json as _json
    from googleapiclient.discovery import build as _build
    from googleapiclient.http import MediaFileUpload as _MediaFileUpload
    from google.oauth2.credentials import Credentials as _OAuthCreds
    from google.auth.transport.requests import Request as _Request

    TOKEN_PATH = "token_drive.json"
    if not os.path.exists(TOKEN_PATH):
        print("  token_drive.json が見つかりません。Drive保存をスキップ")
        return

    folder_ids = {}
    if os.path.exists("drive_folders.json"):
        with open("drive_folders.json") as f:
            folder_ids = _json.load(f)
    folder_id = folder_ids.get(theme)
    if not folder_id:
        print(f"  Drive [{theme}] フォルダIDが未設定。Drive保存をスキップ")
        return

    try:
        creds = _OAuthCreds.from_authorized_user_file(TOKEN_PATH, ["https://www.googleapis.com/auth/drive"])
        if creds.expired and creds.refresh_token:
            creds.refresh(_Request())
        service = _build("drive", "v3", credentials=creds)
    except Exception as e:
        print(f"  Drive認証失敗（トークン期限切れの可能性）: {e}")
        print("  背景画像のDrive保存をスキップします")
        return

    print(f"\n生成した背景画像をDrive [{theme}] フォルダに保存中...")
    uploaded = 0
    for slide in slides:
        filename = slide.get("filename", "")
        if not filename.startswith("bg_") or not slide.get("_bg_generated"):
            continue
        local_path = os.path.join("backgrounds", filename)
        if not os.path.exists(local_path):
            continue
        try:
            metadata = {"name": filename, "parents": [folder_id]}
            media = _MediaFileUpload(local_path, mimetype="image/jpeg")
            service.files().create(body=metadata, media_body=media, fields="id").execute()
            print(f"  → {filename}")
            uploaded += 1
        except Exception as e:
            print(f"  → {filename} アップロード失敗: {e}")

    if uploaded:
        print(f"  Drive保存完了: {uploaded}枚")


def run(theme: str, menu: str, post_datetime: str, notes: str = "", content_file: str = None):
    # 過去のInstagram投稿を取得（コンテンツファイル指定時も背景画像選択に使用）
    print("過去のInstagram投稿を取得中...")
    past_posts = fetch_instagram_posts(limit=30)

    # 過去画像URLを一覧化（背景選択参考 + ダウンロード用）
    available_images = collect_available_images(past_posts) if past_posts else []
    if available_images:
        print(f"  利用可能な過去画像: {len(available_images)}枚")

    # 参考画像（「施術・メニュー紹介」フォルダの「参考N」）を取得
    print("参考画像を確認中...")
    reference_images = list_reference_images()

    if content_file:
        # Claude Codeが生成したコンテンツを読み込む（Groq呼び出しスキップ）
        print(f"コンテンツファイルを読み込みます: {content_file}")
        with open(content_file, "r", encoding="utf-8") as f:
            result = json.load(f)
    else:
        # Groqでコンテンツ生成（GitHub Actions等の自動化・旧来の動作）
        result = generate_content(theme, menu, notes, past_posts, available_images,
                                  reference_images=reference_images)

    num_slides = len(result["slides"])
    print(f"\n生成完了！スライド数: {num_slides}枚")
    print(f"メモ: {result['memo']}")

    # 各スライドの背景をbg_strategyに従って解決
    # 共通 bg_prompt は generate に落ちうるスライドがある時だけ使われる。
    # 全スライドが Drive の reuse/edit（＝直近の実運用はほぼ全件これ）なら
    # 一度も参照されないので、その1フィールドで投稿作成を止めない。
    # 実際に使う時は resolve_backgrounds() が生成直前に validate_bg_prompt() へ通す。
    bg_prompt = result.get("bg_prompt")
    if any(_may_fall_back_to_generate(s) and not s.get("bg_prompt") for s in result["slides"]):
        bg_prompt = validate_bg_prompt(bg_prompt)
    global_seed = result.get("seed")
    last_seed = resolve_backgrounds(result["slides"], available_images, bg_prompt,
                                    global_seed=global_seed)
    if last_seed:
        print(f"最終seed: {last_seed}（cleanup_backgrounds.py --seed 用）")

    # 新規生成した背景画像をDriveテーマフォルダに保存
    drive_theme = result.get("drive_theme") or _menu_to_theme(menu)
    _upload_backgrounds_to_drive(result["slides"], drive_theme)

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

    # content.jsonに _generated_dir を記録（同じcontent.jsonを別日時で再利用した際の混同防止）
    if content_file and os.path.exists(content_file):
        try:
            with open(content_file, "r", encoding="utf-8") as f:
                stored = json.load(f)
            dt = datetime.strptime(post_datetime, "%Y/%m/%d %H:%M")
            stored["_generated_dir"] = dt.strftime("%Y-%m-%d-%H%M")
            with open(content_file, "w", encoding="utf-8") as f:
                json.dump(stored, f, ensure_ascii=False, indent=2)
            print(f"content.json に _generated_dir={stored['_generated_dir']} を記録しました")
        except Exception as e:
            print(f"content.json の _generated_dir 記録スキップ: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Instagram投稿コンテンツを生成・登録する")
    parser.add_argument("--content-file", help="Claude Codeが生成したcontent.jsonのパス（指定時はGroq生成をスキップ）")
    parser.add_argument("--theme", default="休みの日に一人でエステに行くことへの背中押し。疲れた体のリセット・リフレッシュ、首・肩・背中の凝りを解消し巡りを良くしてQOL向上", help="投稿テーマ")
    parser.add_argument("--menu", default="ご褒美エステ", help="メニュー種別（例: ご褒美エステ / ブライダルエステ / アラサー美容）")
    parser.add_argument("--post-datetime", default="2026/04/12 21:00", help="投稿日時（例: 2026/04/14 21:00）")
    parser.add_argument("--notes", default="", help="追加指示")
    args = parser.parse_args()

    run(
        theme=args.theme,
        menu=args.menu,
        post_datetime=args.post_datetime,
        notes=args.notes,
        content_file=args.content_file,
    )
