import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
import os
import glob
import base64
import requests

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


def get_sheet():
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).sheet1


def upload_to_github(filepath: str) -> str:
    """ファイルをGitHubリポジトリにアップロードしてファイル名を返す"""
    filename = os.path.basename(filepath)
    with open(filepath, "rb") as f:
        content = base64.b64encode(f.read()).decode()

    api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{GENERATED_DIR}/{filename}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    # 既存ファイルのSHAを取得（更新の場合に必要）
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

    filenames = []
    print(f"\n{len(files)}枚をGitHubにアップロード中...")
    for filepath in files:
        filename = upload_to_github(filepath)
        filenames.append(filename)

    files_str = ",".join(filenames)

    # スプレッドシートに登録
    sheet = get_sheet()
    row = [post_datetime, menu_type, files_str, caption, hashtags, memo, "未投稿"]
    sheet.append_row(row)

    print(f"\nスプレッドシートに登録完了！")
    print(f"  投稿日時: {post_datetime}")
    print(f"  画像: {len(filenames)}枚")
    print(f"  ステータス: 未投稿")
    print(f"\nGOを出すにはGitHub Actions → Run workflow を押してください！")


if __name__ == "__main__":
    register(
        post_datetime="2026/04/07 21:00",
        menu_type="ブライダルエステ",
        caption="ここにキャプションを入力",
        hashtags="#ブライダルエステ",
        memo="",
    )
