"""Threads API クライアント（Threads 1か月実験用・2026-10 追加）。

Instagram の Graph API とは別物。ホストもトークンも別に発行される:
  - ホスト: https://graph.threads.net/v1.0
  - トークン: THREADS_ACCESS_TOKEN（Threads 用の Meta アプリで発行した長期トークン、60日）
  - ユーザーID: THREADS_USER_ID
INSTAGRAM_ACCESS_TOKEN は使えない（共用できる根拠が公式に無いため）。

投稿の流れ（公式 docs/threads/posts）:
  1. POST /{user}/threads でコンテナを作る（TEXT / IMAGE / VIDEO / CAROUSEL）
  2. GET /{container}?fields=status,error_message が FINISHED になるまで待つ
     （公式は「平均30秒待ってから公開」「確認は1分に1回・最大5分」を推奨）
  3. POST /{user}/threads_publish で公開
予約投稿のパラメータは API に無いので、時刻管理は threads_scheduler.py が行う。

トピックは topic_tag で1投稿に1つだけ付けられる（1〜50字、「.」「&」不可）。

単体実行:
  python3 threads_api.py --check     # トークン・ユーザー・投稿枠の確認（書き込みなし）
  python3 threads_api.py --refresh   # 長期トークンを更新して新トークンを表示（期限を60日延長）
"""

from __future__ import annotations

import argparse
import os
import time

import requests

from load_env import load_from_zshrc
load_from_zshrc()

API_BASE = "https://graph.threads.net/v1.0"
TEXT_LIMIT = 500          # 本文の上限（公式）。絵文字はUTF-8バイト数で数えられる
TOPIC_TAG_MAX = 50
CAROUSEL_MIN, CAROUSEL_MAX = 2, 20

# コンテナの処理待ち。公式推奨に合わせ、まず30秒待ってから確認する
INITIAL_WAIT_SEC = 30
POLL_INTERVAL_SEC = 15
POLL_TIMEOUT_SEC = 300


class ThreadsAPIError(Exception):
    pass


def _token() -> str:
    token = (os.getenv("THREADS_ACCESS_TOKEN") or "").strip()
    if not token:
        raise ThreadsAPIError(
            "THREADS_ACCESS_TOKEN が未設定です（~/.zshrc または GitHub secrets）")
    return token


def _user_id() -> str:
    uid = (os.getenv("THREADS_USER_ID") or "").strip()
    if not uid:
        raise ThreadsAPIError(
            "THREADS_USER_ID が未設定です（~/.zshrc または GitHub secrets）")
    return uid


def _parse(res: requests.Response) -> dict:
    try:
        data = res.json()
    except ValueError:
        raise ThreadsAPIError(f"不正な応答（HTTP {res.status_code}）")
    if isinstance(data, dict) and "error" in data:
        err = data["error"]
        raise ThreadsAPIError(
            f"{err.get('message', 'unknown error')} "
            f"(code={err.get('code')}, subcode={err.get('error_subcode')})")
    return data


def _get(path: str, params: dict = None) -> dict:
    params = dict(params or {})
    params["access_token"] = _token()
    res = requests.get(f"{API_BASE}/{path}", params=params, timeout=30)
    return _parse(res)


def _post(path: str, data: dict, attempts: int = 3) -> dict:
    """POST。通信エラーと5xxだけ再試行する（4xx は内容の誤りなので即失敗）。

    コンテナ作成は id が返らなければ何も作られていないので再試行してよい。
    公開（threads_publish）は二重公開を避けるため attempts=1 で呼ぶ。
    """
    data = dict(data)
    data["access_token"] = _token()
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            res = requests.post(f"{API_BASE}/{path}", data=data, timeout=60)
        except requests.exceptions.RequestException as e:
            last_error = ThreadsAPIError(f"通信エラー: {e}")
        else:
            if res.status_code < 500:
                return _parse(res)
            last_error = ThreadsAPIError(f"サーバーエラー（HTTP {res.status_code}）")
        if attempt < attempts:
            wait = 5 * attempt
            print(f"  Threads API POST {path} 失敗、{wait}秒後に再試行 [{attempt}/{attempts - 1}]: {last_error}")
            time.sleep(wait)
    raise last_error


# ── 投稿 ─────────────────────────────────────────────

def _is_emoji(ch: str) -> bool:
    cp = ord(ch)
    return (0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF
            or cp in (0xFE0F, 0x200D) or 0x1F1E6 <= cp <= 0x1F1FF)


