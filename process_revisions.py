"""
修正依頼自動処理スクリプト
スプレッドシートで「修正依頼」ステータスの行を検出し、
Groq APIを使って自動修正を行い、完了したらLINE通知を送る。
GitHub Actionsで定期実行される。
"""
import glob
import json
import os
import traceback

from groq import Groq
from load_env import load_from_zshrc
load_from_zshrc()

from check_revisions import check_and_report, mark_as_revised
from create_post import (
    fetch_instagram_posts,
    collect_available_images,
    resolve_backgrounds,
    SYSTEM_PROMPT,
    BRIDAL_ADDON,
)
from generate_carousel import generate_with_slides
from register_post import generate_preview_html, upload_html_to_github, upload_to_github
from line_notify import notify_revision_done

GENERATED_DIR = "generated"


IMAGE_KEYWORDS = ["背景", "画像", "スライド", "枚", "表紙", "構図", "bg_prompt", "generate", "reuse", "edit"]


def is_text_only_revision(instruction: str) -> bool:
    """修正指示が文章・キャプション・ハッシュタグのみか判定"""
    return not any(kw in instruction for kw in IMAGE_KEYWORDS)


def revise_text_only_with_groq(item: dict) -> dict:
    """テキストのみ修正：Groqにcaption/hashtagsだけを返させる"""
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    past_posts = fetch_instagram_posts(limit=30)
    system = SYSTEM_PROMPT

    if past_posts:
        top_captions = [
            p["caption"] for p in past_posts[:10]
            if p.get("caption") and len(p["caption"]) > 100
        ][:3]
        if top_captions:
            captions_text = "\n\n---\n\n".join(top_captions)
            system += f"""
## MIKIの実際の過去投稿（文体・言い回し・テンポの参考）
{captions_text}
"""

    user_message = f"""以下の投稿のキャプションとハッシュタグを修正指示に従って修正してください。

【現在のキャプション】
{item['caption']}

【現在のハッシュタグ】
{item['hashtags']}

【修正指示】
{item['instruction']}

以下のJSON形式のみで返してください（他のフィールドは不要）：
{{"caption": "修正後のキャプション", "hashtags": "修正後のハッシュタグ"}}
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
        max_tokens=2048,
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def revise_with_groq(item: dict) -> dict:
    """Groq APIを使って修正内容を生成（create_post.pyと同じルールで）"""
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    # create_post.pyと同じSYSTEM_PROMPTをベースに使用
    system = SYSTEM_PROMPT

    # ブライダル系の場合はBRIDAL_ADDONを追加
    menu_type = item.get("menu_type", "")
    if "ブライダル" in menu_type or "花嫁" in item.get("caption", "")[:50]:
        system += BRIDAL_ADDON

    # 過去の高反応投稿キャプションを文体参考として追加
    past_posts = fetch_instagram_posts(limit=30)
    available_images = collect_available_images(past_posts) if past_posts else []

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

{img_list}

各スライドのbg_strategyを "reuse"（転用）"edit"（PIL加工転用）"generate"（新規生成）で指定し、
"reuse"/"edit"の場合はreuse_indexで上記の番号を指定してください。
"""
    else:
        system += "\n## 注意\n過去投稿画像は取得できませんでした。全スライドbg_strategy=\"generate\"にしてください。\n"

    user_message = f"""以下の投稿内容を修正指示に従って修正してください。

【現在のキャプション】
{item['caption']}

【現在のハッシュタグ】
{item['hashtags']}

【修正指示】
{item['instruction']}

修正後はSYSTEM_PROMPTのJSON形式（slides/caption/hashtags/memo/bg_prompt）で返してください。
修正が不要なフィールドは現在の値をそのまま維持してください。
"""

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
    result = json.loads(raw)
    return result, available_images


def process_revision(sheet, item: dict):
    """1件の修正依頼を処理"""
    row_num = item["row_num"]

    if is_text_only_revision(item["instruction"]):
        print(f"行{row_num}: テキストのみ修正（画像再生成なし）...")
        result = revise_text_only_with_groq(item)
        new_caption = result.get("caption", item["caption"])
        new_hashtags = result.get("hashtags", item["hashtags"])
        filenames = [f.strip() for f in item["files"].split(",")]
    else:
        print(f"行{row_num}: Groq APIで修正中（画像再生成あり）...")
        result, available_images = revise_with_groq(item)
        new_caption = result["new_caption"] if "new_caption" in result else result.get("caption", item["caption"])
        new_hashtags = result["new_hashtags"] if "new_hashtags" in result else result.get("hashtags", item["hashtags"])

        if result.get("slides"):
            print(f"行{row_num}: 背景画像を準備中...")
            bg_prompt = result.get("bg_prompt", "Japanese esthetic salon, soft pink, elegant, luxury spa")
            original_seed = item.get("seed")
            resolve_backgrounds(result["slides"], available_images, bg_prompt,
                                global_seed=original_seed)

            result["slides"].append({"filename": "slide8.jpg", "type": "raw"})
            result["slides"].append({"filename": "slide7.jpg", "type": "raw"})

            print(f"行{row_num}: 画像を再生成中...")
            generate_with_slides(result["slides"])

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
    # ローカル環境ではスキップ（Claude Codeで処理するため）
    # GitHub Actions実行時のみ自動処理する
    if not os.getenv("GITHUB_ACTIONS"):
        print("ローカル環境のためスキップ。修正依頼はClaude Codeで処理してください。")
        return

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
            traceback.print_exc()


if __name__ == "__main__":
    run()
