"""
Step 3: post_classifications.json に基づいてDriveファイルを正しいフォルダへ移動。
デフォルト: dry-run（確認のみ）
実行:       python3 reclassify_drive.py --execute
"""
import json
import sys
import time

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

TOKEN_PATH = "token_drive.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]


def get_drive_service():
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("drive", "v3", credentials=creds)


def move_file(service, file_id: str, from_folder_id: str, to_folder_id: str) -> bool:
    try:
        service.files().update(
            fileId=file_id,
            addParents=to_folder_id,
            removeParents=from_folder_id,
            fields="id, parents",
        ).execute()
        time.sleep(0.1)
        return True
    except HttpError as e:
        print(f"    移動失敗 ({file_id}): {e}")
        return False


def trash_file(service, file_id: str) -> bool:
    try:
        service.files().update(fileId=file_id, body={"trashed": True}).execute()
        time.sleep(0.1)
        return True
    except HttpError as e:
        print(f"    削除失敗 ({file_id}): {e}")
        return False


def main():
    dry_run = "--execute" not in sys.argv
    service = None if dry_run else get_drive_service()

    if dry_run:
        print("=== DRY-RUN モード（実際の移動はしません）===")
        print("実行するには: python3 reclassify_drive.py --execute\n")
    else:
        print("=== EXECUTEモード（実際に移動・削除します）===\n")

    try:
        classifications_data = json.load(open("post_classifications.json", encoding="utf-8"))
        drive_state = json.load(open("drive_current_state.json", encoding="utf-8"))
        folders = json.load(open("drive_folders.json"))
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        print("fetch_posts_data.py を先に実行してください")
        sys.exit(1)

    # 分類マップ: drive_prefix → 分類情報
    class_map = {c["drive_prefix"]: c for c in classifications_data["classifications"]}

    # Drive状態: prefix → {theme: [file_dict, ...]}
    prefix_files = {}
    for theme, files in drive_state["folders"].items():
        for f in files:
            prefix = f["drive_prefix"]
            if not prefix:
                continue
            prefix_files.setdefault(prefix, {}).setdefault(theme, []).append(f)

    moved = []
    deleted = []
    skipped = []
    not_in_drive = []
    errors = []

    print(f"分類件数: {len(class_map)}件\n")

    for prefix, cls in class_map.items():
        target_theme = cls["theme"]

        if target_theme == "NEEDS_REVIEW":
            print(f"  [未分類] {prefix}")
            not_in_drive.append(f"NEEDS_REVIEW:{prefix}")
            continue

        current = prefix_files.get(prefix)
        if not current:
            not_in_drive.append(prefix)
            continue

        target_folder_id = folders[target_theme]
        all_themes = list(current.keys())
        already_correct = target_theme in current

        # すでに全て正しいフォルダにあればスキップ
        if all(t == target_theme for t in all_themes):
            skipped.append(prefix)
            continue

        for theme, files in current.items():
            if theme == target_theme:
                continue
            from_folder_id = folders[theme]
            for f in files:
                if already_correct:
                    # 正解フォルダに既にある → 誤フォルダのものを削除（重複除去）
                    print(f"  削除（重複）: {f['name']} [{theme}]")
                    if not dry_run:
                        ok = trash_file(service, f["file_id"])
                        if ok:
                            deleted.append((prefix, theme, f["name"]))
                        else:
                            errors.append((prefix, f"削除失敗: {f['name']}"))
                    else:
                        deleted.append((prefix, theme, f["name"]))
                else:
                    # 正解フォルダにない → 移動
                    print(f"  移動: {f['name']} [{theme}→{target_theme}]")
                    if not dry_run:
                        ok = move_file(service, f["file_id"], from_folder_id, target_folder_id)
                        if ok:
                            moved.append((prefix, theme, target_theme, f["name"]))
                            already_correct = True
                        else:
                            errors.append((prefix, f"移動失敗: {f['name']}"))
                    else:
                        moved.append((prefix, theme, target_theme, f["name"]))
                        already_correct = True

    print(f"\n=== {'DRY-RUN ' if dry_run else ''}結果サマリー ===")
    print(f"  移動予定/実行: {len(moved)}件")
    print(f"  削除予定/実行: {len(deleted)}件（重複除去）")
    print(f"  変更なし:      {len(skipped)}件")
    print(f"  Drive未存在:   {len(not_in_drive)}件")
    print(f"  エラー:        {len(errors)}件")

    log = {
        "mode": "dry-run" if dry_run else "execute",
        "moved": moved,
        "deleted": deleted,
        "skipped": skipped,
        "not_in_drive": not_in_drive,
        "errors": errors,
    }
    with open("reclassify_log.json", "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print("\n→ reclassify_log.json に詳細を保存しました")


if __name__ == "__main__":
    main()