def text_length(text: str) -> int:
    """Threads の文字数換算。公式は「絵文字はUTF-8のバイト数で数える」としているので、
    絵文字だけバイト数、それ以外（日本語を含む）は1文字=1で数える。"""
    return sum(len(ch.encode("utf-8")) if _is_emoji(ch) else 1 for ch in text)


def validate_topic_tag(tag: str) -> str | None:
    """topic_tag の形式エラーを返す（問題なければ None）。"""
    if not tag:
        return None
    if len(tag) > TOPIC_TAG_MAX:
        return f"topic_tag が{TOPIC_TAG_MAX}字を超えています（{len(tag)}字）"
    if "." in tag or "&" in tag:
        return "topic_tag に「.」「&」は使えません"
    if tag.startswith("#"):
        return "topic_tag に「#」は付けません"
    return None


def create_container(media_type: str, text: str = "", image_url: str = "",
                     video_url: str = "", children: list = None,
                     topic_tag: str = "", is_carousel_item: bool = False) -> str:
    data = {"media_type": media_type}
    if text:
        data["text"] = text
    if image_url:
        data["image_url"] = image_url
    if video_url:
        data["video_url"] = video_url
    if children:
        data["children"] = ",".join(children)
    if topic_tag and not is_carousel_item:
        data["topic_tag"] = topic_tag
    if is_carousel_item:
        data["is_carousel_item"] = "true"
    res = _post(f"{_user_id()}/threads", data)
    if "id" not in res:
        raise ThreadsAPIError(f"コンテナIDが返りません: {res}")
    return res["id"]


def wait_until_ready(container_id: str, timeout: int = POLL_TIMEOUT_SEC,
                     initial_wait: int = INITIAL_WAIT_SEC) -> None:
    """コンテナが FINISHED になるまで待つ。ERROR / EXPIRED / タイムアウトは例外。"""
    time.sleep(initial_wait)
    deadline = time.time() + timeout
    while True:
        info = _get(container_id, {"fields": "status,error_message"})
        status = info.get("status")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise ThreadsAPIError(
                f"コンテナ {container_id} が {status}: {info.get('error_message', '')}")
        if status == "PUBLISHED":
            raise ThreadsAPIError(f"コンテナ {container_id} は公開済みです（二重公開を防ぐため中止）")
        if time.time() >= deadline:
            raise ThreadsAPIError(f"コンテナ {container_id} の処理が{timeout}秒で終わりません（status={status}）")
        time.sleep(POLL_INTERVAL_SEC)


def publish(container_id: str) -> str:
    res = _post(f"{_user_id()}/threads_publish", {"creation_id": container_id}, attempts=1)
    if "id" not in res:
        raise ThreadsAPIError(f"公開IDが返りません: {res}")
    return res["id"]


def post_thread(text: str, media: list, topic_tag: str = "") -> str:
    """Threads に1投稿する。media は [{"type": "IMAGE"|"VIDEO", "url": ...}, ...]。

    0件=テキスト、1件=単体、2件以上=カルーセル。公開後の Threads 投稿IDを返す。
    """
    if text_length(text) > TEXT_LIMIT:
        raise ThreadsAPIError(f"本文が{TEXT_LIMIT}字を超えています（{text_length(text)}字換算）")
    err = validate_topic_tag(topic_tag)
    if err:
        raise ThreadsAPIError(err)
    if len(media) > CAROUSEL_MAX:
        raise ThreadsAPIError(f"メディアは{CAROUSEL_MAX}件までです（{len(media)}件）")

    if not media:
        cid = create_container("TEXT", text=text, topic_tag=topic_tag)
    elif len(media) == 1:
        m = media[0]
        cid = create_container(
            m["type"], text=text, topic_tag=topic_tag,
            image_url=m["url"] if m["type"] == "IMAGE" else "",
            video_url=m["url"] if m["type"] == "VIDEO" else "")
    else:
        child_ids = []
        for m in media:
            child = create_container(
                m["type"], is_carousel_item=True,
                image_url=m["url"] if m["type"] == "IMAGE" else "",
                video_url=m["url"] if m["type"] == "VIDEO" else "")
            child_ids.append(child)
        for child in child_ids:
            wait_until_ready(child, initial_wait=5)
        cid = create_container("CAROUSEL", text=text, children=child_ids, topic_tag=topic_tag)

    wait_until_ready(cid)
    return publish(cid)


