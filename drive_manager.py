"""
Google Drive テーマ別画像フォルダ管理モジュール
既存の credentials.json (gspread用) をそのまま流用して認証する。
"""
import io
import json
import os

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

DRIVE_FOLDERS_PATH = "drive_folders.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]

THEME_NAMES = {
    "bridal":    "ブライダル・花嫁",
    "reward":    "ご褒美・自分磨き",
    "menu":      "施術・メニュー紹介",
    "lifestyle": "MIKIの世界観・日常",
}


def _get_service():
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    return build("drive", "v3", credentials=creds)


def load_folder_ids() -> dict:
    if os.path.exists(DRIVE_FOLDERS_PATH):
        with open(DRIVE_FOLDERS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def list_drive_images(theme: str) -> list:
    """テーマフォルダ内の画像ファイル一覧を返す（ページネーション対応・全件取得）"""
    folder_ids = load_folder_ids()
    folder_id = folder_ids.get(theme)
    if not folder_id:
        return []

    service = _get_service()
    query = f"'{folder_id}' in parents and mimeType contains 'image/' and trashed=false"
    all_files = []
    page_token = None
    while True:
        kwargs = dict(
            q=query,
            fields="nextPageToken, files(id, name, thumbnailLink, webContentLink)",
            pageSize=100,
            orderBy="name",
        )
        if page_token:
            kwargs["pageToken"] = page_token
        results = service.files().list(**kwargs).execute()
        all_files += results.get("files", [])
        page_token = results.get("nextPageToken")
        if not page_token:
            break
    print(f"  Drive '{THEME_NAMES.get(theme, theme)}': {len(all_files)}枚")
    return all_files


def download_drive_image(file_id: str, dest_path: str) -> bool:
    """Drive ファイルをローカルにダウンロード"""
    service = _get_service()
    try:
        request = service.files().get_media(fileId=file_id)
        with io.FileIO(dest_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        return True
    except Exception as e:
        print(f"  Driveダウンロード失敗 ({file_id}): {e}")
        return False


def upload_to_drive(theme: str, local_path: str) -> str:
    """ローカル画像をテーマフォルダにアップロードしてファイルIDを返す"""
    folder_ids = load_folder_ids()
    folder_id = folder_ids.get(theme)
    if not folder_id:
        raise ValueError(f"テーマ '{theme}' のフォルダIDが未設定 (setup_drive_folders.py を先に実行)")

    service = _get_service()
    filename = os.path.basename(local_path)
    file_metadata = {"name": filename, "parents": [folder_id]}
    media = MediaFileUpload(local_path, mimetype="image/jpeg")
    file = service.files().create(
        body=file_metadata, media_body=media, fields="id"
    ).execute()
    return file.get("id")


def collect_drive_images_all() -> dict:
    """
    全テーマの画像一覧を取得してClaudeへの提示用に返す。
    Returns:
        {
            "bridal": [{"index": 0, "name": "...", "file_id": "..."}, ...],
            "reward": [...],
            ...
        }
    """
    result = {}
    for theme in THEME_NAMES:
        files = list_drive_images(theme)
        result[theme] = [
            {"index": i, "name": f["name"], "file_id": f["id"]}
            for i, f in enumerate(files)
        ]
    return result


if __name__ == "__main__":
    # 接続テスト：各テーマのフォルダ内ファイル一覧を表示
    all_images = collect_drive_images_all()
    for theme, files in all_images.items():
        print(f"\n【{THEME_NAMES[theme]}】({len(files)}枚)")
        for f in files[:5]:
            print(f"  [{f['index']}] {f['name']}")
        if len(files) > 5:
            print(f"  ... 他{len(files) - 5}枚")
