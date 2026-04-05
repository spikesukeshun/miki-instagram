import requests
from dotenv import load_dotenv
import os

load_dotenv()

def _get_user_ids() -> list:
    ids = []
    if os.getenv("LINE_USER_ID_SHUNSUKE"):
        ids.append(os.getenv("LINE_USER_ID_SHUNSUKE"))
    if os.getenv("LINE_USER_ID_MIKI"):
        ids.append(os.getenv("LINE_USER_ID_MIKI"))
    return ids

def send_line_message(message: str, user_ids: list = None):
    """LINEに通知を送る。user_ids省略時は.envの全ユーザーに送信"""
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    if not token:
        print("LINE_CHANNEL_ACCESS_TOKEN が設定されていません")
        return

    targets = user_ids or _get_user_ids()
    if not targets:
        print("送信先のLINEユーザーIDが設定されていません")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    for user_id in targets:
        res = requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers=headers,
            json={"to": user_id, "messages": [{"type": "text", "text": message}]}
        )
        if res.status_code != 200:
            print(f"LINE送信失敗 ({user_id}): {res.json()}")


def notify_revision_done(row_num: int, menu_type: str, instruction: str, preview_url: str):
    """修正完了通知"""
    message = (
        f"✅ 修正が完了しました\n"
        f"\n"
        f"📋 {menu_type}\n"
        f"修正内容: {instruction[:50]}{'...' if len(instruction) > 50 else ''}\n"
        f"\n"
        f"プレビューを確認してください👇\n"
        f"{preview_url}\n"
        f"\n"
        f"問題なければスプレッドシートで「承認済み」に変更してください"
    )
    send_line_message(message)


def notify_revision_found(row_num: int, menu_type: str, instruction: str):
    """修正依頼を検知した通知（Shunsukeのみ）"""
    shunsuke_id = os.getenv("LINE_USER_ID_SHUNSUKE")
    if not shunsuke_id:
        return
    message = (
        f"🔔 修正依頼を検知しました\n"
        f"\n"
        f"📋 {menu_type}（{row_num}行目）\n"
        f"指示: {instruction[:100]}{'...' if len(instruction) > 100 else ''}\n"
        f"\n"
        f"修正を開始します..."
    )
    send_line_message(message, user_ids=[shunsuke_id])
