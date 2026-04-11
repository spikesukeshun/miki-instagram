"""
修正依頼チェックスクリプト
スプレッドシートを確認し、「修正依頼」があればClaudeに処理を依頼する。
GitHub Actionsで1日3回（9時・15時・21時 JST）実行される。
"""
import gspread
from google.oauth2.service_account import Credentials
import os
import sys

from load_env import load_from_zshrc
load_from_zshrc()

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

COL_DATETIME   = 0  # A: 投稿日時
COL_MENU       = 1  # B: メニュー種別
COL_FILES      = 2  # C: 画像ファイル名
COL_CAPTION    = 3  # D: 投稿文
COL_HASHTAGS   = 4  # E: ハッシュタグ
COL_MEMO       = 5  # F: 投稿メモ
COL_STATUS     = 6  # G: ステータス
COL_PREVIEW    = 7  # H: プレビューURL
COL_REVISION   = 8  # I: 修正指示
COL_SEED       = 9  # J: 画像生成seed（同構図で再生成するために保存）


def get_sheet():
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(os.getenv("SPREADSHEET_ID")).sheet1


def check_and_report():
    """修正依頼を探してリストで返す"""
    sheet = get_sheet()
    rows = sheet.get_all_values()
    print(f"[DEBUG] シート読み込み: {len(rows)}行")

    pending = []
    for i, row in enumerate(rows[1:], start=2):  # 2行目から（ヘッダーをスキップ）
        if len(row) <= COL_STATUS:
            continue
        status = row[COL_STATUS].strip()
        print(f"[DEBUG] 行{i}: ステータス='{status}' (len={len(status)})")
        if status == "修正依頼":
            instruction = row[COL_REVISION].strip() if len(row) > COL_REVISION else ""
            seed_val = row[COL_SEED].strip() if len(row) > COL_SEED else ""
            pending.append({
                "row_num": i,
                "datetime": row[COL_DATETIME],
                "menu_type": row[COL_MENU],
                "caption": row[COL_CAPTION],
                "hashtags": row[COL_HASHTAGS],
                "files": row[COL_FILES],
                "preview_url": row[COL_PREVIEW] if len(row) > COL_PREVIEW else "",
                "instruction": instruction,
                "seed": int(seed_val) if seed_val.isdigit() else None,
            })

    return sheet, pending


def mark_as_revised(sheet, row_num: int, new_caption: str, new_hashtags: str, new_preview_url: str):
    """修正完了後にスプレッドシートを更新"""
    sheet.update(values=[[new_caption]], range_name=f"D{row_num}")
    sheet.update(values=[[new_hashtags]], range_name=f"E{row_num}")
    sheet.update(values=[[new_preview_url]], range_name=f"H{row_num}")
    sheet.update(values=[["修正済み（確認待ち）"]], range_name=f"G{row_num}")
    sheet.update(values=[[""]], range_name=f"I{row_num}")  # 修正指示をクリア


if __name__ == "__main__":
    sheet, pending = check_and_report()

    if not pending:
        print("修正依頼はありません")
        sys.exit(0)

    print(f"{len(pending)}件の修正依頼があります:")
    for item in pending:
        print(f"  行{item['row_num']}: {item['menu_type']} - {item['instruction'][:50]}")

    sys.exit(1)  # 修正依頼ありの場合はexit code 1（GitHub Actionsで検知用）
