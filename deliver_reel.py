"""リール動画をMIKIさんのLINEへ配信して、手動で投稿してもらうためのスクリプト。

Instagram Graph API では本体の音源ライブラリ（トレンド音源）をリールに付けられない。
音源の有無はリールの伸びを大きく左右するため、リールだけは自動投稿せず、
MIKIさんがInstagramアプリから音源を選んで投稿する運用にしている。

このスクリプトは以下をまとめて行う:
  1. 動画の途中フレームからサムネイルを作る（LINEの動画メッセージに必須）
  2. 動画とサムネイルを GitHub の generated/<slug>/ にアップロード
  3. MIKIさんのLINEへ「動画・手順・キャプション・代替テキスト」を送る
  4. シートのステータスを「手動投稿待ち」にする

「手動投稿待ち」は post_scheduler.py の自動投稿対象外（承認済み/未投稿/エラー以外は
スキップされる）で、check_week_slots.py からは枠が埋まっている扱いになる。
実際に投稿されたかどうかは post_scheduler.verify_manual_reels() が Graph API で確認する。

使い方:
    python3 deliver_reel.py --datetime "2026/08/21 21:00" \
                            --video ~/Desktop/美喜のinstagram/miki-profile-reel/reel_new.mp4 \
                            --content-file content_2026-08-21-2100.json
    # 文面とサムネイルだけ確認する
    python3 deliver_reel.py ... --dry-run
    # 自分のLINEにだけ送って実機確認する
    python3 deliver_reel.py ... --to-shunsuke-only
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime

import requests

from load_env import load_from_zshrc

load_from_zshrc()

from line_notify import send_line_message, send_line_video  # noqa: E402
from register_post import (  # noqa: E402
    GENERATED_DIR,
    GITHUB_PAGES_URL,
    _slug_from_datetime,
    update_spreadsheet_row,
    upload_path_to_github,
)
from sheet_client import get_all_values_with_retry, open_sheet  # noqa: E402

MANUAL_STATUS = "手動投稿待ち"
VIDEO_NAME = "reel.mp4"
THUMB_NAME = "reel_thumb.jpg"
THUMB_MAX_BYTES = 1024 * 1024  # LINEのプレビュー画像は1MBまで
WEEKDAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]

# 配信は GitHub Pages（docs/）から行う。raw.githubusercontent は mp4 を
# application/octet-stream で返すため、動画として取得できない可能性がある。
# Pages は拡張子どおり video/mp4 で返す（実測確認済み）。
DOCS_DIR = "docs"


def extract_thumbnail(video_path: str, out_path: str, at_sec: float = 0.5) -> str:
    """動画の指定秒地点から1フレーム抜き出してJPEGにする。

    0秒ではなく0.5秒地点を使うのは、冒頭のフェードインで1フレーム目が
    ほぼ白一色になり、サムネイルとして成立しないため。
    """
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    last_error = ""
    for quality in (3, 6, 9):  # 1MBを超えたら段階的に圧縮する
        cmd = [
            "ffmpeg", "-y", "-ss", str(at_sec), "-i", video_path,
            "-frames:v", "1", "-q:v", str(quality), out_path,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            last_error = res.stderr[-500:]
            continue
        size = os.path.getsize(out_path)
        if size <= THUMB_MAX_BYTES:
            print(f"  サムネイル作成: {out_path}（{size / 1024:.0f}KB・q={quality}）")
            return out_path
        print(f"  サムネイルが大きいので圧縮し直します（{size / 1024:.0f}KB・q={quality}）")
        last_error = f"1MBを超えたまま圧縮しきれませんでした（{size / 1024:.0f}KB）"
    raise RuntimeError(f"サムネイル作成に失敗しました: {last_error}")


def wait_until_reachable(url: str, expect_type: str, attempts: int = 6, wait: int = 3) -> None:
    """アップロードしたURLが実際に配信されるまで待つ。

    LINEは指定URLを自分で取りに行くため、到達できない状態で送ると
    MIKIさんの画面に壊れた動画が届く。送信前にここで止める。
    """
    for attempt in range(1, attempts + 1):
        try:
            res = requests.head(url, timeout=15, allow_redirects=True)
            content_type = res.headers.get("content-type", "")
            if res.status_code == 200 and content_type.startswith(expect_type):
                print(f"  配信URL確認OK: {url}")
                return
            detail = f"status={res.status_code} content-type={content_type or '不明'}"
        except requests.RequestException as e:
            detail = str(e)
        if attempt < attempts:
            print(f"  配信URLをまだ取得できません（{detail}）。{wait}秒待って再確認します")
            time.sleep(wait)
    raise RuntimeError(f"配信URLに到達できませんでした: {url}")


def find_sheet_row(post_datetime: str):
    """A列が post_datetime と一致する行を (行番号, 値のリスト) で返す。無ければ None。"""
    sheet = open_sheet()
    rows = get_all_values_with_retry(sheet)
    for i, row in enumerate(rows[1:], start=2):
        if row and row[0].strip() == post_datetime:
            return i, row
    return None


def load_texts(content_file: str, sheet_row: list) -> tuple:
    """キャプションとハッシュタグを content.json かシートから取る。

    alt_text は送らない。リールでは代替テキストの入力欄が出ないことが多く、
    このプロジェクトでもAPIに渡していないため、送ってもMIKIさんの手数が増えるだけ。
    """
    if content_file:
        with open(content_file, encoding="utf-8") as f:
            data = json.load(f)
        return (
            (data.get("caption") or "").strip(),
            (data.get("hashtags") or "").strip(),
        )
    if not sheet_row:
        return "", ""
    caption = sheet_row[3].strip() if len(sheet_row) > 3 else ""
    hashtags = sheet_row[4].strip() if len(sheet_row) > 4 else ""
    return caption, hashtags


def format_schedule(post_datetime: str) -> str:
    """'2026/08/21 21:00' → '8/21（木）21:00ごろ'"""
    dt = datetime.strptime(post_datetime, "%Y/%m/%d %H:%M")
    return f"{dt.month}/{dt.day}（{WEEKDAYS_JP[dt.weekday()]}）{dt.strftime('%H:%M')}ごろ"


def build_instruction(post_datetime: str) -> str:
    return (
        "🎬 リール動画ができました\n"
        "\n"
        f"【投稿予定】{format_schedule(post_datetime)}\n"
        "\n"
        "【手順】\n"
        "1. 上の動画を保存（右下の↓マーク）\n"
        "2. Instagram → リール → カメラロールからこの動画を選ぶ\n"
        "3. 音源から好きな曲を選んでください🎵\n"
        "　（曲名の横に矢印マークが付いている＝流行っている曲です）\n"
        "4. カバーは1秒目より後ろを選んでください\n"
        "　（冒頭は白く飛んでいます）\n"
        "5. 次のメッセージのキャプションをコピーして貼り付け\n"
        "6. シェア\n"
        "\n"
        "投稿が終わったらこちらで自動確認します。"
    )


def main():
    parser = argparse.ArgumentParser(description="リール動画をLINEでMIKIさんに配信する")
    parser.add_argument("--datetime", required=True,
                        help="投稿予定日時（例: '2026/08/21 21:00'）。シートのA列と一致させる")
    parser.add_argument("--video", required=True, help="リール動画（mp4）のパス")
    parser.add_argument("--content-file",
                        help="キャプション等を読む content.json。省略時はシートのD/E列を使う")
    parser.add_argument("--dry-run", action="store_true",
                        help="アップロード・LINE送信・シート更新をせず、文面とサムネイルだけ作る")
    parser.add_argument("--to-shunsuke-only", action="store_true",
                        help="MIKIさんには送らず、自分のLINEにだけ送って実機確認する")
    args = parser.parse_args()

    if not os.path.exists(args.video):
        sys.exit(f"動画が見つかりません: {args.video}")

    try:
        datetime.strptime(args.datetime, "%Y/%m/%d %H:%M")
    except ValueError:
        sys.exit(f"--datetime は 'YYYY/MM/DD HH:MM' 形式で指定してください: {args.datetime}")

    slug = _slug_from_datetime(args.datetime)
    dest_dir = os.path.join(GENERATED_DIR, slug)

    # シートの行が無いと配信後にステータスを記録できない。アップロード前に確かめる。
    # （--to-shunsuke-only は実機確認用でシートを触らないので、行が無くても続行する）
    found = None
    if not args.dry_run:
        found = find_sheet_row(args.datetime)
        if not found and not args.to_shunsuke_only:
            sys.exit(f"シートに {args.datetime} の行がありません。先に投稿枠を登録してください")
    sheet_row = found[1] if found else None

    caption, hashtags = load_texts(args.content_file, sheet_row)
    if not caption:
        sys.exit("キャプションが取得できませんでした（--content-file かシートのD列を確認してください）")

    print(f"リール配信の準備: {args.datetime}（{slug}）")

    # 動画を generated/<slug>/reel.mp4 に置く（投稿後の掃除がスラッグ単位のため）
    os.makedirs(dest_dir, exist_ok=True)
    video_dest = os.path.join(dest_dir, VIDEO_NAME)
    if os.path.abspath(args.video) != os.path.abspath(video_dest):
        shutil.copy(args.video, video_dest)
    print(f"  動画: {video_dest}（{os.path.getsize(video_dest) / 1024 / 1024:.1f}MB）")

    thumb_dest = os.path.join(dest_dir, THUMB_NAME)
    extract_thumbnail(video_dest, thumb_dest)

    caption_message = f"{caption}\n\n{hashtags}".strip()
    instruction = build_instruction(args.datetime)

    video_url = f"{GITHUB_PAGES_URL}/{slug}/{VIDEO_NAME}"
    thumb_url = f"{GITHUB_PAGES_URL}/{slug}/{THUMB_NAME}"

    if args.dry_run:
        print("\n--- LINEに送る文面（dry-run） ---")
        print(f"[1通目] 動画: {video_url}")
        print(f"        サムネ: {thumb_url}")
        print(f"[2通目]\n{instruction}")
        print(f"[3通目]\n{caption_message}")
        print("\ndry-run のためアップロード・送信・シート更新は行いませんでした")
        print(f"サムネイルを目視で確認してください: {thumb_dest}")
        return

    print("GitHub Pages にアップロード中...")
    upload_path_to_github(video_dest, f"{DOCS_DIR}/{slug}/{VIDEO_NAME}",
                          message=f"リール配信: {slug}")
    upload_path_to_github(thumb_dest, f"{DOCS_DIR}/{slug}/{THUMB_NAME}",
                          message=f"リール配信サムネイル: {slug}")

    # Pages はコミット後にビルドが走るため、公開まで数十秒かかる
    print("GitHub Pages の公開を待っています...")
    wait_until_reachable(video_url, "video/", attempts=20, wait=6)
    wait_until_reachable(thumb_url, "image/", attempts=20, wait=6)

    target_key = "LINE_USER_ID_SHUNSUKE" if args.to_shunsuke_only else "LINE_USER_ID_MIKI"
    target_id = (os.getenv(target_key) or "").strip()
    if not target_id:
        sys.exit(f"{target_key} が設定されていません")
    targets = [target_id]

    print(f"LINE送信中（{target_key}）...")
    if not send_line_video(video_url, thumb_url, user_ids=targets):
        sys.exit("動画の送信に失敗しました。シートは更新していません")

    # 動画だけ届いて手順やキャプションが欠けている状態に気づけるようにする
    failed = []
    if not send_line_message(instruction, user_ids=targets):
        failed.append("手順")
    if not send_line_message(caption_message, user_ids=targets):
        failed.append("キャプション")
    if failed:
        print(f"⚠️ 送信できなかったメッセージがあります: {', '.join(failed)}")

    if args.to_shunsuke_only:
        print("実機確認用の送信のみ完了しました（シートは更新していません）")
        return

    if update_spreadsheet_row(args.datetime, filename=f"{slug}/{VIDEO_NAME}",
                              status=MANUAL_STATUS):
        print(f"シートのステータスを「{MANUAL_STATUS}」にしました")
    else:
        print("⚠️ シートを更新できませんでした。手動でステータスを"
              f"「{MANUAL_STATUS}」に変更してください")

    shunsuke_id = (os.getenv("LINE_USER_ID_SHUNSUKE") or "").strip()
    if shunsuke_id:
        summary = ("📤 リール動画をMIKIさんに送りました\n"
                   f"📅 {format_schedule(args.datetime)}\n"
                   f"🎬 {video_url}")
        if failed:
            summary += f"\n⚠️ 送信できなかったメッセージ: {', '.join(failed)}"
        send_line_message(summary, user_ids=[shunsuke_id])

    print("配信完了。MIKIさんの投稿は次回のスケジューラ実行時に自動確認されます")


if __name__ == "__main__":
    main()
