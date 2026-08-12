#!/usr/bin/env python3
"""正規化した口コミ画像を lp/index.html の Voice カルーセルに埋め込む。

採用順 = 文章量（本文の描画高さ）の降順。同数のものは投稿日の新しい順。
"""
import base64
import io
import re

from PIL import Image

LP = "/Users/shunsuke/Desktop/美喜のinstagram/lp/index.html"
SRC = "normalized"
QUALITY = 80

# (ファイル, 投稿者属性, 投稿日, alt に書く要旨)
REVIEWS = [
    ("IMG_0105", "女性・40代・会社員", "2026/7/26",
     "個室のジャグジーで身体を温めてから施術に入る流れが心地よく、肩・首・腕のコリを重点的にほぐしてもらえた。終わったあとは身体が軽く、姿勢まで伸びた感覚だったという声。"),
    ("IMG_0093", "女性・30代前半・会社員", "2025/11/19",
     "ブライダルエステとして利用。背中やお腹まわりのビフォーアフター写真、気になる箇所へのマシンの当て方、自宅でできる運動まで教えてもらい、理想の体型で結婚式に臨めたという声。"),
    ("IMG_0085", "女性・30代前半・会社員", "2025/6/15",
     "定期的なメンテナンスで通っていて、今回は結婚式の前撮りのために来店。前回の体型や体質を覚えていてもらえたこと、一人ひとりに合わせた施術に感激したという声。"),
    ("IMG_9584", "女性・30代前半・主婦", "2023/3/16",
     "2回目のブライダルエステ。痩身を目的に通っていて、施術以外の日の過ごし方や運動・食事のアドバイスももらえた。挙式場が決まり次第通い始めるのがおすすめだという声。"),
    ("IMG_0095", "女性・60代・パート／アルバイト", "2026/5/31",
     "個室にベッドとジャグジー、シャワーブースがあり、施術前に身体が温まって開放的な気分になれた。クローゼットのセンサーライトなど細かい配慮も心地よかったという声。"),
    ("IMG_0108", "女性・30代前半", "2026/6/24",
     "事前のカウンセリングが丁寧で、悩みに合わせたマシンを提案してもらえて安心感があった。ボディはコリがほぐれてラインが整い、フェイシャルは目もとが軽くなったという声。"),
    ("IMG_0110", "女性・30代前半", "2026/6/15",
     "最新のマシンを使った施術。じんわり温かく心地よいのに終わったあとは身体が軽く、痛い痩身マシンが多いなかで気持ちよく受けられたという声。"),
    ("IMG_0091", "女性・30代前半・自営業", "2026/3/1",
     "マタニティエステとして利用。妊娠中の浮腫みや腰痛が楽になり、施術中も体勢がつらくないか都度確認してもらえるので安心して任せられるという声。"),
    ("IMG_0092", "女性・30代前半・会社員", "2025/11/22",
     "誕生日のご褒美として来店。ジェットバスで芯から身体を温めてから、こわばった背中や肩を流してもらい、久しぶりにぐっすり眠れたという声。"),
    ("IMG_3854", "女性・20代後半・会社員", "2023/6/5",
     "担当者の施術と接客が何より良く、丁寧に話を聞いて自分に合ったものを提案してもらえるので、いつも身体が軽くなって満足しているという声。"),
    ("IMG_0109", "女性・30代前半・自営業", "2026/6/22",
     "間隔を空けずに来店したところ、帰りは身体がとても軽やかで、むくみが取れたのをより実感できたという声。"),
]


def figure(name, who, date, gist):
    im = Image.open(f"{SRC}/{name}.png").convert("RGB")
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=QUALITY, method=6)
    b64 = base64.b64encode(buf.getvalue()).decode()
    alt = f"{who}の口コミ（総合5.0・{date}投稿）。{gist}"
    return (
        '            <figure class="vcard">'
        f'<img src="data:image/webp;base64,{b64}" '
        f'alt="{alt}" width="{im.width}" height="{im.height}" decoding="async"></figure>'
    )


def main():
    html = open(LP, encoding="utf-8").read()
    pattern = re.compile(
        r'(<div class="carousel-track" id="vtrack">\n).*?(\n          </div>)',
        re.S,
    )
    if not pattern.search(html):
        raise SystemExit("vtrack ブロックが見つからない")
    figures = "\n".join(figure(*r) for r in REVIEWS)
    html = pattern.sub(lambda m: m.group(1) + figures + m.group(2), html, count=1)
    open(LP, "w", encoding="utf-8").write(html)
    print(f"embedded {len(REVIEWS)} reviews / index.html = {len(html)/1024/1024:.2f} MB")


if __name__ == "__main__":
    main()
