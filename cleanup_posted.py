"""
cleanup_posted.py
-----------------
既存の取り残しファイルを一括掃除するスクリプト（一回限りのバッチ用途）。

【役割】
1. ルート直下 generated/carousel_*.jpg（フラット残骸）を削除
2. スプレッドシートで status="投稿済み" の行から slug を抽出
3. 各 slug について GitHub 上の generated/{slug}/ を全削除
4. 最後にローカルの git rm -r とコミット/push をユーザーに案内

確認待ち・承認済みの slug は触らない（投稿前なので削除すると post_scheduler.py が失敗する）。

【使い方】
  python cleanup_posted.py --dry-run   # 削除対象を表示するだけ
  python cleanup_posted.py --force     # 確認なしで削除実行
"""

import argparse
import glob
import os
import subprocess
import sys

import gspread
from google.oauth2.service_account import Credentials

from load_env import load_from_zshrc
from register_post import (
    GENERATED_DIR,
    GITHUB_OWNER,
    GITHUB_REPO,
    delete_post_folder_from_github,
    list_github_folder,
)

load_from_zshrc()

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
COL_DATETIME = 0
COL_FILENAME = 2
COL_STATUS = 6


def get_sheet():
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(os.getenv("SPREADSHEET_ID")).sheet1


def collect_posted_slugs() -> list:
    """status='投稿済み' の行から slug 一覧を返す"""
    sheet = get_sheet()
    rows = sheet.get_all_values()
    slugs = []
    for row in rows[1:]:
        if len(row) <= COL_STATUS:
            continue
        if row[COL_STATUS].strip() != "投稿済み":
            continue
        filename = row[COL_FILENAME].strip()
        if not filename or "/" not in filename:
            continue
        slug = filename.split(",")[0].strip().split("/")[0]
        if slug and slug not in slugs:
            slugs.append(slug)
    return slugs


def collect_pending_slugs() -> list:
    """status='確認待ち' '承認済み' の slug（保護対象）を返す"""
    sheet = get_sheet()
    rows = sheet.get_all_values()
    slugs = []
    for row in rows[1:]:
        if len(row) <= COL_STATUS:
            continue
        if row[COL_STATUS].strip() not in ("確認待ち", "承認済み"):
            continue
        filename = row[COL_FILENAME].strip()
        if not filename or "/" not in filename:
            continue
        slug = filename.split(",")[0].strip().split("/")[0]
        if slug and slug not in slugs:
            slugs.append(slug)
    return slugs


def main():
    parser = argparse.ArgumentParser(description="投稿済みフォルダの一括掃除")
    parser.add_argument("--dry-run", action="store_true", help="削除せず対象一覧のみ表示")
    parser.add_argument("--force", action="store_true", help="確認プロンプトをスキップ")
    args = parser.parse_args()

    print("=" * 50)
    print("  cleanup_posted.py")
    print("=" * 50)

    # 1. ルート直下のフラット残骸
    flat_files = sorted(glob.glob(os.path.join(GENERATED_DIR, "carousel_*.jpg")))
    print(f"\n[1] ルート直下の残骸: {len(flat_files)} ファイル")
    for f in flat_files:
        print(f"  - {f}")

    # 2. 投稿済み slug
    posted = collect_posted_slugs()
    pending = set(collect_pending_slugs())
    targets = [s for s in posted if s not in pending]
    skipped = [s for s in posted if s in pending]

    print(f"\n[2] 投稿済み slug: {len(targets)} 件")
    for s in targets:
        print(f"  - generated/{s}/")
    if skipped:
        print(f"\n[!] 確認待ち/承認済みと重複するため保護: {skipped}")

    if args.dry_run:
        print("\n--dry-run モード: 何も削除しません。")
        return

    if not args.force:
        ans = input(f"\n{len(flat_files)}ファイル + {len(targets)}フォルダを削除します。実行しますか？ [y/N]: ").strip().lower()
        if ans != "y":
            print("キャンセルしました。")
            return

    # 3. ルート直下のフラットを削除（git rm はユーザー任せ。.gitignore で今後は track されない）
    for f in flat_files:
        try:
            os.remove(f)
            print(f"  削除: {f}")
        except Exception as e:
            print(f"  失敗: {f} ({e})")

    # 4. GitHub 上の slug フォルダを削除
    print(f"\n[3] GitHub上のフォルダを削除中...")
    for slug in targets:
        try:
            n = delete_post_folder_from_github(slug)
            print(f"  generated/{slug}/ : {n}ファイル削除")
        except Exception as e:
            print(f"  generated/{slug}/ : 失敗 ({e})")

    print("\n完了。次の手順でローカルにも反映してください：")
    print("  git pull origin main")
    print("  git add -A && git commit -m 'chore: cleanup posted images' && git push")


if __name__ == "__main__":
    main()
