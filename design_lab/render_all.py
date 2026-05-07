"""Render all 4 design variants from the same content fixtures.

Usage:
    python design_lab/render_all.py                   # render all variants
    python design_lab/render_all.py --variant a       # render just one
    python design_lab/render_all.py --content menu    # use menu fixture
"""
import argparse
import importlib
import json
import os
import sys

# allow `from variants import ...` whether run from repo root or design_lab/
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from variants import _base as B  # noqa: E402

VARIANT_MODULES = {
    "a": "variants.variant_a_magazine",
    "b": "variants.variant_b_monochrome",
    "c": "variants.variant_c_beige",
    "d": "variants.variant_d_themed",
}

OUTPUT_DIR = os.path.join(HERE, "output")


def _load_fixture(kind: str) -> dict:
    name = "sample_content.json" if kind == "lifestyle" else "sample_content_menu.json"
    with open(os.path.join(HERE, name), "r", encoding="utf-8") as f:
        return json.load(f)


def _render_variant(variant_key: str, content: dict, label: str):
    mod_name = VARIANT_MODULES[variant_key]
    try:
        module = importlib.import_module(mod_name)
    except ModuleNotFoundError:
        print(f"  [skip] {mod_name} not implemented yet")
        return
    out_dir = os.path.join(OUTPUT_DIR, module.NAME, label)
    os.makedirs(out_dir, exist_ok=True)
    # Map fixture type → palette key for variant D
    palette_key = {"lifestyle": "lifestyle", "menu": "bridal"}.get(label, "lifestyle")
    print(f"  rendering {module.NAME} / {label}")
    for i, slide in enumerate(content["slides"], 1):
        gen = module.GENERATORS.get(slide["type"])
        if not gen:
            continue
        slide_with_meta = dict(slide)
        slide_with_meta.setdefault("_palette", palette_key)
        bg = B.load_sample_bg(slide["filename"])
        img = gen(bg, slide_with_meta)
        out = os.path.join(out_dir, f"{i:02d}_{slide['type']}.jpg")
        img.save(out, "JPEG", quality=92)
        print(f"    -> {os.path.relpath(out, HERE)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=list(VARIANT_MODULES.keys()) + ["all"],
                    default="all")
    ap.add_argument("--content", choices=["lifestyle", "menu", "both"],
                    default="both")
    args = ap.parse_args()

    fixtures = (["lifestyle", "menu"] if args.content == "both" else [args.content])
    variants = (list(VARIANT_MODULES.keys()) if args.variant == "all"
                else [args.variant])

    for v in variants:
        for fix in fixtures:
            _render_variant(v, _load_fixture(fix), fix)

    print("\ndone.")


if __name__ == "__main__":
    main()
