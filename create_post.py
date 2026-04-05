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

SYSTEM_PROMPT = """あなたはエステサロン「AMRTA六本木」のInstagram投稿コンテンツ担当です。
テーマを受け取り、カルーセル投稿のスライド内容・キャプション・ハッシュタグを生成してください。

## MIKIについて
- サロン名: AMRTA六本木 / Instagram: @estmiki
- エステティシャン・リラクゼーションサロンオーナー
- 専門: ブライダルエステ・ご褒美エステ
- 自身も花嫁経験あり（その経験が原点）
- 名前の表記はMIKI（大文字）

## ブランドメッセージ
- 技術だけでなく花嫁様の不安・迷いに寄り添う「一番の理解者」でありたい
- 土台となる肌・体・メンタルを整えることが全ての美しさの根幹
- 丁寧・温かみがある・押し付けがましくない文体
- CTAは「MIKI指名 初回限定20%OFF」「DMからご相談」

## ターゲット
- 20代後半〜40代の女性
- バリキャリ・正社員・平日休み（美容・ホテル・アパレル・飲食業界など）
- 美容好き・素直・ダイエットに成功したことがない

## 投稿スタイル
- MIKIの個人的なストーリー・自分語り系が最も反応が良い（いいね451件実績）
- キャプションの冒頭は「MIKIです。」で始める
- キャプション末尾に必ずCTAを入れる
- キャプションは必ずテーマに即した内容で書く（テンプレートをそのまま使わない）

## カルーセルスライドのルール
- スライド数: 6〜7枚（最後のプロフィールスライドは自動追加するので含めない）
- filenameは "bg01.jpg" "bg02.jpg" ... と連番で指定する
- スライドタイプと必須フィールド:

cover（表紙）:
  {"filename": "bg01.jpg", "type": "cover", "title": "タイトル（改行は\\nで）", "tag": "- サブタイトル -"}

text（テキスト）:
  {"filename": "bg02.jpg", "type": "text", "title": "セクションタイトル", "text": "本文（改行は\\nで）"}

list（リスト）:
  {"filename": "bg03.jpg", "type": "list", "title": "タイトル", "items": ["項目1", "項目2", ...], "footer": "締めの一言（省略可）"}

cta（コールトゥアクション）:
  {"filename": "bgN.jpg", "type": "cta", "title": "MIKI指名  初回限定20%OFF", "body": "本文（改行は\\nで）", "subtitle": "ご予約・ご相談はDMからお気軽にどうぞ"}

## ハッシュタグ候補
ブライダルエステ系: #ブライダルエステ #ブライダルエステ東京 #ブライダルエステ体験 #プレ花嫁2026 #大人花嫁 #東京花嫁 #六本木エステ
ご褒美エステ系: #ご褒美エステ #ご褒美時間 #自分へのご褒美 #大人の女性 #六本木エステ #リラクゼーション
アラサー・アラフォー系: #アラサー美容 #アラフォー美容 #大人の肌ケア #30代美容 #40代美容 #六本木エステ
サロン紹介系: #六本木エステ #六本木サロン #AMRTA #エステ体験 #プライベートサロン

## 出力形式
必ずJSONのみを返してください。説明文は不要です。

{
  "slides": [...],
  "caption": "キャプション全文（テーマに即した内容）",
  "hashtags": "#タグ1 #タグ2 ...",
  "memo": "このコンテンツの一言メモ",
  "bg_prompt": "背景画像生成用の英語プロンプト（例: Japanese esthetic salon, soft pink, elegant woman relaxing, luxury spa）"
}
"""

# 既存の背景ファイルの特徴（使い回し提案用）
EXISTING_BG_FEATURES = {
    "slide1.jpg": "ウェディング・花嫁系（指輪・ブーケ）",
    "slide2.jpg": "エステ・スパ系（背中・白い室内）",
    "slide3.jpg": "花嫁・ドレス・座り姿",
    "slide4.jpg": "花嫁・スタッフ・笑顔・2人",
    "slide5.jpg": "花・ピンク・柔らかい雰囲気",
    "slide6.jpg": "エステ・施術・ゴールド",
    "slide8.jpg": "シンプル・白・エレガント",
}


def suggest_reusable_backgrounds(menu: str, theme: str) -> None:
    """テーマに合わせて使い回せる既存背景を提案"""
    print("\n💡 使い回せる可能性がある既存背景:")
    if "ご褒美" in menu or "リラク" in menu or "首" in theme or "疲れ" in theme:
        print("  slide2.jpg（エステ・スパ系）, slide6.jpg（エステ・施術系）")
    elif "ブライダル" in menu or "花嫁" in theme:
        print("  slide1.jpg（ウェディング系）, slide3.jpg（花嫁・ドレス系）")
    else:
        print("  slide5.jpg（ピンク・柔らか）, slide8.jpg（シンプル・白）")
    print("  → 次回は --reuse-bg フラグで指定すると背景生成をスキップできます（将来対応予定）")


def generate_backgrounds(bg_prompt: str, num_slides: int) -> list:
    """Pollinations.aiでテーマ別背景画像を生成してbackgrounds/に保存"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filenames = []

    # 英語プロンプトに共通スタイルを付加
    full_prompt = f"{bg_prompt}, soft light, elegant, minimal background, no text, no watermark, photography"
    encoded = urllib.parse.quote(full_prompt)

    print(f"\nテーマ別背景画像を生成中（Pollinations.ai）...")
    for i in range(num_slides):
        seed = random.randint(1000, 99999)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1350&nologo=true&seed={seed}"
        filename = f"custom_{timestamp}_{i+1:02d}.jpg"
        path = os.path.join("backgrounds", filename)

        print(f"  背景 {i+1}/{num_slides} を生成中...")
        try:
            res = requests.get(url, timeout=120)
            if res.status_code == 200 and len(res.content) > 10000:
                with open(path, "wb") as f:
                    f.write(res.content)
                filenames.append(filename)
                print(f"  保存: {filename}")
            else:
                raise Exception(f"レスポンス不正: {res.status_code}, size={len(res.content)}")
        except Exception as e:
            # 失敗時は既存背景をフォールバック
            fallback = f"slide{(i % 6) + 1}.jpg"
            filenames.append(fallback)
            print(f"  生成失敗 → フォールバック: {fallback} ({e})")

    return filenames


def generate_content(theme: str, menu: str, notes: str = "") -> dict:
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    user_message = f"テーマ: {theme}\nメニュー種別: {menu}"
    if notes:
        user_message += f"\n追加指示: {notes}"

    print("Groq APIでコンテンツを生成中...")
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
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
    # コンテンツ生成
    result = generate_content(theme, menu, notes)

    print(f"\n生成完了！スライド数: {len(result['slides'])}枚")
    print(f"メモ: {result['memo']}")

    # 使い回せる背景を提案
    suggest_reusable_backgrounds(menu, theme)

    # テーマ別背景画像を生成
    bg_prompt = result.get("bg_prompt", "Japanese esthetic salon, soft pink, elegant, luxury spa")
    bg_files = generate_backgrounds(bg_prompt, len(result["slides"]))

    # スライドに生成した背景ファイルを割り当て
    for i, slide in enumerate(result["slides"]):
        slide["filename"] = bg_files[i]

    # slide7.jpg（MIKIプロフィール）を最後に自動追加
    result["slides"].append({"filename": "slide7.jpg", "type": "raw"})

    print(f"\n最終スライド数: {len(result['slides'])}枚（最後はMIKIプロフィール固定）")

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
