import time
import requests
import os

from load_env import load_from_zshrc
load_from_zshrc()

_USER_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN")
ACCOUNT_ID = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
API_BASE = "https://graph.facebook.com/v19.0"

_page_token_cache = None


def _get_access_token() -> str:
    """Instagram Content Publishing に必要な Page Access Token を返す。
    環境変数 INSTAGRAM_ACCESS_TOKEN（ユーザートークン）から
    紐づくページトークンを Graph API 経由で取得してキャッシュする。
    .env への書き込みや永続化は行わない。"""
    global _page_token_cache
    if _page_token_cache:
        return _page_token_cache

    res = requests.get(
        f"{API_BASE}/me/accounts",
        params={"access_token": _USER_TOKEN}
    )
    pages = res.json().get("data", [])
    for page in pages:
        ig_res = requests.get(
            f"{API_BASE}/{page['id']}",
            params={"fields": "instagram_business_account", "access_token": page["access_token"]}
        )
        ig_id = ig_res.json().get("instagram_business_account", {}).get("id")
        if ig_id == ACCOUNT_ID:
            _page_token_cache = page["access_token"]
            return _page_token_cache

    if pages:
        _page_token_cache = pages[0]["access_token"]
        return _page_token_cache

    return _USER_TOKEN


def create_image_container(image_url: str, caption: str) -> str:
    """画像投稿用コンテナを作成してcontainer_idを返す"""
    url = f"{API_BASE}/{ACCOUNT_ID}/media"
    params = {
        "image_url": image_url,
        "caption": caption,
        "access_token": _get_access_token()
    }
    res = requests.post(url, params=params)
    data = res.json()
    if "id" not in data:
        raise Exception(f"コンテナ作成失敗: {data}")
    return data["id"]


def create_video_container(video_url: str, caption: str) -> str:
    """リール動画投稿用コンテナを作成してcontainer_idを返す"""
    url = f"{API_BASE}/{ACCOUNT_ID}/media"
    params = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": _get_access_token()
    }
    res = requests.post(url, params=params)
    data = res.json()
    if "id" not in data:
        raise Exception(f"動画コンテナ作成失敗: {data}")
    return data["id"]


def _wait_for_container_ready(container_id: str, timeout: int = 120, interval: int = 10):
    """コンテナのstatus_codeがFINISHEDになるまでポーリングする"""
    # コンテナ（メディアオブジェクト）はIGユーザー所有のため、status_code の
    # 読み取りにはユーザートークンが必要（ページトークンだと Authorization
    # Error code=100 / subcode=33 になり status が空のままタイムアウトする）。
    url = f"{API_BASE}/{container_id}"
    params = {"fields": "status_code", "access_token": _USER_TOKEN}
    elapsed = 0
    while elapsed < timeout:
        res = requests.get(url, params=params)
        status = res.json().get("status_code", "")
        print(f"  コンテナステータス: {status}（{elapsed}秒経過）")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise Exception(f"コンテナ処理エラー: {res.json()}")
        time.sleep(interval)
        elapsed += interval
    raise Exception(f"コンテナ準備タイムアウト（{timeout}秒）: status={status}")


def publish_container(container_id: str) -> str:
    """コンテナを公開してpost_idを返す"""
    _wait_for_container_ready(container_id)
    url = f"{API_BASE}/{ACCOUNT_ID}/media_publish"
    # publish もコンテナ読み取りと同様にユーザートークンで実行する。
    params = {
        "creation_id": container_id,
        "access_token": _USER_TOKEN
    }
    res = requests.post(url, params=params)
    data = res.json()
    if "id" not in data:
        raise Exception(f"投稿公開失敗: {data}")
    return data["id"]


def post_image(image_url: str, caption: str) -> str:
    """画像を投稿してpost_idを返す"""
    container_id = create_image_container(image_url, caption)
    post_id = publish_container(container_id)
    return post_id


def post_video(video_url: str, caption: str) -> str:
    """動画（リール）を投稿してpost_idを返す"""
    container_id = create_video_container(video_url, caption)
    post_id = publish_container(container_id)
    return post_id


def _api_post_with_retry(url: str, params: dict, label: str, max_retries: int = 3) -> dict:
    """POSTリクエストを最大max_retries回リトライする（指数バックオフ）"""
    last_exc = None
    for attempt in range(1, max_retries + 1):
        res = requests.post(url, params=params)
        data = res.json()
        if "id" in data:
            return data
        last_exc = data
        if attempt < max_retries:
            wait = 5 * (2 ** (attempt - 1))
            print(f"  {label} 失敗（試行{attempt}/{max_retries}）→ {wait}秒後リトライ: {data}")
            time.sleep(wait)
    raise Exception(f"{label}: {last_exc}")


def create_carousel_item(image_url: str) -> str:
    """カルーセルの各画像コンテナを作成してidを返す"""
    url = f"{API_BASE}/{ACCOUNT_ID}/media"
    params = {
        "image_url": image_url,
        "is_carousel_item": "true",
        "access_token": _get_access_token()
    }
    data = _api_post_with_retry(url, params, "カルーセルアイテム作成失敗")
    return data["id"]


def post_carousel(image_urls: list, caption: str) -> str:
    """カルーセル（複数画像）を投稿してpost_idを返す"""
    item_ids = []
    for i, url in enumerate(image_urls, 1):
        print(f"  カルーセルアイテム {i}/{len(image_urls)} 作成中...")
        item_id = create_carousel_item(url)
        item_ids.append(item_id)

    url = f"{API_BASE}/{ACCOUNT_ID}/media"
    params = {
        "media_type": "CAROUSEL",
        "children": ",".join(item_ids),
        "caption": caption,
        "access_token": _get_access_token()
    }
    data = _api_post_with_retry(url, params, "カルーセルコンテナ作成失敗")

    post_id = publish_container(data["id"])
    return post_id
