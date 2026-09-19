"""素材の受け皿を作る（フェーズ0）。何度実行しても同じ状態になる。

  python3 -m reels.drive_setup            # Driveのフォルダと台帳タブを用意して drive_config.json を書く
  python3 -m reels.drive_setup --check    # 何も作らず、今の状態だけ表示する

Drive の構成（「instagram投稿素材」フォルダの中）:
  リール素材/
    01_動画・写真の受付/        ← 写真など、動画以外をアップロードする場所
    02_ボイスメモの受付/        ← フェーズ4（ナレーション）で使う。今は置き場だけ
  動画/                          ← 実写動画の入口。既にあるフォルダを取り込み元として登録し、
                                   これから撮ってもらう分もここに入れてもらう

ファイルは移動しない（誰が取り込んだかは台帳の DriveファイルID で管理する）。
サービスアカウントは保存容量が0なので、ここで作れるのはフォルダとタブだけ。
"""

from __future__ import annotations

import argparse
import json
import sys

from reels import config

ROOT_NAME = "リール素材"
INTAKE_NAME = "01_動画・写真の受付"
VOICE_NAME = "02_ボイスメモの受付"
# 2026-09-17 時点で動画が置かれていた既存フォルダ（取り込み元に含める）
EXISTING_VIDEO_FOLDER_NAME = "動画"

FOLDER_MIME = "application/vnd.google-apps.folder"


def _drive():
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    creds = Credentials.from_service_account_file(
        str(config.credentials_path()), scopes=["https://www.googleapis.com/auth/drive"])
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _posting_materials_folder_id(svc) -> str:
    """既存のテーマ別フォルダ（drive_folders.json）の親＝「instagram投稿素材」を探す。"""
    with open(config.REPO_ROOT / "drive_folders.json", encoding="utf-8") as f:
        theme_folders = json.load(f)
    parents = set()
    for folder_id in theme_folders.values():
        meta = svc.files().get(fileId=folder_id, fields="parents").execute()
        parents.update(meta.get("parents", []))
    if len(parents) != 1:
        raise RuntimeError(f"テーマ別フォルダの親が1つに決まりません: {parents}")
    return parents.pop()


def _find_child_folder(svc, parent_id: str, name: str) -> str | None:
    escaped = name.replace("'", "\\'")
    res = svc.files().list(
        q=f"'{parent_id}' in parents and name = '{escaped}' and mimeType = '{FOLDER_MIME}' and trashed = false",
        fields="files(id,name)").execute()
    files = res.get("files", [])
    return files[0]["id"] if files else None


def _ensure_folder(svc, parent_id: str, name: str, create: bool) -> str | None:
    folder_id = _find_child_folder(svc, parent_id, name)
    if folder_id or not create:
        return folder_id
    meta = svc.files().create(
        body={"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]},
        fields="id").execute()
    print(f"  作成: {name}")
    return meta["id"]


def setup(create: bool = True) -> dict:
    svc = _drive()
    parent_id = _posting_materials_folder_id(svc)
    root_id = _ensure_folder(svc, parent_id, ROOT_NAME, create)
    intake_id = _ensure_folder(svc, root_id, INTAKE_NAME, create) if root_id else None
    voice_id = _ensure_folder(svc, root_id, VOICE_NAME, create) if root_id else None
    existing_video_id = _find_child_folder(svc, parent_id, EXISTING_VIDEO_FOLDER_NAME)

    sources = []
    if intake_id:
        sources.append({"name": f"{ROOT_NAME}/{INTAKE_NAME}", "folder_id": intake_id})
    if existing_video_id:
        sources.append({"name": EXISTING_VIDEO_FOLDER_NAME, "folder_id": existing_video_id})

    cfg = {
        "posting_materials_folder_id": parent_id,
        "reel_root_folder_id": root_id,
        "intake_folder_id": intake_id,
        "voice_memo_folder_id": voice_id,
        "intake_sources": sources,
        "catalog_tab": config.CATALOG_TAB,
        "ba_tab": config.BA_TAB,
    }

    if create:
        from reels.catalog import BARegistry, Catalog, _open_spreadsheet
        spreadsheet = _open_spreadsheet()
        Catalog(spreadsheet)
        BARegistry(spreadsheet)
        print(f"  台帳タブ: 「{config.CATALOG_TAB}」「{config.BA_TAB}」")
        config.save_drive_config(cfg)
        print(f"  設定を保存: {config.DRIVE_CONFIG_PATH.relative_to(config.REPO_ROOT)}")
    return cfg


def main(argv=None):
    from load_env import load_from_zshrc
    load_from_zshrc()

    parser = argparse.ArgumentParser(description="リール素材の受け皿（Driveフォルダと台帳タブ）を用意する")
    parser.add_argument("--check", action="store_true", help="何も作らず状態だけ表示する")
    args = parser.parse_args(argv)

    cfg = setup(create=not args.check)
    for key in ("posting_materials_folder_id", "reel_root_folder_id", "intake_folder_id",
                "voice_memo_folder_id"):
        print(f"{key}: {cfg[key] or '（未作成）'}")
    for src in cfg["intake_sources"]:
        print(f"取り込み元: {src['name']} ({src['folder_id']})")
        print(f"  https://drive.google.com/drive/folders/{src['folder_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
