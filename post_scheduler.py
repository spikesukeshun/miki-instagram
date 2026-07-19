import os
import requests
from datetime import datetime, timezone, timedelta
import time
from instagram_api import post_image, post_video, post_carousel
from instagram_mixed import post_mixed_carousel
from drive_helper import get_file_url
from line_notify import send_line_message
from register_post import delete_preview_from_github, delete_post_folder_from_github
from sheet_client import open_sheet, get_all_values_with_retry, update_cell_with_retry

from load_env import load_from_zshrc
load_from_zshrc()

JST = timezone(timedelta(hours=9))

# 列の定義
COL_DATETIME  = 0  # A: 投稿日時
COL_MENU      = 1  # B: メニュー種別
COL_FILENAME  = 2  # C: 画像ファイル名
COL_TEXT      = 3  # D: 投稿文
COL_HASHTAGS  = 4  # E: ハッシュタグ
COL_MEMO      = 5  # F: 投稿メモ
COL_STATUS    = 6  # G: ステータス
COL_PREVIEW   = 7  # H: プレビューURL


def get_sheet():
    return open_sheet()


def mark_status(sheet, row: int, value: str) -> bool:
    """ステータス列を更新する。失敗しても例外を投げない。

    ここで落とすと残りの行が丸ごと処理されなくなるため、記録できなかったことを
    ログに残して先へ進める。投稿失敗時の記録に使う場合、書けなければ行は
    「承認済み」のまま残り次回起動で再試行されるので、安全側に倒れる。
    """
    try:
        update_cell_with_retry(sheet, row, COL_STATUS + 1, value)
        return True
    except Exception as e:
        print(f"行{row}: ステータス更新に失敗 → {e}")
        return False


def build_caption(text: str, hashtags: str) -> str:
    caption = text.strip()
    if hashtags.strip():
        caption += f"\n\n{hashtags.strip()}"
    return caption


def is_video(filename: str) -> bool:
    return filename.lower().endswith((".mp4", ".mov"))


def check_token_expiry():
    """INSTAGRAM_ACCESS_TOKEN の有効期限を確認し、7日以内ならLINE通知する"""
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    if not token:
        return

    try:
        res = requests.get(
            "https://graph.facebook.com/debug_token",
            params={"input_token": token, "access_token": token},
            timeout=10,
        )
        data = res.json().get("data", {})

        if not data.get("is_valid", False):
            send_line_message(
                "⚠️ INSTAGRAM_ACCESS_TOKEN が無効です\n"
                "Graph API Explorer でトークンを再発行し、\n"
                "GitHub Secrets の INSTAGRAM_ACCESS_TOKEN を更新してください。"
            )
            print("警告: INSTAGRAM_ACCESS_TOKEN が無効です")
            return

        expires_at = data.get("expires_at")
        if not expires_at:
            # 有効期限なし（無期限トークン）はスキップ
            return

        now = datetime.now(timezone.utc)
        expire_dt = datetime.fromtimestamp(expires_at, tz=timezone.utc)
        days_left = (expire_dt - now).days

        print(f"トークン有効期限: {expire_dt.strftime('%Y/%m/%d')}（残り{days_left}日）")

        if days_left <= 7:
            send_line_message(
                f"⚠️ INSTAGRAM_ACCESS_TOKEN があと {days_left} 日で期限切れになります\n"
                f"期限: {expire_dt.astimezone(JST).strftime('%Y/%m/%d')}\n\n"
                f"Graph API Explorer でトークンを再発行し、\n"
                f"GitHub Secrets の INSTAGRAM_ACCESS_TOKEN を更新してください。"
            )
            print(f"警告: トークン残り{days_left}日 → LINE通知送信")

    except Exception as e:
        print(f"トークン有効期限チェックスキップ: {e}")


