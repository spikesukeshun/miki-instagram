"""Build a 3x3 profile-grid preview for each variant.

Instagramのプロフィール画面では投稿の1枚目が3×3で並ぶ。各 variant で過去9件分の
カバーを生成し、3×3のグリッド画像を作って「もしこの新デザインだったら」を確認する。

カバー素材は repo の content_*.json から最新9件を流用し、design_lab の variant
generators で再描画する。
"""
from __future__ import annotations  # Python 3.9 互換（PEP 604 union syntax）

import argparse
import importlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

from PIL import Image  # noqa: E402
from variants import _base as B  # noqa: E402

VARIANT_MODULES = {
    "a": "variants.variant_a_magazine",
    "b": "variants.variant_b_monochrome",
    "c": "variants.variant_c_beige",
    "d": "variants.variant_d_themed",
}

# Pull the cover slide from each repo content_*.json and use a placeholder bg
# (variant generators degrade gracefully when sample_bg/ is empty).
GRID_FIXTURES = [
    "content_01.json", "content_02.json", "content_03.json",
    "content_04.json", "content_05.json", "content_06.json",
    "content_07.json", "content_08.json", "content_09.json",
]


def _kicker_for(menu: str) -> str:
    if not menu:
        return "lifestyle"
    if "ブライダル" in menu:
        return "bridal"
    if "ご褒美" in menu or "ライフ" in menu:
        return "lifestyle"
    return "menu"


def _load_cover_slide(filename: str) -> dict | None:
    path = os.path.join(REPO, filename)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    slides = data.get("slides", [])
    if not slides:
        return None
    cover = slides[0].copy()
    cover.setdefault("kicker", _kicker_for(data.get("menu", "")))
    cover["_palette"] = _kicker_for(data.get("menu", ""))
    cover["filename"] = "_grid_placeholder.jpg"  # force placeholder bg
    return cover


def _render_grid_for_variant(variant_key: str, slides: list[dict]):
    mod_name = VARIANT_MODULES[variant_key]
    try:
        module = importlib.import_module(mod_name)
    except ModuleNotFoundError:
        print(f"  [skip] {mod_name}")
        return
    cell = 360  # 1080 / 3
    grid = Image.new("RGB", (cell * 3, cell * 3), (240, 235, 228))
    print(f"  rendering grid: {module.NAME}")
    for i, slide in enumerate(slides[:9]):
        gen = module.GENERATORS.get(slide["type"])
        if not gen:
            continue
        bg = B.load_sample_bg(slide.get("filename", "_grid_placeholder.jpg"))
        img = gen(bg, slide).convert("RGB")
        # Square-crop the 4:5 cover to a 1:1 grid cell (Instagram crops the
        # center for the profile grid).
        w, h = img.size
        side = min(w, h)
        sq = img.crop(((w - side) // 2, (h - side) // 2,
                       (w + side) // 2, (h + side) // 2))
        sq = sq.resize((cell, cell), Image.LANCZOS)
        x = (i % 3) * cell
        y = (i // 3) * cell
        grid.paste(sq, (x, y))
    out = os.path.join(HERE, "output", module.NAME, "grid_3x3.jpg")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    grid.save(out, "JPEG", quality=92)
    print(f"    -> {os.path.relpath(out, HERE)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=list(VARIANT_MODULES.keys()) + ["all"],
                    default="all")
    args = ap.parse_args()

    slides = []
    for fname in GRID_FIXTURES:
        s = _load_cover_slide(fname)
        if s:
            slides.append(s)

    print(f"loaded {len(slides)} cover slides for the grid")
    if len(slides) < 9:
        # pad with the lifestyle sample so the grid is always 3x3
        with open(os.path.join(HERE, "sample_content.json"), "r", encoding="utf-8") as f:
            sample = json.load(f)["slides"][0]
        sample["filename"] = "_grid_placeholder.jpg"
        sample["_palette"] = "lifestyle"
        while len(slides) < 9:
            slides.append(sample.copy())

    variants = (list(VARIANT_MODULES.keys()) if args.variant == "all"
                else [args.variant])
    for v in variants:
        _render_grid_for_variant(v, slides)

    print("\ndone.")


if __name__ == "__main__":
    main()
