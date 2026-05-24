"""Before/After 投稿用のラッパースクリプト。

通常のカルーセル（generate_carousel.py + create_post.py）と
BA 専用カルーセル（experiments/before_after/generate_ba_carousel.py）を
組み合わせる。

スライド構成（最終8枚）：
  1枚目: 表紙（既存 generate_carousel.py で生成）
  2-6枚目: BA 5枚（experiments/before_after で生成）
    - 2枚目は動画（mp4）。プレビュー用にサムネ jpg も生成
  7-8枚目: 既存固定（slide8.jpg → carousel_07.jpg、slide7.jpg → carousel_08.jpg）

Usage:
  python create_post_ba.py \\
    --content-main content_16_main.json \\
    --content-ba   content_16_ba.json \\
    --post-datetime "2026/05/13 21:00" \\
    --menu "ご褒美エステ"
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
GENERATED_DIR = os.path.join(REPO_ROOT, "generated")
BACKGROUNDS_DIR = os.path.join(REPO_ROOT, "backgrounds")
TMP_BA_DIR = os.path.join(REPO_ROOT, "tmp_ba_dir")

# 既存パイプラインのヘルパーを再利用（モジュール import で load_env も走る）
from create_post import (  # noqa: E402
    fetch_instagram_posts,
    collect_available_images,
    list_reference_images,
    resolve_backgrounds,
    _upload_backgrounds_to_drive,
    _menu_to_theme,
)
from generate_carousel import generate_with_slides, crop_center, W, H  # noqa: E402
from register_post import register  # noqa: E402

# BA パイプライン
from experiments.before_after.generate_ba_carousel import generate as ba_generate  # noqa: E402


def _extract_video_thumbnail(video_path: str, jpg_path: str) -> bool:
    """ffmpeg で動画の先頭フレームを抜き出して 1080x1350 のクリーム背景にフィットさせて保存。
    成功判定はファイルサイズ > 1KB も必須（ffmpeg は失敗時にも 0 バイトを出すことがある）。"""
    try:
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf",
            "scale=1080:1350:force_original_aspect_ratio=decrease,"
            "pad=1080:1350:(ow-iw)/2:(oh-ih)/2:color=0xF6F1F1",
            "-vframes", "1", "-q:v", "3",
            jpg_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    except Exception as e:
        print(f"  サムネ抽出失敗: {e}")
        return False
    if not os.path.exists(jpg_path) or os.path.getsize(jpg_path) < 1024:
        print(f"  サムネ抽出は完了したが出力サイズが小さすぎる: {jpg_path}")
        return False
    return True


def _make_video_placeholder(jpg_path: str) -> None:
    """サムネ抽出失敗時のフェイルセーフ：クリーム背景に「動画スライド」テキストを描いた JPG を生成。
    プレビュー時にスライド順序がズレないように必ず carousel_NN.jpg を埋める。"""
    from PIL import Image, ImageDraw
    from generate_carousel import get_serif
    img = Image.new("RGB", (W, H), (246, 241, 241))
    draw = ImageDraw.Draw(img)
    font = get_serif(56)
    msg = "動画スライド"
    bbox = font.getbbox(msg)
    tx = (W - (bbox[2] - bbox[0])) // 2
    ty = H // 2 - 28
    draw.text((tx, ty), msg, font=font, fill=(140, 120, 110))
    sub = ImageDraw.Draw(img)
    sub_font = get_serif(28)
    sub_msg = "(プレビューでは静止画として表示)"
    sb = sub_font.getbbox(sub_msg)
    sub.text(((W - (sb[2] - sb[0])) // 2, ty + 80), sub_msg, font=sub_font,
             fill=(160, 145, 130))
    img.save(jpg_path, "JPEG", quality=92)


def _resize_to_carousel(src_path: str, dst_path: str) -> None:
    """1080x1350 にセンタークロップして保存。元が既に 1080x1350 のときは
    再エンコード劣化を避けるため shutil.copy2 で済ませる。"""
    from PIL import Image
    img = Image.open(src_path).convert("RGB")
    if img.size == (W, H):
        shutil.copy2(src_path, dst_path)
        return
    img = crop_center(img, (W, H))
    img.save(dst_path, "JPEG", quality=95)


def _clean_generated_dir() -> None:
    """generated/ の前回ビルド成果物（カルーセル画像・動画）をクリア。"""
    os.makedirs(GENERATED_DIR, exist_ok=True)
    for pattern in ("carousel_*.jpg", "carousel_*.mp4"):
        for f in glob.glob(os.path.join(GENERATED_DIR, pattern)):
            os.remove(f)


def main():
    ap = argparse.ArgumentParser(description="Before/After 投稿用カルーセル生成 + 登録ラッパー")
    ap.add_argument("--content-main", required=True, help="表紙 + キャプション + メタの JSON")
    ap.add_argument("--content-ba", required=True, help="BA 5枚（2-6枚目）の JSON")
    ap.add_argument("--post-datetime", required=True, help='例: "2026/05/13 21:00"')
    ap.add_argument("--menu", default=None,
                    help="メニュー種別（省略時は content-main の menu フィールド or 'ご褒美エステ'）")
    args = ap.parse_args()

    # ---------------------------------------------------------------
    # 1. main 側 JSON 読み込み
    # ---------------------------------------------------------------
    print(f"[load] {args.content_main}")
    with open(args.content_main, "r", encoding="utf-8") as f:
        main_content = json.load(f)

    if not main_content.get("slides"):
        print("ERROR: content-main の slides が空です（cover 1枚を必ず含めてください）")
        sys.exit(1)
    cover_slide = main_content["slides"][0]
    if cover_slide.get("type") != "cover":
        print("ERROR: content-main の slides[0] は type='cover' である必要があります")
        sys.exit(1)

    # menu の単一情報源化：CLI > content-main > デフォルト
    menu_type = args.menu or main_content.get("menu") or "ご褒美エステ"

    # ---------------------------------------------------------------
    # 2. 背景解決（過去画像/参考画像/Drive画像を取得して cover の背景を作る）
    # ---------------------------------------------------------------
    print("\n[bg] 過去のInstagram投稿を取得中...")
    past_posts = fetch_instagram_posts(limit=30)
    available_images = collect_available_images(past_posts) if past_posts else []
    if available_images:
        print(f"  利用可能な過去画像: {len(available_images)}枚")

    print("[bg] 参考画像を確認中...")
    list_reference_images()  # ログ目的

    bg_prompt = main_content.get(
        "bg_prompt",
        "Japanese esthetic salon, soft morning light, no people, calm atmosphere",
    )
    global_seed = main_content.get("seed")
    last_seed = resolve_backgrounds(
        [cover_slide], available_images, bg_prompt, global_seed=global_seed,
    )

    # 表紙だけを Drive に保存
    drive_theme = main_content.get("drive_theme") or _menu_to_theme(menu_type)
    _upload_backgrounds_to_drive([cover_slide], drive_theme)

    # ---------------------------------------------------------------
    # 3. 表紙の生成（generate_carousel が backgrounds/<filename> を読む）
    #    出力先は generated/carousel_01.jpg
    # ---------------------------------------------------------------
    _clean_generated_dir()
    print("\n[cover] 表紙スライドを生成中...")
    generate_with_slides([cover_slide])  # → generated/carousel_01.jpg

    # ---------------------------------------------------------------
    # 4. BA スライド 5枚を生成
    # ---------------------------------------------------------------
    print(f"\n[BA] BA スライドを生成中 ({args.content_ba})...")
    if os.path.exists(TMP_BA_DIR):
        shutil.rmtree(TMP_BA_DIR)
    os.makedirs(TMP_BA_DIR, exist_ok=True)
    ba_result = ba_generate(args.content_ba, TMP_BA_DIR)

    # ---------------------------------------------------------------
    # 5. BA 出力を generated/carousel_02..06 に連結
    # ---------------------------------------------------------------
    print("\n[combine] BA 出力を本番カルーセルに連結中...")
    for idx, rec in enumerate(ba_result["generated"], start=2):
        src = rec["path"]
        if rec["type"] == "video_passthrough":
            mp4_dst = os.path.join(GENERATED_DIR, f"carousel_{idx:02d}.mp4")
            shutil.copy2(src, mp4_dst)
            print(f"  {idx}枚目（動画）: {mp4_dst}")
            jpg_dst = os.path.join(GENERATED_DIR, f"carousel_{idx:02d}.jpg")
            ok = _extract_video_thumbnail(src, jpg_dst)
            if ok:
                print(f"  {idx}枚目（サムネ）: {jpg_dst}")
            else:
                # フェイルセーフ：プレースホルダ JPG を必ず置く
                # （register_post.py が glob でスライド順を決めるため、欠番にすると順序が崩れる）
                _make_video_placeholder(jpg_dst)
                print(f"  ⚠ {idx}枚目のサムネ抽出に失敗 → プレースホルダで埋めました: {jpg_dst}")
        else:
            jpg_dst = os.path.join(GENERATED_DIR, f"carousel_{idx:02d}.jpg")
            _resize_to_carousel(src, jpg_dst)
            print(f"  {idx}枚目: {jpg_dst}")

    # ---------------------------------------------------------------
    # 6. 末尾2枚（slide8.jpg → carousel_07.jpg / slide7.jpg → carousel_08.jpg）
    # ---------------------------------------------------------------
    for idx, fixed in [(7, "slide8.jpg"), (8, "slide7.jpg")]:
        src = os.path.join(BACKGROUNDS_DIR, fixed)
        if not os.path.exists(src):
            print(f"  ⚠ {fixed} が backgrounds/ にありません — スキップ")
            continue
        dst = os.path.join(GENERATED_DIR, f"carousel_{idx:02d}.jpg")
        _resize_to_carousel(src, dst)
        print(f"  {idx}枚目（固定）: {dst}")

    # ---------------------------------------------------------------
    # 7. 登録（GitHub Pages にアップロード + スプレッドシート記入）
    # ---------------------------------------------------------------
    print("\n[register] スプレッドシート登録 + GitHub Pages プレビュー...")
    register(
        post_datetime=args.post_datetime,
        menu_type=menu_type,
        caption=main_content["caption"],
        hashtags=main_content.get("hashtags", ""),
        memo=main_content.get("memo", ""),
        seed=last_seed,
        alt_text=main_content.get("alt_text", ""),
    )

    # ---------------------------------------------------------------
    # 8. content_main.json に _generated_dir を記録
    #    parse の例外と書き戻しの例外を分離して、書き戻し失敗を握り潰さない
    # ---------------------------------------------------------------
    try:
        dt = datetime.strptime(args.post_datetime, "%Y/%m/%d %H:%M")
    except ValueError as e:
        print(f"  _generated_dir 記録スキップ（datetime parse 失敗）: {e}")
    else:
        main_content["_generated_dir"] = dt.strftime("%Y-%m-%d-%H%M")
        with open(args.content_main, "w", encoding="utf-8") as f:
            json.dump(main_content, f, ensure_ascii=False, indent=2)
        print(f"\n  _generated_dir={main_content['_generated_dir']} を記録しました")

    # ---------------------------------------------------------------
    # 9. tmp ディレクトリのクリーンアップ
    # ---------------------------------------------------------------
    if os.path.exists(TMP_BA_DIR):
        shutil.rmtree(TMP_BA_DIR)

    print("\n[done] BA 投稿の生成と登録が完了しました")
    print("       ⚠ register_post は表紙〜BAの静止画プレビューを GitHub Pages に上げ、")
    print("         スプレッドシートに行を追加するだけです。")
    print("         実際の Instagram 投稿（動画スライドを含むカルーセル）は")
    print("         post_ba_mixed.py で別途実行する必要があります（今回スコープ外）。")


if __name__ == "__main__":
    main()
