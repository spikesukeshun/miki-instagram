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

print("接続成功！")
print("ヘッダー行:", sheet.row_values(1))