def run():
    check_token_expiry()

    sheet = get_sheet()
    rows = get_all_values_with_retry(sheet)
    now = datetime.now(JST).replace(tzinfo=None)  # JST時刻で比較（スプレッドシートの記録と統一）

    print(f"チェック開始: {now.strftime('%Y/%m/%d %H:%M')} JST")
    posted = 0

    for i, row in enumerate(rows[1:], start=2):
        if len(row) < 7:
            continue

        status = row[COL_STATUS].strip()

        # 「承認済み」「未投稿」は通常フロー
        # 「エラー：」は7日以内なら再試行（トークン更新後のリカバリ等）
        is_normal = status in ("承認済み", "未投稿")
        is_error_retry = status.startswith("エラー：")
        if not is_normal and not is_error_retry:
            continue

        datetime_str = row[COL_DATETIME].strip()
        try:
            post_time = datetime.strptime(datetime_str, "%Y/%m/%d %H:%M")
        except ValueError:
            print(f"行{i}: 日時フォーマットエラー → {datetime_str}")
            continue

        # エラー行は7日以内のものだけ再試行
        if is_error_retry:
            if post_time < now - timedelta(days=7):
                print(f"行{i}: エラー行（7日超）スキップ → {datetime_str}")
                continue
            print(f"行{i}: エラー行を再試行 → {datetime_str}")

        if post_time > now:
            print(f"行{i}: 投稿待機中 → {datetime_str}")
            continue

        filename = row[COL_FILENAME].strip()
        caption = build_caption(row[COL_TEXT], row[COL_HASHTAGS])

        print(f"行{i}: 投稿中 → {filename}")

        try:
            filenames = [f.strip() for f in filename.split(",")]

            if len(filenames) > 1:
                if any(is_video(f) for f in filenames):
                    items = [
                        {"type": "video" if is_video(f) else "image",
                         "url": get_file_url(f)}
                        for f in filenames
                    ]
                    post_id = post_mixed_carousel(items, caption)
                else:
                    image_urls = [get_file_url(f) for f in filenames]
                    post_id = post_carousel(image_urls, caption)
            elif is_video(filenames[0]):
                post_id = post_video(get_file_url(filenames[0]), caption)
            else:
                post_id = post_image(get_file_url(filenames[0]), caption)

        except FileNotFoundError as e:
            print(f"行{i}: ファイルなし → {e}")
            mark_status(sheet, i, "エラー：ファイルなし")
            send_line_message(
                f"❌ 投稿失敗（ファイルなし）\n"
                f"📅 {datetime_str}\n"
                f"エラー: {str(e)[:100]}"
            )
            continue
        except Exception as e:
            print(f"行{i}: 投稿失敗 → {e}")
            mark_status(sheet, i, f"エラー：{str(e)[:100]}")
            send_line_message(
                f"❌ 投稿失敗\n"
                f"📅 {datetime_str}\n"
                f"エラー: {str(e)[:300]}"
            )
            continue

        # --- ここから先はInstagramへの投稿が成功している ---
        # 以降の後始末で失敗しても「エラー：」を書いてはいけない。
        # エラー行は7日以内なら再試行されるため、同じ内容がもう一度投稿されてしまう。
        # 同じ理由で、後始末の例外でループを止めることもしない。
        recorded = mark_status(sheet, i, "投稿済み")

        print(f"行{i}: 投稿成功！ post_id={post_id}")
        posted += 1

        try:
            delete_preview_from_github(datetime_str)
        except Exception as e:
            print(f"行{i}: プレビュー削除に失敗（投稿は成功済み） → {e}")

        if recorded:
            send_line_message(
                f"✅ Instagram投稿完了\n"
                f"📅 {datetime_str}\n"
                f"🆔 post_id={post_id}"
            )
        else:
            send_line_message(
                f"⚠️ Instagram投稿は完了しましたがシートを更新できませんでした\n"
                f"📅 {datetime_str}\n"
                f"🆔 post_id={post_id}\n"
                f"二重投稿を防ぐため、該当行のステータスを手動で「投稿済み」に変更してください。"
            )

        # 投稿済みの画像はInstagram CDNにコピー済みなので、GitHub上のコピーを削除する
        slug = filenames[0].split("/")[0] if "/" in filenames[0] else ""
        if slug:
            time.sleep(2)  # プレビュー削除コミット直後の競合を避けるため少し待つ
            for attempt in range(1, 4):  # 最大3回リトライ
                try:
                    n = delete_post_folder_from_github(slug)
                    if n > 0:
                        print(f"行{i}: GitHub generated/{slug}/ から{n}ファイル削除（試行{attempt}）")
                        break
                    else:
                        print(f"行{i}: GitHub generated/{slug}/ にファイルなし（試行{attempt}）")
                        break
                except Exception as cleanup_err:
                    print(f"行{i}: GitHub掃除失敗（試行{attempt}/3）: {cleanup_err}")
                    if attempt < 3:
                        time.sleep(5 * attempt)  # 5秒、10秒と徐々に待つ

    print(f"完了！投稿数: {posted}件")


if __name__ == "__main__":
    run()
