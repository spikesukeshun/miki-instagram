"""
Step 1: Instagram全投稿キャプションとDrive現在状態を取得して保存。
  → posts_cache.json
  → drive_current_state.json
"""
import json
import os
import re
import sys
import time
from datetime import datetime

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

IG_ACCOUNT_ID = "17841440986401113"
IG_API_BASE = "https://graph.facebook.com/v19.0"
TOKEN_PATH = "token_drive.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]


# ── 認証 ────────────────────────────────────────────────
def get_ig_token() -> str:
    with open(os.path.expanduser("~/.zshrc")) as f:
        content = f.read()
    m = re.search(r"INSTAGRAM_ACCESS_TOKEN='([^']+)'", content)
    if not m:
        print("ERROR: INSTAGRAM_ACCESS_TOKEN が ~/.zshrc に見つかりません")
        sys.exit(1)
    return m.group(1).strip()


def get_drive_service():
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("drive", "v3", credentials=creds)


# ── Instagram ────────────────────────────────────────────
def fetch_all_media(ig_token: str) -> list:
    media_list = []
    url = f"{IG_API_BASE}/{IG_ACCOUNT_ID}/media"
    params = {
        "fields": "id,media_type,caption,timestamp",
        "limit": 100,
        "access_token": ig_token,
    }
    page = 1
    while url:
        r = requests.get(url, params=params, timeout=30)
        data = r.json()
        if "error" in data:
            print(f"Instagram APIエラー: {data['error']['message']}")
            sys.exit(1)
        items = data.get("data", [])
        media_list.extend(items)
        print(f"  ページ{page}: {len(items)}件 (累計{len(media_list)}件)")
        url = data.get("paging", {}).get("next")
        params = {"access_token": ig_token}
        page += 1
        time.sleep(0.3)
    return media_list


def fetch_carousel_children(media_id: str, ig_token: str) -> list:
    r = requests.get(
        f"{IG_API_BASE}/{media_id}/children",
        params={"fields": "id,media_type", "access_token": ig_token},
        timeout=30,
    )
    data = r.json()
    return [c["id"] for c in data.get("data", []) if c.get("media_type") in ("IMAGE", None, "CAROUSEL_ALBUM")]


def build_posts_cache(media_list: list, ig_token: str) -> dict:
    posts = []
    warn_ids = []
    total = len(media_list)

    for i, item in enumerate(media_list, 1):
        media_id = item["id"]
        media_type = item.get("media_type", "")
        caption = item.get("caption", "") or ""
        timestamp = item.get("timestamp", "")
        date_str = timestamp[:10].replace("-", "") if timestamp else "00000000"
        drive_prefix = f"{date_str}_{media_id[-6:]}"

        if media_type == "VIDEO":
            continue

        child_ids = []
        if media_type == "CAROUSEL_ALBUM":
            try:
                child_ids = fetch_carousel_children(media_id, ig_token)
                time.sleep(0.2)
            except Exception as e:
                warn_ids.append(media_id)

        posts.append({
            "media_id": media_id,
            "timestamp": timestamp,
            "date_str": date_str,
            "media_type": media_type,
            "caption": caption,
            "child_ids": child_ids,
            "slide_count": len(child_ids) if child_ids else 1,
            "drive_prefix": drive_prefix,
        })

        if i % 50 == 0 or i == total:
            print(f"  整形中: {i}/{total}")

    if warn_ids:
        print(f"\n警告: カルーセル子取得失敗 {len(warn_ids)}件: {warn_ids[:5]}")

    return {
        "fetched_at": datetime.now().isoformat(),
        "total_count": len(posts),
        "posts": posts,
    }


# ── Drive ────────────────────────────────────────────────
def fetch_folder_files(service, folder_id: str) -> list:
    files = []
    page_token = None
    while True:
        params = {
            "q": f"'{folder_id}' in parents and trashed=false",
            "fields": "nextPageToken, files(id, name)",
            "pageSize": 1000,
        }
        if page_token:
            params["pageToken"] = page_token
        res = service.files().list(**params).execute()
        for f in res.get("files", []):
            name = f["name"]
            parts = name.split("_")
            drive_prefix = "_".join(parts[:2]) if len(parts) >= 3 else None
            files.append({
                "file_id": f["id"],
                "name": name,
                "drive_prefix": drive_prefix,
            })
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    return files


def build_drive_current_state(service, folders: dict) -> dict:
    state = {"fetched_at": datetime.now().isoformat(), "folders": {}, "prefix_to_folder": {}}
    duplicates = {}

    for theme, folder_id in folders.items():
        print(f"  Drive [{theme}] フォルダ取得中...")
        files = fetch_folder_files(service, folder_id)
        state["folders"][theme] = files
        print(f"    → {len(files)}件")

        for f in files:
            prefix = f["drive_prefix"]
            if not prefix:
                continue
            existing = state["prefix_to_folder"].get(prefix)
            if existing is None:
                state["prefix_to_folder"][prefix] = theme
            elif existing != theme:
                # 重複: リスト化
                if isinstance(existing, list):
                    if theme not in existing:
                        existing.append(theme)
                else:
                    state["prefix_to_folder"][prefix] = [existing, theme]
                duplicates[prefix] = state["prefix_to_folder"][prefix]

    if duplicates:
        print(f"\n  重複prefix（複数フォルダに存在）: {len(duplicates)}件")

    return state


# ── メイン ────────────────────────────────────────────────
def main():
    ig_token = get_ig_token()
    folders = json.load(open("drive_folders.json"))

    print("=== Instagram全投稿取得 ===")
    media_list = fetch_all_media(ig_token)
    print(f"\n取得完了: {len(media_list)}件")

    print("\nキャプション等を整形中（カルーセルは子画像IDも取得）...")
    posts_cache = build_posts_cache(media_list, ig_token)

    with open("posts_cache.json", "w", encoding="utf-8") as f:
        json.dump(posts_cache, f, ensure_ascii=False, indent=2)
    print(f"\n→ posts_cache.json 保存完了（{posts_cache['total_count']}投稿）")

    print("\n=== Drive現在状態取得 ===")
    service = get_drive_service()
    drive_state = build_drive_current_state(service, folders)

    total_files = sum(len(v) for v in drive_state["folders"].values())
    with open("drive_current_state.json", "w", encoding="utf-8") as f:
        json.dump(drive_state, f, ensure_ascii=False, indent=2)
    print(f"\n→ drive_current_state.json 保存完了（総{total_files}ファイル）")

    print("\n=== 完了 ===")
    for theme, files in drive_state["folders"].items():
        print(f"  {theme}: {len(files)}件")


if __name__ == "__main__":
    main()