def get_post(media_id: str) -> dict:
    return _get(media_id, {"fields": "id,permalink,timestamp,media_type,topic_tag"})


# ── インサイト ───────────────────────────────────────

MEDIA_METRICS = ["views", "likes", "replies", "reposts", "quotes", "shares"]
USER_METRICS = ["views", "likes", "replies", "reposts", "quotes", "clicks", "followers_count"]


def _metric_value(item: dict):
    """メトリクス1件の値を取り出す。形式が3種類ある（公式 docs/threads/insights）。"""
    if "total_value" in item:
        return item["total_value"].get("value")
    if "link_total_values" in item:
        return {v.get("link_url", ""): v.get("value", 0) for v in item["link_total_values"]}
    values = item.get("values") or []
    if item.get("name") == "views" and item.get("period") == "day":
        return [{"date": v.get("end_time", "")[:10], "value": v.get("value", 0)} for v in values]
    return values[0].get("value") if values else None


def _get_metrics(path: str, metrics: list, extra: dict = None) -> dict:
    """まとめて取り、失敗したら1件ずつ取り直す（未提供のメトリクスで全滅させない）。

    投稿単位の views / shares は公式に "in development" と書かれており、
    取れない可能性がある。取れなかったものは結果に含めず _missing に名前を残す。
    """
    params = dict(extra or {})
    try:
        data = _get(path, {**params, "metric": ",".join(metrics)})
        return {i["name"]: _metric_value(i) for i in data.get("data", [])}
    except ThreadsAPIError as e:
        print(f"  ⚠ インサイト一括取得に失敗: {e} → 1件ずつ取り直します")
    result, missing = {}, []
    for m in metrics:
        try:
            data = _get(path, {**params, "metric": m})
            for i in data.get("data", []):
                result[i["name"]] = _metric_value(i)
        except ThreadsAPIError:
            missing.append(m)
    if missing:
        result["_missing"] = missing
    return result


def get_media_insights(media_id: str) -> dict:
    return _get_metrics(f"{media_id}/insights", MEDIA_METRICS)


def get_user_insights(since: int = None, until: int = None) -> dict:
    """アカウント単位。views はプロフィール閲覧数（公式の定義）で日別に返る。
    followers_count は since/until 非対応なので別に取る。"""
    extra = {}
    if since:
        extra["since"] = since
    if until:
        extra["until"] = until
    ranged = [m for m in USER_METRICS if m != "followers_count"]
    result = _get_metrics(f"{_user_id()}/threads_insights", ranged, extra)
    result.update(_get_metrics(f"{_user_id()}/threads_insights", ["followers_count"]))
    return result


# ── トークン・枠 ─────────────────────────────────────

def publishing_limit() -> dict:
    data = _get(f"{_user_id()}/threads_publishing_limit", {"fields": "quota_usage,config"})
    return (data.get("data") or [{}])[0]


def refresh_token() -> dict:
    """長期トークンを更新する（有効期限を60日に戻す）。新しいトークンを返すだけで保存はしない。"""
    res = requests.get(f"{API_BASE}/refresh_access_token",
                       params={"grant_type": "th_refresh_token", "access_token": _token()},
                       timeout=30)
    return _parse(res)


def check() -> dict:
    me = _get("me", {"fields": "id,username"})
    if str(me.get("id")) != _user_id():
        raise ThreadsAPIError(
            f"トークンのユーザー（{me.get('username')} / {me.get('id')}）と "
            f"THREADS_USER_ID が一致しません")
    return {"user": me, "publishing_limit": publishing_limit()}


def main():
    parser = argparse.ArgumentParser(description="Threads API の接続確認・トークン更新")
    parser.add_argument("--check", action="store_true", help="トークン・ユーザー・投稿枠を確認（書き込みなし）")
    parser.add_argument("--refresh", action="store_true", help="長期トークンを更新して表示する")
    args = parser.parse_args()
    if args.refresh:
        data = refresh_token()
        days = int(data.get("expires_in", 0)) // 86400
        print(f"新しいトークン（有効 約{days}日）。~/.zshrc と GitHub secrets の "
              f"THREADS_ACCESS_TOKEN を置き換えてください:\n{data.get('access_token')}")
        return
    info = check()
    print(f"✅ 接続OK: @{info['user'].get('username')} (id={info['user'].get('id')})")
    print(f"   24時間の投稿枠: {info['publishing_limit']}")


if __name__ == "__main__":
    main()
