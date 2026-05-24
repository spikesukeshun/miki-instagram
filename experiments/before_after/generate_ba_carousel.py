"""Before/After カルーセル試作の生成パイプライン。

content_ba.json を読んで:
- ba_split スライドは PIL で左右分割画像を合成して generated/ に保存
- video_passthrough スライドは src の動画を generated/ にコピー（変換なし）
出力先: experiments/before_after/generated/

--dry-run（デフォルト）: 生成のみ。Instagram には何も投稿しない
--publish: post_ba_mixed.post_mixed_carousel を呼んで実際に投稿（image_url/video_url 必須）
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from experiments.before_after.ba_helpers import (  # noqa: E402
    IMAGE_SLIDE_TYPES,
    compose_ba_split,
    compose_ba_cover,
    compose_ba_text_overlay,
    compose_ba_grid_compare,
    compose_ba_duration,
    compose_ba_points,
    compose_ba_cta,
    save_image_jpg,
)


def _resolve_path(base_dir: str, path: str) -> str:
    """content.json 内の相対パスを解決する。

    content.json があるディレクトリを基準に解決する。
    絶対パスはそのまま返す。
    """
    if os.path.isabs(path):
        return path
    return os.path.normpath(os.path.join(base_dir, path))


def generate(content_path: str, output_dir: str) -> dict:
    """content_ba.json から各スライドを生成し、出力ファイルパスを返す。"""
    with open(content_path, "r", encoding="utf-8") as f:
        content = json.load(f)

    base_dir = os.path.dirname(os.path.abspath(content_path))
    os.makedirs(output_dir, exist_ok=True)

    generated = []
    for i, slide in enumerate(content.get("slides", []), 1):
        t = slide.get("type")
        out_name = slide.get("filename_out") or f"ba_{i:02d}.jpg"
        out_path = os.path.join(output_dir, out_name)

        if t == "ba_split":
            before = _resolve_path(base_dir, slide["before"])
            after = _resolve_path(base_dir, slide["after"])
            if not os.path.exists(before):
                raise FileNotFoundError(f"before 画像が見つかりません: {before}")
            if not os.path.exists(after):
                raise FileNotFoundError(f"after 画像が見つかりません: {after}")
            img = compose_ba_split(
                before_path=before,
                after_path=after,
                labels=slide.get("labels"),
                divider=slide.get("divider"),
                bubble=slide.get("bubble"),
            )
            save_image_jpg(img, out_path)
            print(f"  [{i}] ba_split → {out_path}")
            generated.append({"type": "ba_split", "path": out_path, "slide": slide})

        elif t == "ba_cover":
            before = _resolve_path(base_dir, slide["before"])
            after = _resolve_path(base_dir, slide["after"])
            for p, label in [(before, "before"), (after, "after")]:
                if not os.path.exists(p):
                    raise FileNotFoundError(f"ba_cover の {label} 画像が見つかりません: {p}")
            miki_icon = slide.get("miki_icon")
            if miki_icon:
                miki_icon = _resolve_path(base_dir, miki_icon)
                if not os.path.exists(miki_icon):
                    miki_icon = None  # プレースホルダで描画
            img = compose_ba_cover(
                before_path=before,
                after_path=after,
                upper_caption=slide.get("upper_caption", "— 6ヶ月前"),
                lower_caption=slide.get("lower_caption", "現在 —"),
                sub_text=slide.get("sub_text", "続く綺麗\n作れていますか？"),
                bubble_text=slide.get("bubble_text", ""),
                miki_icon_path=miki_icon,
            )
            save_image_jpg(img, out_path)
            print(f"  [{i}] ba_cover → {out_path}")
            generated.append({"type": "ba_cover", "path": out_path, "slide": slide})

        elif t == "ba_text_overlay":
            images = [_resolve_path(base_dir, p) for p in slide.get("images", [])]
            for p in images:
                if not os.path.exists(p):
                    raise FileNotFoundError(f"ba_text_overlay の画像が見つかりません: {p}")
            img = compose_ba_text_overlay(
                images=images,
                top_text=slide.get("top_text", ""),
                bottom_text=slide.get("bottom_text", ""),
                bottom_keywords=slide.get("bottom_keywords"),
                layout=slide.get("layout", "horizontal"),
                strip_h=int(slide.get("strip_h", 410)),
            )
            save_image_jpg(img, out_path)
            print(f"  [{i}] ba_text_overlay → {out_path}")
            generated.append({"type": "ba_text_overlay", "path": out_path, "slide": slide})

        elif t == "ba_grid_compare":
            pairs = []
            for pair in slide.get("pairs", []):
                b = _resolve_path(base_dir, pair["before"])
                a = _resolve_path(base_dir, pair["after"])
                if not os.path.exists(b) or not os.path.exists(a):
                    raise FileNotFoundError(f"ba_grid_compare の写真が見つかりません: {b} / {a}")
                pairs.append((b, a))
            img = compose_ba_grid_compare(
                pairs=pairs,
                title=slide.get("title", "施術例"),
                subtitle=slide.get("subtitle", "担当したお客様の変化"),
            )
            save_image_jpg(img, out_path)
            print(f"  [{i}] ba_grid_compare → {out_path}")
            generated.append({"type": "ba_grid_compare", "path": out_path, "slide": slide})

        elif t == "ba_duration":
            before = _resolve_path(base_dir, slide["before"])
            after = _resolve_path(base_dir, slide["after"])
            for p, label in [(before, "before"), (after, "after")]:
                if not os.path.exists(p):
                    raise FileNotFoundError(f"ba_duration の {label} 画像が見つかりません: {p}")
            img = compose_ba_duration(
                before_path=before,
                after_path=after,
                headline=slide.get("headline", "半年〜1年で\n続く美しさ"),
                body=slide.get("body", ""),
                before_label=slide.get("before_label", "初回来店時"),
                after_label=slide.get("after_label", "再来店時"),
                image_zoom=slide.get("image_zoom", 1.0),
            )
            save_image_jpg(img, out_path)
            print(f"  [{i}] ba_duration → {out_path}")
            generated.append({"type": "ba_duration", "path": out_path, "slide": slide})

        elif t == "ba_points":
            items = []
            for it in slide.get("items", []):
                resolved = dict(it)
                if it.get("image"):
                    resolved["image"] = _resolve_path(base_dir, it["image"])
                items.append(resolved)
            img = compose_ba_points(
                title=slide.get("title", "選ばれる理由"),
                items=items,
            )
            save_image_jpg(img, out_path)
            print(f"  [{i}] ba_points → {out_path}")
            generated.append({"type": "ba_points", "path": out_path, "slide": slide})

        elif t == "ba_cta":
            bg = slide.get("bg_image")
            if bg:
                bg = _resolve_path(base_dir, bg)
                if not os.path.exists(bg):
                    bg = None
            img = compose_ba_cta(
                title=slide.get("title", "MIKI指名 初回限定20%OFF\n（VIPコースのみ）"),
                body=slide.get("body", ""),
                subtitle=slide.get("subtitle", "ご予約・ご相談はDMからお気軽にどうぞ"),
                bg_image=bg,
            )
            save_image_jpg(img, out_path)
            print(f"  [{i}] ba_cta → {out_path}")
            generated.append({"type": "ba_cta", "path": out_path, "slide": slide})

        elif t == "video_passthrough":
            src = _resolve_path(base_dir, slide["src"])
            if not os.path.exists(src):
                raise FileNotFoundError(f"動画ファイルが見つかりません: {src}")
            frame_width = int(slide.get("frame_width", 0))
            frame_color = slide.get("frame_color", "#F6F1F1")  # CREAM
            if frame_width > 0:
                # ffmpeg で外周に均等パディング → 額縁風フレーム
                color_str = frame_color.lstrip("#")
                cmd = [
                    "ffmpeg", "-y", "-i", src,
                    "-vf",
                    f"pad=iw+{frame_width*2}:ih+{frame_width*2}:{frame_width}:{frame_width}:color=0x{color_str}",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    # mov(PCM) 入力でも mp4 へ収まるように音声は AAC へ再エンコ
                    "-c:a", "aac", "-b:a", "128k",
                    out_path,
                ]
                try:
                    subprocess.run(cmd, check=True, capture_output=True, timeout=300)
                except subprocess.CalledProcessError as e:
                    err = e.stderr.decode("utf-8", "replace") if e.stderr else ""
                    raise RuntimeError(
                        f"ffmpeg でフレーム付与に失敗しました: {src}\n"
                        f"--- ffmpeg stderr ---\n{err}"
                    ) from e
                except subprocess.TimeoutExpired as e:
                    raise RuntimeError(
                        f"ffmpeg がタイムアウトしました（300秒）: {src}"
                    ) from e
            else:
                shutil.copy2(src, out_path)
            print(f"  [{i}] video_passthrough → {out_path}")
            generated.append({"type": "video_passthrough", "path": out_path, "slide": slide})

        else:
            raise ValueError(f"未対応のスライド type: {t}")

    return {"content": content, "generated": generated}


def _items_for_publish(generated_records: list[dict]) -> list[dict]:
    """publish 用に各スライドの url を集める（image_url / video_url を slide から拾う）。"""
    items = []
    for rec in generated_records:
        slide = rec["slide"]
        if rec["type"] in IMAGE_SLIDE_TYPES:
            url = slide.get("image_url")
            if not url:
                raise ValueError(
                    f"--publish には {rec['type']}.image_url（公開 URL）が必要: {slide.get('filename_out')}"
                )
            items.append({"type": "image", "url": url})
        elif rec["type"] == "video_passthrough":
            url = slide.get("video_url")
            if not url:
                raise ValueError(
                    f"--publish には video_passthrough.video_url（公開 URL）が必要: {slide.get('filename_out')}"
                )
            items.append({"type": "video", "url": url})
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--content", default=os.path.join(_THIS_DIR, "content_ba.json"))
    ap.add_argument("--output-dir", default=os.path.join(_THIS_DIR, "generated"))
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--dry-run", action="store_true", help="生成のみ（既定）")
    grp.add_argument("--publish", action="store_true", help="生成後に Instagram へ投稿する")
    args = ap.parse_args()

    print(f"[generate] content={args.content} output_dir={args.output_dir}")
    result = generate(args.content, args.output_dir)

    if not args.publish:
        print("[done] dry-run（生成のみ）。--publish で投稿します。")
        return

    # publish 経路は遅延 import（資格情報が無いとき dry-run が阻害されないように）
    from experiments.before_after.post_ba_mixed import post_mixed_carousel

    items = _items_for_publish(result["generated"])
    caption = result["content"].get("caption", "")
    post_mixed_carousel(items, caption, dry_run=False)


if __name__ == "__main__":
    main()
