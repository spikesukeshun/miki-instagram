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
from line_notify import notify_revision_done, notify_revision_found, send_line_message

GENERATED_DIR = "generated"
CONTENT_JSON_PATH = "content.json"

# 背景画像の変更を明示的に指示するキーワード（誤検知防止のため具体的な表現のみ）
IMAGE_KEYWORDS = ["背景画像", "背景を変", "背景を差し替", "画像を変", "写真を変", "表紙を変", "構図", "bg_prompt"]

# スライド内テキストの修正を指示するキーワード
SLIDE_TEXT_KEYWORDS = ["スライド", "枚目", "タイトル", "本文", "items", "リスト", "箇条書き"]


def load_content_json():
    """content.jsonが存在すればロードして返す（Claude Codeの最新修正版）"""
    if os.path.exists(CONTENT_JSON_PATH):
        with open(CONTENT_JSON_PATH, encoding="utf-8") as f:
            return json.load(f)
    return None


def is_image_revision(instruction: str) -> bool:
    """修正指示が背景画像の変更を含むか判定"""
    return any(kw in instruction for kw in IMAGE_KEYWORDS)


def is_slide_text_revision(instruction: str) -> bool:
    """修正指示がスライド内テキストの変更を含むか判定"""
    return any(kw in instruction for kw in SLIDE_TEXT_KEYWORDS)


def is_text_only_revision(instruction: str) -> bool:
    """修正指示が文章・キャプション・ハッシュタグのみか判定（画像変更を含まない）"""
    return not is_image_revision(instruction)


def revise_text_only_with_groq(item: dict) -> dict:
    """テキストのみ修正：Groqにcaption/hashtagsだけを返させる"""
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    past_posts = fetch_instagram_posts(limit=10)
    system = SYSTEM_PROMPT

    if past_posts:
        top_captions = [
            p["caption"][:400] for p in past_posts[:5]
            if p.get("caption") and len(p["caption"]) > 100
        ][:1]
        if top_captions:
            system += f"""
## MIKIの実際の過去投稿（文体参考・抜粋）
{top_captions[0]}
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
        max_tokens=4096,
    )
    import re
    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw).strip()
    return json.loads(raw)


def revise_slide_text_only_with_groq(item: dict) -> dict:
    """スライドテキストのみ修正：bg_strategy等の背景指定は一切変更しない"""
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    slides_json = json.dumps(item.get("slides", []), ensure_ascii=False, indent=2)

    system = """あなたはInstagram投稿スライドのテキスト修正アシスタントです。
以下のルールを厳守してください：
- title / text / body / items / footer フィールドのみ修正する
- bg_strategy / reuse_source / reuse_theme / reuse_filename / filename / type は絶対に変更しない
- スライドの枚数・順序は変更しない
- 修正不要なスライドはそのまま維持する

返答はJSON形式のみ：{"slides": [...修正後のスライド配列...]}
"""

    user_message = f"""以下のスライド構成のテキストを修正指示に従って修正してください。

【現在のスライド構成】
{slides_json}

【修正指示】
{item['instruction']}

