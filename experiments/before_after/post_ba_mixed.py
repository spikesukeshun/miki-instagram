"""動画混在カルーセル投稿（試作版）。

Meta Graph API のカルーセルは IMAGE と VIDEO を混在できる。
本流の instagram_api.py には手を加えず、ここに独立した関数として実装する。
import で借りているのは _get_access_token / _wait_for_container_ready / _api_post_with_retry
（いずれも instagram_api.py 内に存在）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from instagram_api import (  # noqa: E402
    API_BASE,
    ACCOUNT_ID,
    _get_access_token,
    _wait_for_container_ready,
    _api_post_with_retry,
    publish_container,
)

from experiments.before_after.ba_helpers import (  # noqa: E402
    IMAGE_SLIDE_TYPES,
    VIDEO_SLIDE_TYPES,
)


def create_carousel_image_item(image_url: str) -> str:
    """カルーセル子コンテナ（画像）を作成。本流の create_carousel_item と同等。"""
    url = f"{API_BASE}/{ACCOUNT_ID}/media"
    params = {
        "image_url": image_url,
        "is_carousel_item": "true",
        "access_token": _get_access_token(),
    }
    data = _api_post_with_retry(url, params, "BA カルーセル画像アイテム作成失敗")
    return data["id"]


def create_carousel_video_item(video_url: str) -> str:
    """カルーセル子コンテナ（動画）を作成。

    Meta Graph API では media_type=VIDEO + is_carousel_item=true で
    カルーセル用の動画コンテナが作れる。リール用の REELS とは別ルート。
    """
    url = f"{API_BASE}/{ACCOUNT_ID}/media"
    params = {
        "media_type": "VIDEO",
        "video_url": video_url,
        "is_carousel_item": "true",
        "access_token": _get_access_token(),
    }
    data = _api_post_with_retry(url, params, "BA カルーセル動画アイテム作成失敗")
    return data["id"]


def post_mixed_carousel(items: list[dict], caption: str, *, dry_run: bool = False) -> str | None:
    """画像・動画混在のカルーセルを投稿する。

    items: [{"type":"image","url":"https://..."}, {"type":"video","url":"https://..."}, ...]
    dry_run=True の場合は子コンテナの作成までで止め、child IDs を表示して None を返す。
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

    # 動画は処理に時間がかかるので、各子コンテナの FINISHED を待つ
    print("  各子コンテナの FINISHED を待機...")
    for cid in item_ids:
        _wait_for_container_ready(cid, timeout=300, interval=10)

    if dry_run:
        print("  [dry-run] CAROUSEL 親コンテナ作成 / publish はスキップしました")
        return None

    parent_url = f"{API_BASE}/{ACCOUNT_ID}/media"
    parent_params = {
        "media_type": "CAROUSEL",
        "children": ",".join(item_ids),
        "caption": caption,
        "access_token": _get_access_token(),
    }
    parent_data = _api_post_with_retry(
        parent_url, parent_params, "BA カルーセル親コンテナ作成失敗"
    )
    post_id = publish_container(parent_data["id"])
    print(f"  公開完了: post_id={post_id}")
    return post_id


def _items_from_content(content: dict) -> list[dict]:
    """content_ba.json の slides から API へ渡す items に変換する。

    ba_helpers.IMAGE_SLIDE_TYPES / VIDEO_SLIDE_TYPES の集合に従い、
    全画像系スライドは image_url、video_passthrough は video_url を取り出す。
    新スライド type を追加するときは ba_helpers の集合を更新するだけで両方追従する。
    """
    items = []
    for s in content.get("slides", []):
        t = s.get("type")
        if t in IMAGE_SLIDE_TYPES:
            url = s.get("image_url")
            if not url:
                raise ValueError(
                    f"{t} スライドに image_url が無いため publish できない: {s.get('filename_out')}"
                )
            items.append({"type": "image", "url": url})
        elif t in VIDEO_SLIDE_TYPES:
            url = s.get("video_url")
            if not url:
                raise ValueError(
                    f"{t} スライドに video_url が無いため publish できない: {s.get('filename_out')}"
                )
            items.append({"type": "video", "url": url})
        else:
            raise ValueError(f"未対応スライド type: {t}")
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--content", required=True, help="content_ba.json のパス")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="子コンテナ作成までで止め、publish しない",
    )
    args = ap.parse_args()

    with open(args.content, "r", encoding="utf-8") as f:
        content = json.load(f)

    items = _items_from_content(content)
    caption = content.get("caption", "")
    post_mixed_carousel(items, caption, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
