"""
修正依頼自動処理スクリプト
スプレッドシートで「修正依頼」ステータスの行を検出し、
Gemini APIを使って自動修正を行い、完了したらLINE通知を送る。
GitHub Actionsで定期実行される。
"""
import glob
import json
import os

from groq import Groq

from check_revisions import check_and_report, mark_as_revised
from generate_carousel import generate_with_slides, SLIDES as DEFAULT_SLIDES
from register_post import generate_preview_html, upload_html_to_github, upload_to_github
from line_notify import notify_revision_done

GENERATED_DIR = "generated"


def revise_with_groq(item: dict) -> dict:
    """Groq APIを使って修正内容を生成"""
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    prompt = f"""あなたはエステサロン「AMRTA六本木」のInstagram投稿の修正担当です。
以下の修正指示に従って、投稿内容を修正してください。

【現在のキャプション】
{item['caption']}

【現在のハッシュタグ】
{item['hashtags']}

【現在のカルーセルスライド構成（JSON）】
{json.dumps(DEFAULT_SLIDES, ensure_ascii=False, indent=2)}

【修正指示】
{item['instruction']}

以下のJSON形式だけで回答してください（余分なテキスト不要）：
{{
    "new_caption": "修正後のキャプション",
    "new_hashtags": "修正後のハッシュタグ",
    "revise_images": true,
    "new_slides": []
}}

注意：
- revise_imagesは、スライド画像のテキスト内容を変更する場合のみtrueにしてください
- revise_imagesがfalseの場合、new_slidesは空配列でOKです
- new_slidesはrevise_imagesがtrueの場合のみ、修正後のSLIDES配列全体を入れてください
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def process_revision(sheet, item: dict):
    """1件の修正依頼を処理"""
    row_num = item["row_num"]
    print(f"行{row_num}: Claude APIで修正中...")

    result = revise_with_groq(item)

    new_caption = result["new_caption"]
    new_hashtags = result["new_hashtags"]

    if result.get("revise_images") and result.get("new_slides"):
        print(f"行{row_num}: 画像を再生成中...")
        generate_with_slides(result["new_slides"])

        files = sorted(glob.glob(os.path.join(GENERATED_DIR, "carousel_*.jpg")))
        print(f"行{row_num}: {len(files)}枚をGitHubにアップロード中...")
        filenames = [upload_to_github(f) for f in files]
    else:
        filenames = [f.strip() for f in item["files"].split(",")]

    print(f"行{row_num}: プレビューを更新中...")
    html = generate_preview_html(filenames, new_caption, new_hashtags, item["datetime"])
    preview_url = upload_html_to_github(html, item["datetime"])

    mark_as_revised(sheet, row_num, new_caption, new_hashtags, preview_url)
    notify_revision_done(row_num, item["menu_type"], item["instruction"], preview_url)
    print(f"行{row_num}: 修正完了 → {preview_url}")


def run():
    sheet, pending = check_and_report()

    if not pending:
        print("修正依頼はありません")
        return

    print(f"{len(pending)}件の修正依頼を処理します")

    for item in pending:
        try:
            process_revision(sheet, item)
        except Exception as e:
            print(f"行{item['row_num']}: 修正失敗 → {e}")


if __name__ == "__main__":
    run()
