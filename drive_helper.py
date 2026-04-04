from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from dotenv import load_dotenv
import os

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_ID = os.getenv("DRIVE_FOLDER_ID")


def get_drive_service():
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    return build("drive", "v3", credentials=creds)


def get_file_url(filename: str) -> str:
    """ファイル名からGoogleドライブの公開URLを返す"""
    service = get_drive_service()
    results = service.files().list(
        q=f"name='{filename}' and '{FOLDER_ID}' in parents and trashed=false",
        fields="files(id, name)"
    ).execute()

    files = results.get("files", [])
    if not files:
        raise FileNotFoundError(f"ドライブにファイルが見つかりません: {filename}")

    file_id = files[0]["id"]

    # ファイルを公開設定にする
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"}
    ).execute()

    return f"https://drive.google.com/uc?export=download&id={file_id}"


if __name__ == "__main__":
    # テスト用
    print("Googleドライブ接続テスト")
    service = get_drive_service()
    results = service.files().list(
        q=f"'{FOLDER_ID}' in parents and trashed=false",
        fields="files(id, name)"
    ).execute()
    files = results.get("files", [])
    if files:
        print(f"フォルダ内のファイル ({len(files)}件):")
        for f in files:
            print(f"  - {f['name']}")
    else:
        print("フォルダは空です（正常）")
    print("接続成功！")
