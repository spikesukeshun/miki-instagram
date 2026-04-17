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
spreadsheet = client.open_by_key(spreadsheet_id)
sheet = spreadsheet.sheet1

# ヘッダーを設定
headers = ["投稿日時", "メニュー種別", "画像ファイル名", "投稿文", "ハッシュタグ", "投稿メモ", "ステータス"]
sheet.update("A1:G1", [headers])

# 既存のH列をクリア
sheet.update("H1:H100", [[""] * 1] * 100)

# ヘッダーのデザイン
sheet.format("A1:G1", {
    "backgroundColor": {"red": 0.2, "green": 0.6, "blue": 0.9},
    "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
    "horizontalAlignment": "CENTER"
})

# 投稿文の列（D列）を折り返し表示に設定
sheet.format("D:D", {"wrapStrategy": "WRAP"})

print("投稿スケジュールシート更新完了！")

# ───────────────────────────────
# 画像プロンプトシートを追加
# ───────────────────────────────
try:
    prompt_sheet = spreadsheet.worksheet("画像プロンプト")
    print("画像プロンプトシートは既に存在します")
except gspread.exceptions.WorksheetNotFound:
    prompt_sheet = spreadsheet.add_worksheet(title="画像プロンプト", rows=50, cols=4)
    print("画像プロンプトシートを作成しました")

# ヘッダー
prompt_headers = ["スライド番号", "内容", "プロンプト（英語）", "備考"]
prompt_sheet.update("A1:D1", [prompt_headers])

# ヘッダーのデザイン
prompt_sheet.format("A1:D1", {
    "backgroundColor": {"red": 0.9, "green": 0.7, "blue": 0.8},
    "textFormat": {"bold": True},
    "horizontalAlignment": "CENTER"
})

# 6枚分のプロンプトデータ
prompts = [
    ["1枚目", "表紙", "elegant bridal bouquet of pink roses, wedding rings, soft pink and gold tones, luxury background", ""],
    ["2枚目", "美容学校・原点", "beauty school, skincare treatment, professional esthetic salon, warm lighting, elegant atmosphere", ""],
    ["3枚目", "4つのお悩み", "worried young woman, soft pink background, elegant style, beauty consultation", ""],
    ["4枚目", "mikiの想い", "bridal consultation, elegant woman in wedding dress, soft pink and gold tones, warm and caring atmosphere, beautiful bouquet of pink roses", ""],
    ["5枚目", "結婚式後も…", "happy elegant woman, daily beauty routine, soft pink tones, self-care lifestyle, luxury spa", ""],
    ["6枚目", "初回20%OFF・DMへ", "beautiful pink roses, gold ribbon, luxury gift, elegant pink and gold background", ""],
]

prompt_sheet.update("A2:D7", prompts)

# プロンプト列（C列）を折り返し表示に設定
prompt_sheet.format("C:C", {"wrapStrategy": "WRAP"})

print("画像プロンプトシート設定完了！")
