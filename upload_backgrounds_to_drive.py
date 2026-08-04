"""
backgrounds/ フォルダの画像をテーマ別に Google Drive にアップロード。
OAuth 2.0（個人アカウント）を使用。初回のみブラウザ認証が必要。
"""
import json
import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/drive"]
TOKEN_PATH = "token_drive.json"
CLIENT_SECRETS_PATH = "client_secrets.json"
BACKGROUNDS_DIR = "backgrounds"

# テーマ別アップロード対象（ローカルファイル名 → Drive上のファイル名）
UPLOAD_MAP = {
    "bridal": [
        ("slide1.jpg",                       "bridal_wedding_hands_roses.jpg"),
        ("slide2.jpg",                       "bridal_wedding_dress_fitting.jpg"),
        ("slide3.jpg",                       "bridal_bride_portrait.jpg"),
        ("bg_20260407045514_05.jpg",         "bridal_hanamiyome_esute_post.jpg"),
        ("bg_20260407050755_02.jpg",         "bridal_cover_kagayaku_hanamiyome.jpg"),
        ("bg_20260407050755_06.jpg",         "bridal_customer_voice_01.jpg"),
        ("bg_20260407052458_02.jpg",         "bridal_graduate_brides_collage.jpg"),
        ("bg_20260407052458_04.jpg",         "bridal_customer_voice_02.jpg"),
    ],
    "reward": [
        ("custom_20260406012741_05.jpg",     "reward_esute_bed_pink.jpg"),
        ("custom_20260406012741_06.jpg",     "reward_esute_bed_curtain.jpg"),
        ("bg_20260407045514_01.jpg",         "reward_relaxation_01.jpg"),
        ("bg_20260407045514_04.jpg",         "reward_relaxation_02.jpg"),
        ("bg_20260407045514_06.jpg",         "reward_relaxation_03.jpg"),
        ("bg_20260407051229_01.jpg",         "reward_jibun_migaki_01.jpg"),
        ("bg_20260407051229_03.jpg",         "reward_jibun_migaki_02.jpg"),
        ("bg_20260407051229_04.jpg",         "reward_jibun_migaki_03.jpg"),
        ("bg_20260407051229_05.jpg",         "reward_jibun_migaki_04.jpg"),
        ("bg_20260407051229_06.jpg",         "reward_jibun_migaki_05.jpg"),
        ("bg_20260407051836_01.jpg",         "reward_gohoubi_esute_01.jpg"),
        ("bg_20260407051836_04.jpg",         "reward_gohoubi_esute_02.jpg"),
        ("bg_20260407051836_06.jpg",         "reward_gohoubi_esute_03.jpg"),
        ("bg_20260407052809_01.jpg",         "reward_gohoubi_esute_04.jpg"),
        ("bg_20260407052809_04.jpg",         "reward_gohoubi_esute_05.jpg"),
        ("bg_20260407052809_06.jpg",         "reward_gohoubi_esute_06.jpg"),
    ],
    "menu": [
        ("custom_20260406012741_01.jpg",     "menu_treatment_room_01.jpg"),
        ("custom_20260406012741_02.jpg",     "menu_treatment_room_02.jpg"),
        ("custom_20260406012741_03.jpg",     "menu_treatment_room_03.jpg"),
        ("custom_20260406012741_04.jpg",     "menu_treatment_room_04.jpg"),
        ("bg_20260407045514_03.jpg",         "menu_dead_sea_bath_salt.jpg"),
        ("bg_20260407050755_07.jpg",         "menu_order_made_course.jpg"),
        ("bg_20260407052458_01.jpg",         "menu_施術_01.jpg"),
        ("bg_20260407052458_05.jpg",         "menu_施術_02.jpg"),
    ],
    "lifestyle": [
        ("bg_20260407050755_01.jpg",         "lifestyle_miki_world_01.jpg"),
        ("bg_20260407050755_04.jpg",         "lifestyle_miki_world_02.jpg"),
        ("bg_20260407050755_05.jpg",         "lifestyle_miki_world_03.jpg"),
        ("bg_20260407051836_02.jpg",         "lifestyle_newyear_2026.jpg"),
        ("bg_20260407052458_06.jpg",         "lifestyle_miki_daily_01.jpg"),
    ],
}


def get_credentials():
    """OAuth認証。token_drive.json があれば再利用、なければブラウザ認証。"""
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRETS_PATH):
                raise FileNotFoundError(
                    f"\n{CLIENT_SECRETS_PATH} が見つかりません。\n"
                    "Google Cloud Console で OAuth 2.0 クライアントID（デスクトップアプリ）を作成し、\n"
                    f"JSONをダウンロードして {CLIENT_SECRETS_PATH} として保存してください。"
                )
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
        print(f"  認証完了 → {TOKEN_PATH} を保存しました")
    return creds


def upload_file(service, folder_id: str, local_path: str, drive_name: str) -> str:
    """1ファイルをDriveフォルダにアップロード。同名があれば上書き。"""
    # 同名ファイルを検索
    query = f"name='{drive_name}' and '{folder_id}' in parents and trashed=false"
    existing = service.files().list(q=query, fields="files(id,name)").execute()
    files = existing.get("files", [])

    media = MediaFileUpload(local_path, mimetype="image/jpeg", resumable=False)

    if files:
        file_id = files[0]["id"]
        service.files().update(fileId=file_id, media_body=media).execute()
        return f"上書き: {drive_name}"
    else:
        metadata = {"name": drive_name, "parents": [folder_id]}
        service.files().create(body=metadata, media_body=media, fields="id").execute()
        return f"新規: {drive_name}"


def main():
    folders = json.load(open("drive_folders.json"))

    print("Google Drive 認証中...")
    creds = get_credentials()
    service = build("drive", "v3", credentials=creds)
    print("認証成功\n")

    total = sum(len(v) for v in UPLOAD_MAP.values())
    done = 0

    for theme, files in UPLOAD_MAP.items():
        folder_id = folders[theme]
        print(f"[{theme}] {len(files)}枚 → フォルダID: {folder_id}")
        for local_name, drive_name in files:
            local_path = os.path.join(BACKGROUNDS_DIR, local_name)
            if not os.path.exists(local_path):
                print(f"  スキップ（ファイル不在）: {local_name}")
                continue
            result = upload_file(service, folder_id, local_path, drive_name)
            done += 1
            print(f"  [{done}/{total}] {result}")
        print()

    print(f"完了: {done}/{total} 枚アップロード")


if __name__ == "__main__":
    main()
