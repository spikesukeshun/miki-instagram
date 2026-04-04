import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
import os

load_dotenv()

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
client = gspread.authorize(creds)

spreadsheet_id = os.getenv("SPREADSHEET_ID")
sheet = client.open_by_key(spreadsheet_id).sheet1

# ヘッダーを設定（予約リンク列を削除）
headers = ["投稿日時", "メニュー種別", "画像ファイル名", "投稿文", "ハッシュタグ", "投稿メモ", "ステータス"]
sheet.update("A1:G1", [headers])

# 既存のH列（旧：ステータス）をクリア
sheet.update("H1:H100", [[""] * 1] * 100)

# ヘッダーのデザイン
sheet.format("A1:G1", {
    "backgroundColor": {"red": 0.2, "green": 0.6, "blue": 0.9},
    "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
    "horizontalAlignment": "CENTER"
})

# 投稿文の列（D列）を折り返し表示に設定
sheet.format("D:D", {"wrapStrategy": "WRAP"})

print("更新完了！")
print("ヘッダー:", headers)
