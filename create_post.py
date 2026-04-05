import json
import os

import anthropic
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
- 「花嫁様」という表記を使う（「花嫁さん」ではなく）
- CTAは「MIKI指名 初回限定20%OFF」「DMからご相談」

## ターゲット
- 20代後半〜40代の女性
- バリキャリ・正社員・平日休み（美容・ホテル・アパレル・飲食業界など）
- 美容好き・素直・ダイエットに成功したことがない

## 投稿スタイル
- MIKIの個人的なストーリー・自分語り系が最も反応が良い（いいね451件実績）
- キャプションの冒頭は「MIKIです。」で始める
- キャプション末尾に必ずCTAを入れる

## カルーセルスライドのルール
- スライド数: 6〜8枚
- 利用可能な背景ファイル: slide1.jpg〜slide8.jpg（使う枚数分を順番に割り当てる）
- スライドタイプと必須フィールド:

cover（表紙）:
  {"filename": "slide1.jpg", "type": "cover", "title": "タイトル（改行は\\nで）", "tag": "- サブタイトル -"}

text（テキスト）:
  {"filename": "slide2.jpg", "type": "text", "title": "セクションタイトル", "text": "本文（改行は\\nで）"}

list（リスト）:
  {"filename": "slide3.jpg", "type": "list", "title": "タイトル", "items": ["項目1", "項目2", ...], "footer": "締めの一言（省略可）"}

cta（コールトゥアクション）:
  {"filename": "slideN.jpg", "type": "cta", "title": "MIKI指名  初回限定20%OFF", "body": "本文（改行は\\nで）", "subtitle": "ご予約・ご相談はDMからお気軽にどうぞ"}

raw（画像のみ・テキストなし）:
  {"filename": "slideN.jpg", "type": "raw"}

## ハッシュタグ候補
ブライダルエステ系: #ブライダルエステ #ブライダルエステ東京 #ブライダルエステ体験 #プレ花嫁2026 #大人花嫁 #東京花嫁 #六本木エステ
ご褒美エステ系: #ご褒美エステ #ご褒美時間 #自分へのご褒美 #大人の女性 #六本木エステ #リラクゼーション
アラサー・アラフォー系: #アラサー美容 #アラフォー美容 #大人の肌ケア #30代美容 #40代美容 #六本木エステ
サロン紹介系: #六本木エステ #六本木サロン #AMRTA #エステ体験 #プライベートサロン

## 出力形式
必ずJSONのみを返してください。説明文は不要です。

{
  "slides": [...],
  "caption": "キャプション全文",
  "hashtags": "#タグ1 #タグ2 ...",
  "memo": "このコンテンツの一言メモ"
}
"""


def generate_content(theme: str, menu: str, notes: str = "") -> dict:
    client = anthropic.Anthropic()

    user_message = f"テーマ: {theme}\nメニュー種別: {menu}"
    if notes:
        user_message += f"\n追加指示: {notes}"

    print("Claude APIでコンテンツを生成中...")
    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = message.content[0].text.strip()
    # コードブロックで囲まれている場合は除去
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
        theme="ここにテーマを書く",
        menu="ご褒美エステ",  # ブライダルエステ / ご褒美エステ / サロン紹介 など
        post_datetime="2026/04/09 21:00",
        notes="",  # 追加の方向性（省略OK）
    )
