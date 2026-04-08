"""
Google Drive にテーマ別サブフォルダを作成する（初回のみ実行）
実行後、drive_folders.json にフォルダIDが保存される。
"""
import json
import os

from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/drive"]
DRIVE_FOLDERS_PATH = "drive_folders.json"

THEME_NAMES = {
    "bridal":    "ブライダル・花嫁",
    "reward":    "ご褒美・自分磨き",
    "menu":      "施術・メニュー紹介",
    "lifestyle": "MIKIの世界観・日常",
}


def create_folders():
    parent_id = os.getenv("DRIVE_FOLDER_ID")
    if not parent_id:
        print("エラー: DRIVE_FOLDER_ID が環境変数に設定されていません。")
        print("~/.zshrc を確認してから source ~/.zshrc を実行してください。")
        return

    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    service = build("drive", "v3", credentials=creds)

    # 既存の drive_folders.json を読み込む
    existing = {}
    if os.path.exists(DRIVE_FOLDERS_PATH):
        with open(DRIVE_FOLDERS_PATH, "r", encoding="utf-8") as f:
            existing = json.load(f)

    folder_ids = dict(existing)

    print(f"親フォルダ: {parent_id}")
    print("テーマ別サブフォルダを作成中...")

    for theme_key, theme_name in THEME_NAMES.items():
        if theme_key in folder_ids and folder_ids[theme_key]:
            print(f"  [{theme_key}] '{theme_name}' は既存: {folder_ids[theme_key]}")
            continue

        file_metadata = {
            "name": theme_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = service.files().create(body=file_metadata, fields="id").execute()
        folder_id = folder.get("id")
        folder_ids[theme_key] = folder_id
        print(f"  [{theme_key}] '{theme_name}' を作成: {folder_id}")

    with open(DRIVE_FOLDERS_PATH, "w", encoding="utf-8") as f:
        json.dump(folder_ids, f, ensure_ascii=False, indent=2)

    print(f"\n完了: {DRIVE_FOLDERS_PATH} を保存しました")
    print("\n各フォルダのリンク（Chromeで開いて画像を追加できます）:")
    for theme_key, folder_id in folder_ids.items():
        theme_name = THEME_NAMES.get(theme_key, theme_key)
        print(f"  {theme_name}: https://drive.google.com/drive/folders/{folder_id}")


if __name__ == "__main__":
    create_folders()
