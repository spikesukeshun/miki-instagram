"""リール設計システムの共通設定（パス・Drive・台帳の場所）。"""

from __future__ import annotations

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REELS_DIR = REPO_ROOT / "reels"

# お客様の映像や解析結果を置く作業場所。公開リポジトリなので git に入れない（.gitignore 済み）
WORK_DIR = REELS_DIR / "work"
ASSETS_WORK_DIR = WORK_DIR / "assets"
PLANS_DIR = WORK_DIR / "plans"

# Drive のフォルダID（秘密情報ではない。drive_folders.json と同じ扱いでコミットする）
DRIVE_CONFIG_PATH = REELS_DIR / "drive_config.json"

# 素材台帳は投稿管理スプレッドシートの「別タブ」に置く。
# サービスアカウントは保存容量が0でスプレッドシートを新規作成できないため
# （2026-09-17 に作成を試して storageQuotaExceeded を確認）。
# 投稿用の1枚目のシート（A〜H列固定）には絶対に触れない。
CATALOG_TAB = "リール素材台帳"
BA_TAB = "BA登録"

GOOGLE_SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]


def credentials_path() -> Path:
    return REPO_ROOT / "credentials.json"


def catalog_spreadsheet_id() -> str:
    """台帳を置くスプレッドシートのID。

    専用のスプレッドシートに移したい場合は REELS_CATALOG_SPREADSHEET_ID を設定する
    （そのファイルをサービスアカウントに編集者として共有しておくこと）。
    未設定なら投稿管理スプレッドシート（SPREADSHEET_ID）の別タブを使う。
    """
    sid = os.getenv("REELS_CATALOG_SPREADSHEET_ID") or os.getenv("SPREADSHEET_ID")
    if not sid:
        raise RuntimeError(
            "REELS_CATALOG_SPREADSHEET_ID も SPREADSHEET_ID も未設定です（~/.zshrc を確認）")
    return sid


def load_drive_config() -> dict:
    if not DRIVE_CONFIG_PATH.exists():
        raise RuntimeError(
            f"{DRIVE_CONFIG_PATH.name} がありません。先に python3 -m reels.drive_setup を実行してください")
    with open(DRIVE_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_drive_config(config: dict) -> None:
    with open(DRIVE_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")
