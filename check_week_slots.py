#!/usr/bin/env python3
"""翌週の投稿スロットのうち、まだ作成されていない「空き枠」を調べる。

weekly-dashboard-update の週次タスクから呼ばれる。
スプレッドシート（投稿予約の正）を見て、すでに作成済みのスロットを
二重に作らないようにするためのもの。

使い方:
    /usr/bin/python3 check_week_slots.py              # 翌週（月〜日）を調べる
    /usr/bin/python3 check_week_slots.py --json       # 機械可読出力
    /usr/bin/python3 check_week_slots.py --week-start 2026-08-10
    /usr/bin/python3 check_week_slots.py --include-registered
        # 「確認待ち」の枠も作り直し対象に含める。新しいダッシュボード分析で
        # 登録済みの下書きを作り直したいときだけ使う。
        # 「承認済み」「投稿済み」は対象外（承認や公開を巻き戻さない）。

設計方針（重複作成を防ぐことを最優先にする）:
  * 空き / 登録済み の判定は **スプレッドシートだけ** で行う。
    A列に同じ日時の行があれば、ステータスが何であれ（空欄でも）「登録済み」とみなす。
  * 手元の content ファイルは判定に使わず、参考情報として添えるだけ。
    過去のworktreeに同じ `_generated_dir` の残骸が大量にあり、判定に使うと誤爆するため。
  * 少しでもおかしければ「空き」ではなく **異常終了（exit 2）** に倒す。
    シートが読めない・ヘッダーが違う・日時が読めない、はすべて中止。
    空き扱いにすると重複投稿を作ってしまうため。
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 投稿スロット（曜日, 時刻）。0=月曜。現行の運用は 月22:00 / 木21:00 / 金22:00。
SLOTS = [(0, "22:00"), (3, "21:00"), (4, "22:00")]
WEEKDAYS_JA = "月火水木金土日"

# A列の日時として受け付ける表記。Sheets側で書式が変わっても拾えるようにする。
# （strptime は %m/%d/%H の前ゼロ無しも受け付けるため "2026/8/3 22:00" も通る）
DATETIME_FORMATS = (
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
)

EXIT_ABORT = 2  # 異常終了。SKILL.md 側は「非ゼロなら中止」で扱う

# --include-registered を付けたときだけ「作り直してよい」とみなすステータス。
# 「確認待ち」はMIKIさんがまだ承認していない下書きなので上書きしてよい。
# 「承認済み」「未投稿」「投稿済み」は承認済み・公開済みなので絶対に作り直さない。
REWRITABLE_STATUSES = ("確認待ち",)


class SheetError(RuntimeError):
    """シートを信頼できる形で読めなかった。空き判定をしてはいけない状態。"""


def next_week_start(today: dt.date) -> dt.date:
    """今日を含む週の翌週の月曜日を返す。"""
    this_monday = today - dt.timedelta(days=today.weekday())
    return this_monday + dt.timedelta(days=7)


def parse_sheet_datetime(value: str):
    """A列の文字列を datetime にする。読めなければ None。"""
    text = value.strip()
    if not text:
        return None
    for fmt in DATETIME_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def load_sheet_reservations() -> tuple[dict, list]:
    """シートの予約を読む。

    戻り値: ({datetime: ステータス}, [読めなかったA列の値])
    信頼できない状態はすべて SheetError にする。
    """
    sys.path.insert(0, BASE_DIR)
    from load_env import load_from_zshrc

    load_from_zshrc()

    import gspread
    from google.oauth2.service_account import Credentials

    spreadsheet_id = os.getenv("SPREADSHEET_ID")
    if not spreadsheet_id:
        raise SheetError("SPREADSHEET_ID が環境変数にありません（~/.zshrc を確認）")

    creds = Credentials.from_service_account_file(
        os.path.join(BASE_DIR, "credentials.json"),
        scopes=[
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    sheet = gspread.authorize(creds).open_by_key(spreadsheet_id).sheet1
    rows = sheet.get_all_values()

    # ヘッダー検証。空シート・別タブを掴んだ場合をここで止める。
    if not rows or not rows[0] or rows[0][0].strip() != "投稿日時":
        head = rows[0][:3] if rows else "(空)"
        raise SheetError(f"ヘッダーが想定と違います（A1が『投稿日時』でない）: {head}")
    if len(rows) < 2:
        raise SheetError("データ行が0件です。シートが空か、別のタブを読んでいます")

    reservations: dict = {}
    unparsed: list = []
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        parsed = parse_sheet_datetime(row[0])
        if parsed is None:
            unparsed.append(row[0].strip())
            continue
        status = row[6].strip() if len(row) > 6 else ""
        # 同じ日時が複数行あるときは register_post.py と同じく最初の行を優先。
        # ただし空ステータスが先に来た場合は、非空の方を残す（見落としを避ける）。
        if parsed not in reservations or (not reservations[parsed] and status):
            reservations[parsed] = status
    return reservations, unparsed


def load_local_drafts() -> dict:
    """手元の content*.json の _generated_dir → ファイルパス一覧（参考情報のみ）。"""
    out: dict = {}
    patterns = [
        os.path.join(BASE_DIR, "content*.json"),
        os.path.join(BASE_DIR, ".claude", "worktrees", "*", "content*.json"),
    ]
    for pattern in patterns:
        for path in sorted(glob.glob(pattern)):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:  # noqa: BLE001 - 壊れたJSON1個で週次ジョブを落とさない
                continue
            if not isinstance(data, dict):
                continue
            gen_dir = data.get("_generated_dir")
            if gen_dir:
                out.setdefault(gen_dir, []).append(os.path.relpath(path, BASE_DIR))
    return out


def build_report(week_start: dt.date, reservations: dict, drafts: dict,
                 include_registered: bool = False) -> dict:
    """スロットごとの状態を組み立てる。

    include_registered=True のときは「確認待ち」の枠も作り直し対象（free）にする。
    承認済み・投稿済みは対象外のまま（承認や公開を巻き戻さないため）。
    """
    # 同じ日に別時刻の予約が入っていないかも見る（スロット時刻は過去に変わっている）
    by_date: dict = {}
    for when, status in reservations.items():
        by_date.setdefault(when.date(), []).append((when, status))

    slots = []
    for weekday, time_str in SLOTS:
        day = week_start + dt.timedelta(days=weekday)
        hour, minute = (int(x) for x in time_str.split(":"))
        slot_dt = dt.datetime.combine(day, dt.time(hour, minute))
        post_datetime = f"{day:%Y/%m/%d} {time_str}"
        gen_dir = f"{day:%Y-%m-%d}-{time_str.replace(':', '')}"

        status = reservations.get(slot_dt)
        same_day = [(w, s) for w, s in by_date.get(day, []) if w != slot_dt]
        local = drafts.get(gen_dir, [])

        if status is not None:
            if include_registered and status in REWRITABLE_STATUSES:
                state = "free"
                note = f"作り直し対象（{status}・未承認のため上書きしてよい）"
            else:
                state = "registered"
                note = f"シート登録済み（{status or 'ステータス空欄'}）"
                if include_registered:
                    note += " → 承認済み・公開済みのため作り直さない"
        elif same_day:
            # 同じ日の別時刻に予約がある＝スロット時刻の変更後に作られた可能性
            state = "registered"
            others = "／".join(f"{w:%H:%M}（{s or '空欄'}）" for w, s in same_day)
            note = f"同じ日の別時刻に登録あり: {others} → 作成しない"
        else:
            state = "free"
            note = "空き"
            if local:
                note += f" ※手元に content あり（{', '.join(local)}）作成前に中身を確認"

        slots.append({
            "post_datetime": post_datetime,
            "weekday": WEEKDAYS_JA[weekday],
            "generated_dir": gen_dir,
            "state": state,
            "has_local_draft": bool(local),
            "note": note,
        })
    return {
        "week_start": week_start.isoformat(),
        "week_end": (week_start + dt.timedelta(days=6)).isoformat(),
        "slots": slots,
        "free_count": sum(1 for s in slots if s["state"] == "free"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="翌週の投稿スロットの空きを調べる")
    parser.add_argument("--week-start", help="週の起点（月曜, YYYY-MM-DD）。省略時は翌週")
    parser.add_argument("--json", action="store_true", help="JSONで出力する")
    parser.add_argument("--include-registered", action="store_true",
                        help="「確認待ち」の枠も作り直し対象にする（承認済み・投稿済みは除く）")
    args = parser.parse_args()

    today = dt.date.today()
    this_monday = today - dt.timedelta(days=today.weekday())

    if args.week_start:
        try:
            week_start = dt.date.fromisoformat(args.week_start)
        except ValueError as exc:
            print(f"❌ --week-start が不正です: {exc}", file=sys.stderr)
            return EXIT_ABORT
        if week_start.weekday() != 0:
            print(f"❌ --week-start は月曜日を指定してください（{args.week_start} は"
                  f"{WEEKDAYS_JA[week_start.weekday()]}曜）", file=sys.stderr)
            return EXIT_ABORT
    else:
        week_start = next_week_start(today)

    # 過去の週を対象にしない。過去日時で登録すると post_scheduler.py が即座に投稿するため。
    if week_start < this_monday:
        print(f"❌ 過去の週は対象にできません（指定: {week_start} / 今週: {this_monday}）。",
              file=sys.stderr)
        print("   過去日時で登録すると次回のスケジューラ実行で即座に投稿されます。",
              file=sys.stderr)
        return EXIT_ABORT

    try:
        reservations, unparsed = load_sheet_reservations()
    except Exception as exc:  # noqa: BLE001 - 失敗理由をそのまま見せたい
        print(f"❌ スプレッドシートを信頼できる形で読めませんでした: {exc}", file=sys.stderr)
        print("   空き枠の判定ができないため中止します（重複作成を防ぐため）。", file=sys.stderr)
        return EXIT_ABORT

    if unparsed:
        # 日時が読めない行は「予約が無い」ことにされてしまうので、黙って捨てない。
        print(f"❌ A列の日時として読めない行が {len(unparsed)}件あります: "
              f"{unparsed[:5]}{' ...' if len(unparsed) > 5 else ''}", file=sys.stderr)
        print("   誤って空き枠と判定する恐れがあるため中止します。"
              "シートのA列の書式を YYYY/MM/DD HH:MM に直してください。", file=sys.stderr)
        return EXIT_ABORT

    report = build_report(week_start, reservations, load_local_drafts(),
                          include_registered=args.include_registered)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"対象週: {week_start:%Y/%m/%d}(月) 〜 {week_start + dt.timedelta(days=6):%Y/%m/%d}(日)")
    print(f"シート参照: 予約{len(reservations)}件"
          + ("  ※--include-registered: 確認待ちの枠も作り直す\n" if args.include_registered else "\n"))
    for s in report["slots"]:
        mark = "🆕" if s["state"] == "free" else "✅"
        print(f"  {mark} {s['post_datetime']}({s['weekday']})  {s['note']}")

    print()
    free = [s for s in report["slots"] if s["state"] == "free"]
    if free:
        print(f"→ 作成が必要な枠: {len(free)}件")
        for s in free:
            print(f"     {s['post_datetime']}  (--post-datetime にこの文字列をそのまま渡す)")
        if any(s["has_local_draft"] for s in free):
            print("\n  ⚠️  手元に content が残っている枠があります。"
                  "過去のworktreeの残骸のことが多いので、作り直す前に中身を確認してください。")
    else:
        print("→ 作成が必要な枠はありません。すべて作成済みです。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(EXIT_ABORT)
    except Exception as exc:  # noqa: BLE001 - 想定外も必ず「中止」に倒す
        print(f"❌ 想定外のエラー: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(EXIT_ABORT)
