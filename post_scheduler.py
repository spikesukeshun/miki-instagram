import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
import os
from datetime import datetime
from instagram_api import post_image, post_video
from drive_helper import get_file_url

load_dotenv()

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

# 列の定義
COL_DATETIME  = 0  # A: 投稿日時
COL_MENU      = 1  # B: メニュー種別
COL_FILENAME  = 2  # C: 画像ファイル名
COL_TEXT      = 3  # D: 投稿文
COL_HASHTAGS  = 4  # E: ハッシュタグ
COL_MEMO      = 5  # F: 投稿メモ
COL_STATUS    = 6  # G: ステータス


def get_sheet():
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet_id = os.getenv("SPREADSHEET_ID")
    return client.open_by_key(spreadsheet_id).sheet1


def build_caption(text: str, hashtags: str) -> str:
    caption = text.strip()
    if hashtags.strip():
        caption += f"\n\n{hashtags.strip()}"
    return caption


def is_video(filename: str) -> bool:
    return filename.lower().endswith((".mp4", ".mov"))


def run():
    sheet = get_sheet()
    rows = sheet.get_all_values()
    now = datetime.now()

    print(f"チェック開始: {now.strftime('%Y/%m/%d %H:%M')}")
    posted = 0

    for i, row in enumerate(rows[1:], start=2):
        if len(row) < 7:
            continue

        status = row[COL_STATUS].strip()
        if status != "未投稿":
            continue

        datetime_str = row[COL_DATETIME].strip()
        try:
            post_time = datetime.strptime(datetime_str, "%Y/%m/%d %H:%M")
        except ValueError:
            print(f"行{i}: 日時フォーマットエラー → {datetime_str}")
            continue

        if post_time > now:
            print(f"行{i}: 投稿待機中 → {datetime_str}")
            continue

        filename = row[COL_FILENAME].strip()
        caption = build_caption(row[COL_TEXT], row[COL_HASHTAGS])

        print(f"行{i}: 投稿中 → {filename}")

        try:
            file_url = get_file_url(filename)

            if is_video(filename):
                post_id = post_video(file_url, caption)
            else:
                post_id = post_image(file_url, caption)

            sheet.update_cell(i, COL_STATUS + 1, "投稿済み")
            print(f"行{i}: 投稿成功！ post_id={post_id}")
            posted += 1

        except FileNotFoundError as e:
            print(f"行{i}: ファイルなし → {e}")
            sheet.update_cell(i, COL_STATUS + 1, "エラー：ファイルなし")
        except Exception as e:
            print(f"行{i}: 投稿失敗 → {e}")
            sheet.update_cell(i, COL_STATUS + 1, f"エラー：{str(e)[:50]}")

    print(f"完了！投稿数: {posted}件")


if __name__ == "__main__":
    run()
