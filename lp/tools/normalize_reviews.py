#!/usr/bin/env python3
"""口コミスクリーンショットを LP 掲載用に正規化する。

- 上端: 「（女性/30代…）」行の上に一定の余白を持たせて揃える（アバターアイコンの切れ端を除去）
- 下端: 「予約時のクーポン・メニュー」ボックスの下罫線でそろえる
- 左右: カードの枠線でトリミングし、全画像を同じ幅にリサイズ
- PAGETOP ボタン（半透明グレー）を逆合成で除去
"""
import glob
import os

import numpy as np
from PIL import Image

SRC = "kuchikomi"
DST = "normalized"
TARGET_W = 1158          # カード内側の幅（1206px スクショの枠線間）
TOP_PAD = 38             # 「女性/30代」行の上に置くベージュ帯の高さ
TEXT_H = 28              # 「（女性/30代…）」行の高さ（全画像共通）
BORDER = (205, 205, 205)  # カード枠線の色
BAND = np.array([254, 248, 236])  # ヘッダー帯のベージュ

# PAGETOP ボタン（x は全画像共通で 991-1141）
PAGETOP = {
    "IMG_0085": (991, 1421, 1142, 1492),
    "IMG_0093": (991, 1359, 1142, 1449),
    "IMG_0105": (991, 1483, 1142, 1634),
}
ALPHA_KEEP = 0.318       # 下地が透ける割合（白地 255 → 実測 188 から逆算）


def strip_pagetop(a, box):
    """半透明グレーのボタンを逆合成して下地を復元する。"""
    x0, y0, x1, y1 = box
    x0, y0 = max(0, x0 - 3), max(0, y0 - 3)
    x1, y1 = min(a.shape[1], x1 + 3), min(a.shape[0], y1 + 3)
    sub = a[y0:y1, x0:x1].astype(float)

    # ボタンが白地に重なった部分の実測色。ベタ塗り部分だけを見る（純白の外側と
    # 下地の文字を除く）ことで、逆合成後に色かぶりが残らないようにする。
    raw_lum = sub.mean(axis=2)
    flat = (raw_lum > 170) & (raw_lum < 200)
    obs_white = np.median(sub[flat], axis=0)
    k = obs_white - ALPHA_KEEP * 255
    rec = np.clip((sub - k) / ALPHA_KEEP, 0, 255)

    # 「^」と「PAGETOP」の白字は逆合成しても淡いグレーの輪郭として残る。
    # 下地の文字（濃い）から離れた淡い画素だけを白に飛ばす。文字のアンチエイリアスは
    # 必ず濃い画素に隣接するので、濃い画素を膨張させたマスクで保護する。
    lum = rec.mean(axis=2)
    dark = lum < 165
    near_dark = dark.copy()
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            near_dark |= np.roll(np.roll(dark, dy, axis=0), dx, axis=1)
    w = np.where(near_dark, 1.0, np.clip((165 - lum) / 25.0, 0, 1))[:, :, None]
    rec = rec * w + 255 * (1 - w)

    a[y0:y1, x0:x1] = rec.astype(int)
    return a


def extend_right(a, new_w, sample_x):
    """右端が切れている画像の余白と枠線を復元する。"""
    h, w, _ = a.shape
    out = np.zeros((h, new_w, 3), dtype=a.dtype)
    out[:, :w] = a
    out[:, w:] = a[:, sample_x][:, None, :]
    out[:, new_w - 3:] = np.array(BORDER)
    return out


def find_rows(a):
    """ヘッダー帯の区切り線・「女性…」行・メニュー枠の罫線位置を返す。"""
    h, w, _ = a.shape
    mid = a[:, int(w * 0.17):int(w * 0.83)]
    purple = ((mid[:, :, 0] > 110) & (mid[:, :, 0] < 190) &
              (mid[:, :, 2] > 150) & (mid[:, :, 2] - mid[:, :, 1] > 40)).mean(axis=1)
    sep = next(y for y in range(min(400, h)) if purple[y] > 0.9)

    band = np.abs(a[:sep, int(w * 0.56):int(w * 0.96)] - BAND).sum(axis=2) > 40
    t0 = min(y for y in range(sep) if band[y].mean() > 0.01)

    x0, x1 = int(w * 0.05), int(w * 0.95)
    reg = a[:, x0:x1]
    gray = (((reg.max(axis=2) - reg.min(axis=2)) < 18) &
            (reg.mean(axis=2) > 160) & (reg.mean(axis=2) < 235)).mean(axis=1)
    lines, groups = [y for y in range(h) if gray[y] > 0.95], []
    for y in lines:
        if groups and y - groups[-1][-1] <= 2:
            groups[-1].append(y)
        else:
            groups.append([y])
    below = [g[0] for g in groups if g[0] > sep + 100]
    return sep, t0, below


def card_columns(a):
    nonwhite = (np.abs(a - 255).sum(axis=2) > 30).mean(axis=0)
    cols = [x for x in range(a.shape[1]) if nonwhite[x] > 0.9]
    return cols[0], cols[-1]


def normalize(path):
    name = os.path.splitext(os.path.basename(path))[0]
    a = np.array(Image.open(path).convert("RGB")).astype(int)

    if name in PAGETOP:
        a = strip_pagetop(a, PAGETOP[name])
    if name == "IMG_0109":          # 右端が 17px ほど切れている
        a = extend_right(a, 1177, 1150)

    sep, t0, below = find_rows(a)
    left, right = card_columns(a)

    # 上端: 「女性/…」行の直上で切り、その上には帯の無地部分（文字行とセパレータの間の
    # 40px）をそのまま移植する。アイコンのアンチエイリアスが残らないよう元画像の帯上部は
    # 使わない。1行を複製するとJPEGのブロックノイズが縦に伸びて筋になるため、帯ごと使う。
    start = t0
    filler = a[t0 + TEXT_H + 1:t0 + TEXT_H + 1 + TOP_PAD, left:right + 1]

    # 下端: メニュー枠の下罫線。無ければ画像末尾に罫線を足す
    menu_bottom = below[-1] if len(below) >= 2 else None
    if menu_bottom is not None and menu_bottom > below[0] + 120:
        body = a[start:menu_bottom + 3, left:right + 1]
    else:
        body = a[start:, left:right + 1]
        rule = np.tile(np.array(BORDER), (3, body.shape[1], 1))
        body = np.concatenate([body, rule], axis=0)

    top_rule = np.tile(np.array(BORDER), (3, body.shape[1], 1))
    out = np.concatenate([top_rule, filler, body], axis=0).astype(np.uint8)

    im = Image.fromarray(out)
    if im.width != TARGET_W:
        im = im.resize((TARGET_W, round(im.height * TARGET_W / im.width)), Image.LANCZOS)
    os.makedirs(DST, exist_ok=True)
    im.save(f"{DST}/{name}.png")
    return name, im.size, sep - t0


if __name__ == "__main__":
    for p in sorted(glob.glob(f"{SRC}/*.jpg")):
        name, size, _ = normalize(p)
        print(f"{name:14s} {size[0]}x{size[1]}")
