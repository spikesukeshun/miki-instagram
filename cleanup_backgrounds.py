"""
cleanup_backgrounds.py
----------------------
投稿完了後に Claude Code から呼び出すクリーンアップスクリプト。
既存コード（create_post.py など）には一切手を加えない独立ファイル。

【役割】
1. seed 履歴（upload_history.json）をもとに「初回 generate か重複か」を判定
2. 初回 generate 画像のみ Drive にアップ済み扱いとして履歴に記録
3. backgrounds/ の画像をすべて削除（reuse / edit / generate 問わず）
4. generated/ の完成カルーセル画像（carousel_*.jpg）を削除（GitHub アップ済み前提）

【Claude Code からの呼び出し方】
  python cleanup_backgrounds.py --seed 123456           # 通常
  python cleanup_backgrounds.py --seed 123456 789012    # seed 複数
  python cleanup_backgrounds.py --seed 123456 --force   # 確認スキップ
  python cleanup_backgrounds.py --seed 123456 --dry-run # 確認のみ
  python cleanup_backgrounds.py --no-generate           # reuse/edit のみの回
"""

import argparse
import glob
import json
import os
from datetime import datetime

BACKGROUNDS_DIR = "backgrounds"
GENERATED_DIR   = "generated"
HISTORY_PATH    = "upload_history.json"
TARGET_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
# 末尾固定スライド（CLAUDE.md「末尾2枚は常に固定」）— 誤削除すると次回投稿が壊れるため保護
# 大小拡張子（slide7.JPG 等）も守るため、比較側で .lower() してから set と照合する
KEEP_BG_FILES   = {"slide7.jpg", "slide8.jpg"}


def load_history() -> dict:
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"uploaded_seeds": []}


def save_history(history: dict) -> None:
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def get_image_files(directory: str) -> list:
    files = []
    for ext in TARGET_EXTENSIONS:
        files.extend(glob.glob(os.path.join(directory, f"*{ext}")))
        files.extend(glob.glob(os.path.join(directory, f"*{ext.upper()}")))
    return sorted(set(files))


def get_carousel_files(directory: str) -> list:
    """generated/ の carousel_*.jpg だけを対象にする"""
    return sorted(glob.glob(os.path.join(directory, "carousel_*.jpg")))


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / 1024 ** 2:.1f} MB"


def delete_files(targets: list, label: str, dry_run: bool) -> int:
    """ファイルを削除して削除数を返す"""
    if not targets:
        print(f"[{label}] 削除対象なし")
        return 0

    total_size = sum(os.path.getsize(f) for f in targets)
    print(f"\n[{label}] 削除対象: {len(targets)} ファイル（合計 {format_size(total_size)}）")
    for f in targets:
        print(f"  - {os.path.basename(f)}  ({format_size(os.path.getsize(f))})")

    if dry_run:
        return 0

    deleted = 0
    for f in targets:
        try:
            os.remove(f)
            deleted += 1
        except Exception as e:
            print(f"  [ERROR] {f} の削除に失敗: {e}")

    print(f"[{label}] 完了: {deleted} ファイル削除（{format_size(total_size)} 解放）")
    return deleted


def cleanup(seeds: list, no_generate: bool, dry_run: bool, force: bool) -> None:
    print(f"\n{'=' * 50}")
    print("  cleanup_backgrounds.py")
    print(f"{'=' * 50}")

    # ── seed 履歴チェック ──────────────────────────
    history = load_history()
    uploaded_seeds = set(history.get("uploaded_seeds", []))
    new_seeds = []

    if not no_generate:
        for seed in seeds:
            if seed in uploaded_seeds:
                print(f"[skip]  seed={seed} は過去にアップ済み → Drive アップをスキップ")
            else:
                new_seeds.append(seed)
                print(f"[new]   seed={seed} は初回 → Drive アップ済みとして記録")

        if new_seeds and not dry_run:
            for s in new_seeds:
                uploaded_seeds.add(s)
            history["uploaded_seeds"] = sorted(uploaded_seeds)
            history["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_history(history)
            print(f"  → upload_history.json を更新（累計 {len(uploaded_seeds)} 件）")
    else:
        print("[info]  generate 画像なし（reuse/edit のみ）→ 履歴は変更しません")

    # ── 削除対象を収集 ────────────────────────────
    bg_files       = [f for f in get_image_files(BACKGROUNDS_DIR) if os.path.basename(f).lower() not in KEEP_BG_FILES] if os.path.isdir(BACKGROUNDS_DIR) else []
    carousel_files = get_carousel_files(GENERATED_DIR) if os.path.isdir(GENERATED_DIR) else []
    all_targets    = bg_files + carousel_files

    if not all_targets:
        print("\n削除対象のファイルはありません。")
        return

    # ── 確認プロンプト（--force でスキップ）────────
    if dry_run:
        delete_files(bg_files,       "backgrounds", dry_run=True)
        delete_files(carousel_files, "generated",   dry_run=True)
        print("\n--dry-run モード: 実際には削除しません。")
        return

    if not force:
        total = sum(os.path.getsize(f) for f in all_targets)
        print(f"\n合計 {len(all_targets)} ファイル（{format_size(total)}）を削除します。")
        answer = input("実行しますか？ [y/N]: ").strip().lower()
        if answer != "y":
            print("キャンセルしました。")
            return

    # ── 削除実行 ──────────────────────────────────
    delete_files(bg_files,       "backgrounds", dry_run=False)
    delete_files(carousel_files, "generated",   dry_run=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="backgrounds/ と generated/ を削除し seed 履歴で Drive 重複アップを防ぐ"
    )
    parser.add_argument(
        "--seed", type=int, nargs="*", default=[],
        help="今回 generate した画像の seed 番号（複数可・スペース区切り）",
    )
    parser.add_argument(
        "--no-generate", action="store_true",
        help="今回 generate 画像がなかった場合（reuse/edit のみの回）",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="削除せず対象ファイルの一覧を表示するだけ",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="確認プロンプトをスキップして即削除",
    )
    args = parser.parse_args()

    cleanup(
        seeds=args.seed,
        no_generate=args.no_generate,
        dry_run=args.dry_run,
        force=args.force,
    )
