"""Drive にアップロードされた動画・写真を取り込み、解析して台帳に載せる（フェーズ1）。

  python3 -m reels.ingest                          # 受付フォルダの新しいファイルを全部取り込む
  python3 -m reels.ingest --dry-run                # 何が取り込まれるかだけ表示
  python3 -m reels.ingest --force                  # 取り込み済みも解析し直す（人が書いた欄は残る）
  python3 -m reels.ingest --drive-file-id ID ...   # テーマ別フォルダの写真などを個別に台帳へ載せる

解析結果・一覧画像・代表フレームは reels/work/assets/<素材ID>/ に置く（git には入れない）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from reels import config
from reels.catalog import KIND_PHOTO, KIND_VIDEO, Catalog, asset_id_for, now_text
from reels.media_analysis import (MOTION_LABELS, analyze_photo, analyze_video,
                                  media_kind)

DRIVE_FIELDS = "id,name,mimeType,size,createdTime,modifiedTime,parents"


def _drive():
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    creds = Credentials.from_service_account_file(
        str(config.credentials_path()), scopes=["https://www.googleapis.com/auth/drive"])
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def list_source_files(svc, folder_id: str) -> list:
    files, token = [], None
    while True:
        res = svc.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields=f"nextPageToken, files({DRIVE_FIELDS})",
            pageSize=200, pageToken=token, orderBy="createdTime").execute()
        files.extend(res.get("files", []))
        token = res.get("nextPageToken")
        if not token:
            return files


def _kind_of(file_meta: dict) -> str | None:
    mime = file_meta.get("mimeType", "")
    if mime.startswith("video/"):
        return KIND_VIDEO
    if mime.startswith("image/"):
        return KIND_PHOTO
    by_ext = media_kind(Path(file_meta["name"]))
    return {"video": KIND_VIDEO, "photo": KIND_PHOTO}.get(by_ext or "")


def _download(svc, file_id: str, dest: Path) -> Path:
    import io
    from googleapiclient.http import MediaIoBaseDownload
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = svc.files().get_media(fileId=file_id)
    with io.FileIO(dest, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=8 * 1024 * 1024)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    return dest


def record_from_analysis(meta: dict, file_meta: dict, source_name: str, kind: str) -> dict:
    record = {
        "asset_id": asset_id_for(file_meta["id"], kind),
        "kind": kind,
        "file_name": file_meta["name"],
        "drive_file_id": file_meta["id"],
        "source_folder": source_name,
        "uploaded_at": (file_meta.get("createdTime") or "")[:10],
        "analyzed_at": now_text(),
        "size": f"{meta['width']}×{meta['height']}",
        "orientation": meta["orientation"],
        "contact_sheet": str(Path(meta["contact_sheet"]).relative_to(config.REPO_ROOT)),
    }
    if kind == KIND_VIDEO:
        record.update({
            "duration": f"{meta['duration']:.1f}",
            "rotation": str(meta["rotation"]),
            "fps": f"{meta['fps']:.2f}" + ("（可変）" if meta["variable_fps"] else ""),
            "hdr": meta["hdr_type"] or "なし",
            "audio": meta["audio_label"],
            "motion": f"{MOTION_LABELS[meta['motion']['class']]}（{meta['motion']['mean']}）",
            "segments": meta["segments_text"],
            "representative": str(meta["representative_second"]),
        })
    else:
        record.update({"duration": "", "rotation": "", "fps": "", "hdr": "", "audio": "",
                       "motion": "", "segments": "", "representative": ""})
    return record


def ingest_file(svc, catalog: Catalog, file_meta: dict, source_name: str, *,
                force: bool = False, dry_run: bool = False) -> str:
    kind = _kind_of(file_meta)
    if kind is None:
        return f"対象外（動画・写真ではない）: {file_meta['name']}"
    asset_id = asset_id_for(file_meta["id"], kind)
    existing = catalog.find_by_drive_id(file_meta["id"])
    if existing and existing.get("analyzed_at") and not force:
        return f"取り込み済み: {asset_id} {file_meta['name']}"
    if dry_run:
        return f"取り込み予定: {asset_id} {kind} {file_meta['name']}"

    work = config.ASSETS_WORK_DIR / asset_id
    ext = Path(file_meta["name"]).suffix.lower() or (".mov" if kind == KIND_VIDEO else ".jpg")
    source = work / f"source{ext}"
    if not source.exists() or force:
        _download(svc, file_meta["id"], source)

    if kind == KIND_VIDEO:
        meta = analyze_video(source, work, title=f"{asset_id}  {file_meta['name']}")
    else:
        meta = analyze_photo(source, work)
    catalog.upsert(record_from_analysis(meta, file_meta, source_name, kind))
    detail = (f"{meta['duration']:.1f}秒 {meta['orientation']} 動き:{MOTION_LABELS[meta['motion']['class']]}"
              if kind == KIND_VIDEO else f"{meta['width']}×{meta['height']}")
    return f"取り込み: {asset_id} {kind} {file_meta['name']}（{detail}）"


def main(argv=None):
    from load_env import load_from_zshrc
    load_from_zshrc()

    parser = argparse.ArgumentParser(description="Driveの受付フォルダから素材を取り込んで台帳に載せる")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="取り込み済みも解析し直す")
    parser.add_argument("--limit", type=int, default=0, help="取り込む最大件数（0=無制限）")
    parser.add_argument("--drive-file-id", nargs="*", default=[],
                        help="受付フォルダ以外のファイルを個別に取り込む（テーマ別フォルダの写真など）")
    args = parser.parse_args(argv)

    cfg = config.load_drive_config()
    svc = _drive()
    catalog = Catalog()

    targets = []
    failures = 0
    if args.drive_file_id:
        for file_id in args.drive_file_id:
            try:
                meta = svc.files().get(fileId=file_id, fields=DRIVE_FIELDS).execute()
                parent_name = ""
                if meta.get("parents"):
                    parent_name = svc.files().get(fileId=meta["parents"][0], fields="name").execute()["name"]
            except Exception as e:  # IDの誤りは1件ずつ報告して残りを続ける
                failures += 1
                print(f"失敗: DriveファイルID {file_id} を取得できません → {e}")
                continue
            targets.append((meta, parent_name))
    else:
        for src in cfg["intake_sources"]:
            for meta in list_source_files(svc, src["folder_id"]):
                targets.append((meta, src["name"]))

    count = 0
    for meta, source_name in targets:
        if args.limit and count >= args.limit:
            break
        try:
            message = ingest_file(svc, catalog, meta, source_name,
                                  force=args.force, dry_run=args.dry_run)
        except Exception as e:  # 1件の失敗で残りを止めない
            failures += 1
            message = f"失敗: {meta['name']} → {e}"
        print(message)
        if message.startswith("取り込み:"):
            count += 1
    print(f"完了: 取り込み {count}件 / 失敗 {failures}件")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
