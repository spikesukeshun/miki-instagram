import requests
import os
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN")
ACCOUNT_ID = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
API_BASE = "https://graph.instagram.com/v19.0"


def create_image_container(image_url: str, caption: str) -> str:
    """画像投稿用コンテナを作成してcontainer_idを返す"""
    url = f"{API_BASE}/{ACCOUNT_ID}/media"
    params = {
        "image_url": image_url,
        "caption": caption,
        "access_token": ACCESS_TOKEN
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
        "access_token": ACCESS_TOKEN
    }
    res = requests.post(url, params=params)
    data = res.json()
    if "id" not in data:
        raise Exception(f"動画コンテナ作成失敗: {data}")
    return data["id"]


def publish_container(container_id: str) -> str:
    """コンテナを公開してpost_idを返す"""
    url = f"{API_BASE}/{ACCOUNT_ID}/media_publish"
    params = {
        "creation_id": container_id,
        "access_token": ACCESS_TOKEN
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
