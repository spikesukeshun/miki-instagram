"""スプレッドシート接続・更新の共通処理（リトライ付き）。

Google Sheets API は一時的に 503 UNAVAILABLE や 429 を返すことがある。
GitHub Actions の定時実行がこれで落ちると、その回に投稿予定だった行が
次の起動（最大約13時間後）まで飛んでしまうため、指数バックオフで再試行する。

特に「投稿済み」への書き込み（post_scheduler.py）は Instagram 投稿の直後にあり、
ここが落ちるとステータスが「承認済み」のまま残って次回に二重投稿となる。
読み取りだけでなく update_cell もリトライ対象にしているのはそのため。

2026-07-19 の post.yml 失敗（503 UNAVAILABLE）を受けて追加。
"""

import os
import time

import google.auth.exceptions
import gspread
import requests
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

# 一時的な障害としてリトライ対象にするHTTPステータス
RETRY_STATUS = {429, 500, 502, 503, 504}

# TransportError は google-auth がトークン取得時の通信エラーを包んだもの。
# requests の例外を継承していないため、明示的に並べる必要がある
# （Sheets API が不調なときはトークンエンドポイントも不調になりやすい）。
_CATCHABLE = (
    gspread.exceptions.APIError,
    requests.exceptions.RequestException,
    google.auth.exceptions.TransportError,
)


def _is_retryable(error) -> bool:
    if isinstance(error, (requests.exceptions.ConnectionError,
                          requests.exceptions.Timeout,
                          google.auth.exceptions.TransportError)):
        return True
    response = getattr(error, "response", None)
    return getattr(response, "status_code", None) in RETRY_STATUS


def _with_retry(what: str, func, attempts: int, wait: int):
    """一時的な障害のみ待ってから再試行する。

    恒久的なエラー（404、認証情報の不備など）と、attempts 回すべて失敗した場合は
    例外をそのまま送出する（恒久的な障害はこれまで通り失敗として通知させたいため）。
    """
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except _CATCHABLE as e:
            if attempt == attempts or not _is_retryable(e):
                raise
            sleep_sec = wait * attempt  # 5秒、10秒と徐々に待つ
            print(f"  {what}に失敗（一時的な障害の可能性）。"
                  f"{sleep_sec}秒待って再試行します [{attempt}/{attempts - 1}]: {e}")
            time.sleep(sleep_sec)


def open_sheet(spreadsheet_id: str = None, attempts: int = 3, wait: int = 5):
    """1枚目のシートを返す。"""
    spreadsheet_id = spreadsheet_id or os.getenv("SPREADSHEET_ID")
    if not spreadsheet_id:
        raise RuntimeError(
            "SPREADSHEET_ID が未設定です。環境変数（~/.zshrc または "
            "GitHub Actions の secrets）を確認してください")

    def _open():
        creds = Credentials.from_service_account_file(
            "credentials.json", scopes=SCOPES)
        client = gspread.authorize(creds)
        return client.open_by_key(spreadsheet_id).sheet1

    return _with_retry("シート取得", _open, attempts, wait)


def get_all_values_with_retry(sheet, attempts: int = 3, wait: int = 5):
    """全行を読み取る。一時的な障害はリトライする。"""
    return _with_retry("シート読み取り", sheet.get_all_values, attempts, wait)


def update_cell_with_retry(sheet, row: int, col: int, value,
                           attempts: int = 3, wait: int = 5):
    """セルを更新する。一時的な障害はリトライする。"""
    return _with_retry(f"セル更新（行{row}）",
                       lambda: sheet.update_cell(row, col, value),
                       attempts, wait)
