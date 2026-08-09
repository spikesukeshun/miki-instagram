"""過去の content.json から「どの画像を、どの位置（focus_y）で使ったか」を集計する。

同じ Drive 画像を再利用するとき、毎回ちがう位置で切り取ってしまうと
フィード上で同じ写真が別物に見える。過去の使用位置を引けるようにして、
`review_post.py` からも機械チェックする（2026-08-09 追加）。

CLI:
    python3 image_positions.py                      # ズレている画像を一覧
    python3 image_positions.py "candle.jpg"         # その画像の使用履歴
"""

import glob
import json
import os
import sys
import unicodedata
from collections import Counter, defaultdict

CONTENT_GLOB = "content*.json"


def _norm(name: str) -> str:
    return unicodedata.normalize("NFC", name)


def build_index(directory: str = ".", exclude: str = None) -> dict:
    """{画像名: [{file, slide, type, focus_y, ratio}, ...]} を返す。

    exclude に content ファイルのパスを渡すと、その1件を集計から外す
    （自分自身と比較して「ズレている」と誤検出しないため）。
    """
    exclude_abs = os.path.abspath(exclude) if exclude else None
    index = defaultdict(list)

    for path in sorted(glob.glob(os.path.join(directory, CONTENT_GLOB))):
        if exclude_abs and os.path.abspath(path) == exclude_abs:
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (ValueError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        for i, slide in enumerate(data.get("slides", []), 1):
            name = slide.get("reuse_filename")
            if not name:
                continue
            index[_norm(name)].append({
                "file": os.path.basename(path),
                "slide": i,
                "type": slide.get("type"),
                "focus_y": slide.get("focus_y"),
                "ratio": slide.get("slide_photo_h_ratio"),
            })
    return dict(index)


def past_positions(name: str, slide_type: str = None, directory: str = ".",
                   exclude: str = None) -> list:
    """その画像の過去の使用履歴。slide_type を渡すと同じ型だけに絞る。

    型で絞るのは、写真ゾーンの高さが型ごとに違う（cover は既定 0.55、
    text/list は 0.35）ため、同じ focus_y でも見え方が変わるから。
    """
    rows = build_index(directory, exclude=exclude).get(_norm(name), [])
    if slide_type is not None:
        rows = [r for r in rows if r["type"] == slide_type]
    return rows


def recommended_focus_y(name: str, slide_type: str = None, directory: str = ".",
                        exclude: str = None):
    """過去に最も多く使われた focus_y。履歴が無ければ None。"""
    rows = past_positions(name, slide_type, directory, exclude)
    values = [r["focus_y"] for r in rows if r["focus_y"] is not None]
    if not values:
        return None
    return Counter(values).most_common(1)[0][0]


def _print_history(name: str, directory: str = "."):
    rows = build_index(directory).get(_norm(name), [])
    if not rows:
        print(f"{name}: 過去の使用なし（初めて使う画像です）")
        return
    print(f"{name}: {len(rows)}回使用")
    by_type = defaultdict(list)
    for r in rows:
        by_type[r["type"]].append(r)
    for stype, group in sorted(by_type.items(), key=lambda x: str(x[0])):
        rec = Counter(r["focus_y"] for r in group).most_common(1)[0][0]
        print(f"  [{stype}] 推奨 focus_y={rec}")
        for r in group:
            print(f"      focus_y={r['focus_y']!s:<5} {r['file']} スライド{r['slide']}")


def _print_conflicts(directory: str = "."):
    index = build_index(directory)
    found = 0
    for name, rows in sorted(index.items()):
        by_type = defaultdict(set)
        for r in rows:
            by_type[r["type"]].add(r["focus_y"])
        clashing = {t: v for t, v in by_type.items() if len(v) > 1}
        if not clashing:
            continue
        found += 1
        print(f"■ {name}")
        for stype, values in clashing.items():
            vals = ", ".join(str(v) for v in sorted(values, key=lambda x: (x is None, x)))
            rec = recommended_focus_y(name, stype, directory)
            print(f"    [{stype}] focus_y が複数: {vals}（多数派: {rec}）")
    print(f"\n同じ型の中で位置がズレている画像: {found}件")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        _print_history(sys.argv[1])
    else:
        _print_conflicts()
