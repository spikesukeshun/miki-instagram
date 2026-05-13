"""画像・動画混在カルーセル投稿用ヘルパー。

instagram_api.py のプリミティブ（_get_access_token / _wait_for_container_ready /
_api_post_with_retry / publish_container）を再利用する。
post_scheduler.py から、ファイル名リストに .mp4 が含まれる場合に呼び出す。
"""
from __future__ import annotations

from instagram_api import (
    API_BASE,
    ACCOUNT_ID,
    _get_access_token,
    _wait_for_container_ready,
    _api_post_with_retry,
    publish_container,
)


def create_carousel_image_item(image_url: str) -> str:
    url = f"{API_BASE}/{ACCOUNT_ID}/media"
    params = {
        "image_url": image_url,
        "is_carousel_item": "true",
        "access_token": _get_access_token(),
    }
    data = _api_post_with_retry(url, params, "混在カルーセル画像アイテム作成失敗")
    return data["id"]


def create_carousel_video_item(video_url: str) -> str:
    url = f"{API_BASE}/{ACCOUNT_ID}/media"
    params = {
        "media_type": "VIDEO",
        "video_url": video_url,
        "is_carousel_item": "true",
        "access_token": _get_access_token(),
    }
    data = _api_post_with_retry(url, params, "混在カルーセル動画アイテム作成失敗")
    return data["id"]


def post_mixed_carousel(items: list[dict], caption: str, *, dry_run: bool = False) -> str | None:
    """画像・動画混在のカルーセルを投稿する。

    items: [{"type":"image","url":"..."}, {"type":"video","url":"..."}, ...]
    """
    if not items:
        raise ValueError("items が空です")

    item_ids: list[str] = []
    for i, it in enumerate(items, 1):
        kind = it.get("type")
        url = it.get("url")
        if not url:
            raise ValueError(f"items[{i - 1}].url が空です")
        print(f"  カルーセル子 {i}/{len(items)} ({kind}) コンテナ作成中... url={url}")
        if kind == "image":
            item_ids.append(create_carousel_image_item(url))
        elif kind == "video":
            item_ids.append(create_carousel_video_item(url))
        else:
            raise ValueError(f"未対応の type: {kind}")

    print(f"  子コンテナ ID: {item_ids}")
    print("  各子コンテナの FINISHED を待機...")
    for cid in item_ids:
        _wait_for_container_ready(cid, timeout=300, interval=10)

    if dry_run:
        print("  [dry-run] 親コンテナ作成 / publish はスキップしました")
        return None

    parent_url = f"{API_BASE}/{ACCOUNT_ID}/media"
    parent_params = {
        "media_type": "CAROUSEL",
        "children": ",".join(item_ids),
        "caption": caption,
        "access_token": _get_access_token(),
    }
    parent_data = _api_post_with_retry(
        parent_url, parent_params, "混在カルーセル親コンテナ作成失敗"
    )
    return publish_container(parent_data["id"])
