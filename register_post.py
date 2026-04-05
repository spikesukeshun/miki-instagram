import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
import os
import glob
import base64
import requests
from datetime import datetime

load_dotenv()

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER = "spikesukeshun"
GITHUB_REPO = "miki-instagram"
GENERATED_DIR = "generated"
GITHUB_PAGES_URL = f"https://{GITHUB_OWNER}.github.io/{GITHUB_REPO}"
RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/main"


def get_sheet():
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).sheet1


def _github_headers():
    return {"Authorization": f"token {GITHUB_TOKEN}"}


def upload_to_github(filepath: str) -> str:
    """ファイルをGitHubリポジトリにアップロードしてファイル名を返す"""
    filename = os.path.basename(filepath)
    with open(filepath, "rb") as f:
        content = base64.b64encode(f.read()).decode()

    api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GENERATED_DIR}/{filename}"
    headers = _github_headers()

    res = requests.get(api_url, headers=headers)
    sha = res.json().get("sha") if res.status_code == 200 else None

    payload = {"message": f"画像追加: {filename}", "content": content}
    if sha:
        payload["sha"] = sha

    res = requests.put(api_url, headers=headers, json=payload)
    if res.status_code not in (200, 201):
        raise Exception(f"GitHubアップロード失敗: {res.json()}")

    print(f"  アップロード完了: {filename}")
    return filename


def setup_github_pages():
    """GitHub Pagesを有効化する（初回のみ、以降はスキップ）"""
    api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/pages"
    headers = {**_github_headers(), "Accept": "application/vnd.github+json"}

    res = requests.get(api_url, headers=headers)
    if res.status_code == 200:
        return  # 既に有効化済み

    payload = {"source": {"branch": "main", "path": "/docs"}}
    res = requests.post(api_url, headers=headers, json=payload)
    if res.status_code == 201:
        print("  GitHub Pagesを有効化しました")
    elif res.status_code == 409:
        pass  # 既に有効化済み
    else:
        print(f"  GitHub Pages設定スキップ: {res.status_code}")


