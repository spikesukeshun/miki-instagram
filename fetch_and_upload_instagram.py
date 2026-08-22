"""
Instagram全投稿画像をDriveにテーマ別アップロード。
389投稿 × 最大10枚 = 大量になるため進捗表示付き。
既存ファイルはスキップ（重複なし）。
"""
import json
import os
import re
import time
import requests
from io import BytesIO
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ── 設定 ──────────────────────────────────────────
TOKEN_PATH = "token_drive.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]

# ~/.zshrc からInstagramトークンを取得
def _get_ig_token():
    with open(os.path.expanduser("~/.zshrc")) as f:
        content = f.read()
    m = re.search(r"INSTAGRAM_ACCESS_TOKEN='([^']+)'", content)
    return m.group(1).strip() if m else ""

IG_TOKEN = _get_ig_token()
IG_ACCOUNT_ID = "17841440986401113"
IG_API_BASE = "https://graph.facebook.com/v19.0"


# ── テーマ分類 ────────────────────────────────────
def classify_theme(caption: str) -> str:
    caption = caption or ""
    if any(k in caption for k in ["花嫁", "ブライダル", "結婚式", "wedding", "Wedding", "挙式", "プレ花嫁"]):
        return "bridal"
    if any(k in caption for k in ["施術", "コース", "メニュー", "デッドシー", "痩身", "フェイシャル", "ボディ", "脱毛", "オーダーメイド"]):
        return "menu"
    if any(k in caption for k in ["ご褒美", "自分磨き", "アラサー", "アラフォー", "頑張った", "疲れた", "リラックス", "癒し"]):
        return "reward"
    return "lifestyle"


# ── Drive認証 ─────────────────────────────────────
def get_drive_service():
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("drive", "v3", credentials=creds)


# ── Drive: ファイルが既存か確認 ───────────────────
def file_exists_in_drive(service, folder_id: str, name: str) -> bool:
    q = f"name='{name}' and '{folder_id}' in parents and trashed=false"
    res = service.files().list(q=q, fields="files(id)").execute()
    return len(res.get("files", [])) > 0


# ── Drive: アップロード ───────────────────────────
def upload_to_drive(service, folder_id: str, name: str, image_bytes: bytes):
    metadata = {"name": name, "parents": [folder_id]}
    media = MediaIoBaseUpload(BytesIO(image_bytes), mimetype="image/jpeg", resumable=False)
    service.files().create(body=metadata, media_body=media, fields="id").execute()


# ── Instagram: 全メディア取得（ページネーション） ──
def fetch_all_media():
    media_list = []
    url = f"{IG_API_BASE}/{IG_ACCOUNT_ID}/media"
    params = {
        "fields": "id,media_type,media_url,caption,timestamp",
        "limit": 100,
        "access_token": IG_TOKEN,
    }
    page = 1
    while url:
        r = requests.get(url, params=params, timeout=30)
        data = r.json()
        if "error" in data:
            print(f"APIエラー: {data['error']['message']}")
            break
        items = data.get("data", [])
        media_list.extend(items)
        print(f"  ページ{page}: {len(items)}件取得（累計: {len(media_list)}件）")
        cursor = data.get("paging", {}).get("cursors", {}).get("after")
        next_url = data.get("paging", {}).get("next")
        url = next_url if next_url else None
        params = {"access_token": IG_TOKEN}  # nextにはすでにパラメータ含まれる
        page += 1
        time.sleep(0.3)
    return media_list


# ── Instagram: カルーセルの子画像取得 ────────────
def fetch_carousel_children(media_id: str) -> list:
    url = f"{IG_API_BASE}/{media_id}/children"
    params = {"fields": "id,media_url,media_type", "access_token": IG_TOKEN}
    r = requests.get(url, params=params, timeout=30)
    data = r.json()
    return data.get("data", [])


# ── メイン ────────────────────────────────────────
def main():
    folders = json.load(open("drive_folders.json"))
    service = get_drive_service()

    print("Instagram全投稿を取得中...")
    media_list = fetch_all_media()
    print(f"\n合計: {len(media_list)}件\n")

    uploaded = 0
    skipped = 0
    errors = 0

    for i, item in enumerate(media_list, 1):
        media_type = item.get("media_type", "")
        caption = item.get("caption", "")
        timestamp = item.get("timestamp", "")[:10].replace("-", "")  # 20260407
        media_id = item["id"]
        theme = classify_theme(caption)
        folder_id = folders[theme]

        # 画像URLリストを作成
        if media_type == "CAROUSEL_ALBUM":
            children = fetch_carousel_children(media_id)
            images = [(c["id"], c.get("media_url", ""), idx+1)
                      for idx, c in enumerate(children)
                      if c.get("media_type") in ("IMAGE", None)]
            time.sleep(0.2)
        elif media_type == "IMAGE":
            images = [(media_id, item.get("media_url", ""), 1)]
        else:
            # VIDEO等はスキップ
            continue

        for child_id, img_url, slide_num in images:
            if not img_url:
                continue
            drive_name = f"{timestamp}_{media_id[-6:]}_{slide_num:02d}.jpg"

            # 既存チェック
            if file_exists_in_drive(service, folder_id, drive_name):
                skipped += 1
                continue

            # ダウンロード
            try:
                res = requests.get(img_url, timeout=30)
                if res.status_code != 200 or len(res.content) < 5000:
                    errors += 1
                    continue
                upload_to_drive(service, folder_id, drive_name, res.content)
                uploaded += 1
            except Exception as e:
                print(f"  エラー ({drive_name}): {e}")
                errors += 1
                continue

            time.sleep(0.1)

        # 進捗表示（10件ごと）
        if i % 10 == 0 or i == len(media_list):
            print(f"[{i}/{len(media_list)}] {theme:10s} | アップ:{uploaded} スキップ:{skipped} エラー:{errors}")

    print(f"\n完了: アップロード {uploaded}枚 / スキップ {skipped}枚 / エラー {errors}件")


if __name__ == "__main__":
    main()
