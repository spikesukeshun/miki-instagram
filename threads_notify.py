"""Threads 実験の LINE 通知（2026-10 追加）。

LINE Messaging API の無料枠（月200通）は Instagram の自動投稿と共有している。
Threads の自動運用でその枠を圧迫しないよう、次の3つで上限を決めている:

  1. 人の対応が必要なときだけ送る（投稿成功では送らない）
  2. 送り先は1人（NOTIFY_USER_ENV）。Instagram 側の2人宛てとは別
  3. 同じ種類×同じ対象は1日1回まで。さらに月の上限 MONTHLY_CAP 通（上限到達の案内1通を含む）

送信記録は LEDGER_FILE に残す。GitHub Actions では実行ごとに環境が消えるので、
threads.yml が actions/cache でこのファイルを次の実行へ引き継ぐ。
記録が読めない場合は「未送信」とみなして送る（通知を落とすより重複の方が安全なため）。

Instagram 側の通知処理（line_notify.py）は変更せず、send_line_message を
送り先を1人に絞って呼ぶだけ。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
LEDGER_FILE = os.path.join("threads", "notify_log.json")
NOTIFY_USER_ENV = "LINE_USER_ID_SHUNSUKE"
MONTHLY_CAP = 30
KEEP_DAYS = 40

# 通知の種類（同じ種類×同じ対象×同じ日 は1回だけ）
POST_FAILED = "post_failed"        # 投稿APIの失敗
HELD = "held"                      # 投稿前チェックで止めた（要確認）
RECORD_FAILED = "record_failed"    # 投稿は成功したがシートに記録できない（手で直す必要）
INSIGHTS_FAILED = "insights_failed"  # アカウントのインサイトが取れない（トークン切れの可能性）
TAB_UNSAFE = "tab_unsafe"          # Threads用タブが1枚目にある（Instagramと干渉するので停止）


def _load(path: str) -> list:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save(path: str, entries: list):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=0)


def notify(kind: str, target: str, message: str, now: datetime = None,
           path: str = None, sender=None) -> bool:
    """条件を満たすときだけ LINE を1人に送る。送ったら True。

    target は「何についての通知か」（例: 予定日時、日付）。同じ kind × target は1日1回。
    """
    now = now or datetime.now(JST)
    path = path or LEDGER_FILE
    today, month = now.strftime("%Y-%m-%d"), now.strftime("%Y-%m")
    cutoff = (now - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    entries = [e for e in _load(path) if e.get("date", "") >= cutoff]

    if any(e.get("date") == today and e.get("kind") == kind and e.get("target") == target
           for e in entries):
        print(f"  LINE通知は本日送信済みのため省略（{kind} / {target}）")
        return False
    sent_this_month = sum(1 for e in entries if e.get("date", "").startswith(month))
    if sent_this_month >= MONTHLY_CAP:
        print(f"  LINE通知は今月の上限（{MONTHLY_CAP}通）に達したため省略（{kind} / {target}）")
        return False
    if sent_this_month == MONTHLY_CAP - 1:
        message += (f"\n\n※ Threads の通知が今月の上限（{MONTHLY_CAP}通）に達しました。"
                    f"今月はこれ以降 LINE に送りません。GitHub Actions のログとシートを確認してください。")

    user = (os.getenv(NOTIFY_USER_ENV) or "").strip()
    if not user:
        print(f"  {NOTIFY_USER_ENV} が未設定のため LINE 通知を省略")
        return False
    if sender is None:
        from line_notify import send_line_message as sender
    from threads_api import redact
    try:
        ok = sender("【Threads】" + redact(message), user_ids=[user])
    except Exception as e:
        print(f"  LINE通知に失敗: {redact(e)}")
        return False
    if ok:
        entries.append({"date": today, "kind": kind, "target": target,
                        "at": now.strftime("%H:%M")})
        _save(path, entries)
    return bool(ok)