def generate_preview_html(filenames: list, caption: str, hashtags: str, post_datetime: str) -> str:
    """スマホで見やすいプレビューHTMLを生成して文字列で返す"""
    generated_at = datetime.now().strftime("%Y/%m/%d %H:%M")

    images_html = ""
    for i, filename in enumerate(filenames, 1):
        img_url = f"{RAW_BASE}/{GENERATED_DIR}/{filename}?t={datetime.now().strftime('%Y%m%d%H%M')}"
        images_html += f"""
        <div class="image-card">
            <div class="image-num">{i} / {len(filenames)}</div>
            <img src="{img_url}" alt="スライド{i}" loading="lazy">
        </div>"""

    # キャプションの改行をHTMLに変換
    caption_html = caption.replace("\n", "<br>")
    hashtags_html = hashtags.replace(" ", "&nbsp;")

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Cache-Control" content="no-cache">
    <title>投稿プレビュー - MIKI</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: #FFF9F5;
            font-family: 'Hiragino Sans', 'Hiragino Kaku Gothic ProN', sans-serif;
            color: #3D1F2D;
            max-width: 480px;
            margin: 0 auto;
            padding-bottom: 40px;
        }}
        .header {{
            background: linear-gradient(135deg, #E8A0B4, #C9A96E);
            color: white;
            padding: 24px 20px 20px;
            text-align: center;
        }}
        .header h1 {{ font-size: 20px; margin-bottom: 6px; }}
        .header .meta {{ font-size: 13px; opacity: 0.9; }}
        .section-title {{
            font-size: 13px;
            color: #C9A96E;
            font-weight: bold;
            letter-spacing: 0.1em;
            padding: 20px 16px 8px;
            border-bottom: 1px solid #F0D9E0;
            margin-bottom: 0;
        }}
        .image-card {{
            position: relative;
            margin: 12px 16px;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 2px 12px rgba(200,120,130,0.15);
        }}
        .image-card img {{
            width: 100%;
            display: block;
        }}
        .image-num {{
            position: absolute;
            top: 10px;
            right: 10px;
            background: rgba(0,0,0,0.45);
            color: white;
            font-size: 12px;
            padding: 3px 10px;
            border-radius: 20px;
        }}
        .caption-box {{
            margin: 4px 16px 0;
            background: white;
            border-radius: 12px;
            padding: 16px;
            font-size: 14px;
            line-height: 1.8;
            box-shadow: 0 1px 6px rgba(200,120,130,0.1);
        }}
        .hashtags {{
            margin: 8px 16px 0;
            background: white;
            border-radius: 12px;
            padding: 12px 16px;
            font-size: 13px;
            color: #5B8FCA;
            line-height: 1.7;
            box-shadow: 0 1px 6px rgba(200,120,130,0.1);
        }}
        .approve-box {{
            margin: 20px 16px 0;
            background: linear-gradient(135deg, #FFF0F5, #FFF8EC);
            border: 1.5px solid #E8A0B4;
            border-radius: 12px;
            padding: 16px;
            text-align: center;
        }}
        .approve-box p {{ font-size: 13px; line-height: 1.7; color: #3D1F2D; }}
        .approve-box .step {{
            font-size: 14px;
            font-weight: bold;
            color: #C9607A;
            margin-top: 10px;
        }}
        .footer {{
            text-align: center;
            font-size: 11px;
            color: #B0969F;
            margin-top: 24px;
            padding: 0 16px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📸 投稿プレビュー</h1>
        <div class="meta">投稿予定: {post_datetime}　|　全{len(filenames)}枚</div>
    </div>

    <div class="section-title">▼ 画像確認</div>
    {images_html}

    <div class="section-title">▼ キャプション</div>
    <div class="caption-box">{caption_html}</div>

    <div class="section-title">▼ ハッシュタグ</div>
    <div class="hashtags">{hashtags_html}</div>

    <div class="approve-box">
        <p>内容を確認したら<br>スプレッドシートで承認してください</p>
        <div class="step">ステータス欄を「承認済み」に変更 →　GO！</div>
    </div>

    <div class="footer">
        <p>プレビュー生成日時: {generated_at}</p>
    </div>
</body>
</html>"""


def upload_html_to_github(html_content: str) -> str:
    """HTMLをdocs/index.htmlとしてGitHubにアップロードしてGitHub Pages URLを返す"""
    content_b64 = base64.b64encode(html_content.encode("utf-8")).decode()

    api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/docs/index.html"
    headers = _github_headers()

    res = requests.get(api_url, headers=headers)
    sha = res.json().get("sha") if res.status_code == 200 else None

    payload = {"message": "プレビューページ更新", "content": content_b64}
    if sha:
        payload["sha"] = sha

    res = requests.put(api_url, headers=headers, json=payload)
    if res.status_code not in (200, 201):
        raise Exception(f"HTMLアップロード失敗: {res.json()}")

    print(f"  プレビューページをアップロード完了")
    return GITHUB_PAGES_URL


def register(
    post_datetime: str,
    menu_type: str,
    caption: str,
    hashtags: str,
    memo: str = "",
):
    """generatedフォルダの画像をGitHubにアップロードしてスプレッドシートに登録"""

    # generatedフォルダの画像を取得
    files = sorted(glob.glob(os.path.join(GENERATED_DIR, "carousel_*.jpg")))
    if not files:
        print("generated/ フォルダに画像が見つかりません")
        return

    # 画像をGitHubにアップロード
    filenames = []
    print(f"\n{len(files)}枚をGitHubにアップロード中...")
    for filepath in files:
        filename = upload_to_github(filepath)
        filenames.append(filename)

    # GitHub Pages設定（初回のみ有効化）
    setup_github_pages()

    # プレビューHTMLを生成してアップロード
    print("  プレビューページを生成中...")
    html = generate_preview_html(filenames, caption, hashtags, post_datetime)
    preview_url = upload_html_to_github(html)

    # スプレッドシートに登録
    sheet = get_sheet()
    files_str = ",".join(filenames)
    row = [post_datetime, menu_type, files_str, caption, hashtags, memo, "確認待ち", preview_url]
    sheet.append_row(row)

    print(f"\nスプレッドシートに登録完了！")
    print(f"  投稿日時: {post_datetime}")
    print(f"  画像: {len(filenames)}枚")
    print(f"  ステータス: 確認待ち")
    print(f"\n📱 MIKIさんへのプレビューURL:")
    print(f"  {preview_url}")
    print(f"\nMIKIさんが確認後、スプレッドシートのステータスを「承認済み」に変更するとGOです！")


if __name__ == "__main__":
    register(
        post_datetime="2026/04/07 21:00",
        menu_type="ブライダルエステ",
        caption="ここにキャプションを入力",
        hashtags="#ブライダルエステ",
        memo="",
    )