bg_strategy / reuse_source / reuse_theme / reuse_filename は絶対に変更しないでください。
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
        max_tokens=4096,
    )
    import re
    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw).strip()
    result = json.loads(raw)

    # 安全策: bg設定が変更されていたら元の値に戻す
    original_slides = item.get("slides", [])
    new_slides = result.get("slides", [])
    for orig, new in zip(original_slides, new_slides):
        for key in ["bg_strategy", "reuse_source", "reuse_theme", "reuse_filename", "filename", "type"]:
            if key in orig:
                new[key] = orig[key]

    return result


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
    past_posts = fetch_instagram_posts(limit=10)
    available_images = collect_available_images(past_posts) if past_posts else []

    if past_posts:
        top_captions = [
            p["caption"][:400] for p in past_posts[:5]
            if p.get("caption") and len(p["caption"]) > 100
        ][:1]
        if top_captions:
            system += f"""
## MIKIの実際の過去投稿（文体参考・抜粋）
{top_captions[0]}
"""

    # 利用可能な過去投稿画像の一覧をGroqに渡す
    if available_images:
        img_list = "\n".join([
            f"- index {i}: いいね{img['like_count']}件, 内容「{img['caption_snippet']}」"
            for i, img in enumerate(available_images[:8])
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

    # Google Driveの画像一覧をGroqに渡す
    try:
        from drive_manager import collect_drive_images_all
        drive_images = collect_drive_images_all()
        drive_lines = []
        for theme, files in drive_images.items():
            if files:
                names = ", ".join(f["name"] for f in files[:20])
                drive_lines.append(f"- {theme}: {names}")
        if drive_lines:
            system += f"""
## Google Driveの利用可能な画像（ファイル名指定用）
修正指示で特定の画像名が指定された場合は、以下のファイル名を使用してください。

{chr(10).join(drive_lines)}

Drive画像を使う場合は各スライドに以下を指定してください：
  "bg_strategy": "reuse" または "edit"
  "reuse_source": "drive"
  "reuse_theme": テーマ名（bridal/reward/menu/lifestyle）
  "reuse_filename": 上記のファイル名
"""
    except Exception as e:
        print(f"  Drive画像リスト取得スキップ: {e}")

    current_slides_json = ""
    if item.get("slides"):
        current_slides_json = f"""
【現在のスライド構成（Claude Codeによる最新版）】
{json.dumps(item["slides"], ensure_ascii=False, indent=2)}

"""

    user_message = f"""以下の投稿内容を修正指示に従って修正してください。
{current_slides_json}
【現在のキャプション（Claude Codeによる最新版）】
{item['caption']}

【現在のハッシュタグ】
{item['hashtags']}

【修正指示】
{item['instruction']}

修正後はSYSTEM_PROMPTのJSON形式（slides/caption/hashtags/memo/bg_prompt）で返してください。
修正が不要なフィールドは現在の値をそのまま維持してください。
スライド構成が提示されている場合は、それを基に修正してください（ゼロから作り直さないこと）。
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
        max_tokens=6000,
    )
    import re
    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw).strip()
    result = json.loads(raw)

    # 安全策: Groq出力でbg設定が変更されていたら元のスライドの値に戻す
    if item.get("slides") and result.get("slides"):
        original_slides = item["slides"]
        new_slides = result["slides"]
        for orig, new in zip(original_slides, new_slides):
            for key in ["bg_strategy", "reuse_source", "reuse_theme", "reuse_filename"]:
                if key in orig:
                    new[key] = orig[key]

    return result, available_images


def process_revision(sheet, item: dict):
    """1件の修正依頼を処理"""
    row_num = item["row_num"]

    # content.jsonが存在する場合、スライド構成のみ引き継ぐ
    # caption/hashtagsはスプレッドシートの値（各投稿の正確な内容）を優先する
    # content.jsonのcaptionを使うと、別投稿のcaptionで上書きされるバグが起きるため
    content = load_content_json()
    if content and content.get("slides"):
        # ファイルパスの投稿日時とcontent.jsonの投稿日時が一致する場合のみslides適用
        # 一致チェック: item["files"]の先頭にある日付フォルダ vs content.jsonの先頭スライドのbg_strategy
        item_prefix = item["files"].split("/")[0] if "/" in item["files"] else ""
        content_prefix = content.get("_generated_dir", "")
        if content_prefix and item_prefix != content_prefix:
            print(f"行{row_num}: content.json（{content_prefix}）は別投稿のため無視 → スプレッドシートの内容を使用")
        else:
            print(f"行{row_num}: content.jsonを検出 → スライド構成をClaude Code最新版に更新")
            item["slides"] = content.get("slides", [])
    else:
        print(f"行{row_num}: content.jsonなし → スプレッドシートの内容を使用")

    if is_text_only_revision(item["instruction"]) and not is_slide_text_revision(item["instruction"]):
        # フロー1: キャプション・ハッシュタグのみ修正（画像もスライドも変更しない）
        print(f"行{row_num}: テキストのみ修正（画像再生成なし）...")
        result = revise_text_only_with_groq(item)
        new_caption = result.get("caption", item["caption"])
        new_hashtags = result.get("hashtags", item["hashtags"])
        filenames = [f.strip() for f in item["files"].split(",")]
    elif is_slide_text_revision(item["instruction"]) and not is_image_revision(item["instruction"]):
        # フロー2: スライド文章のみ修正（背景画像は変更しない・再生成のみ）
        print(f"行{row_num}: スライドテキストのみ修正（背景指定を維持したまま再生成）...")
        if item.get("slides"):
            result = revise_slide_text_only_with_groq(item)
            new_caption = result.get("caption", item["caption"])
            new_hashtags = result.get("hashtags", item["hashtags"])

            slides = result.get("slides", item["slides"])
            slides.append({"filename": "slide8.jpg", "type": "raw"})
            slides.append({"filename": "slide7.jpg", "type": "raw"})

            print(f"行{row_num}: 既存の背景指定で画像を再生成中...")
            generate_with_slides(slides)

            files = sorted(glob.glob(os.path.join(GENERATED_DIR, "carousel_*.jpg")))
            print(f"行{row_num}: {len(files)}枚をGitHubにアップロード中...")
            filenames = [upload_to_github(f) for f in files]
        else:
            # slides情報がない場合はキャプションのみ修正にフォールバック
            print(f"行{row_num}: スライド情報なし → キャプションのみ修正にフォールバック")
            result = revise_text_only_with_groq(item)
            new_caption = result.get("caption", item["caption"])
            new_hashtags = result.get("hashtags", item["hashtags"])
            filenames = [f.strip() for f in item["files"].split(",")]
    else:
        # フロー3: 背景画像を含む全体修正（画像再生成あり）
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

    try:
        sheet, pending = check_and_report()
    except Exception as e:
        send_line_message(f"❌ 修正依頼チェック失敗\nスプレッドシート読み込みエラー:\n{str(e)[:200]}")
        raise

    if not pending:
        print("修正依頼はありません")
        return

    print(f"{len(pending)}件の修正依頼を処理します")

    for item in pending:
        notify_revision_found(item["row_num"], item["menu_type"], item["instruction"])
        try:
            process_revision(sheet, item)
        except Exception as e:
            print(f"行{item['row_num']}: 修正失敗 → {e}")
            traceback.print_exc()
            send_line_message(
                f"❌ 修正依頼の処理に失敗しました\n"
                f"\n"
                f"📋 {item['menu_type']}（{item['row_num']}行目）\n"
                f"エラー: {str(e)[:200]}"
            )


if __name__ == "__main__":
    run()
