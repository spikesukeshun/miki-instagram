#!/usr/bin/env python3
"""lp/index.html から Web公開版（lp/dist/）を組み立てる。

`lp/index.html` は Artifact 用に「殻なし・画像は全部 data URI」で作られている。
そのままサーバに置くと quirks モードになって横スクロールが壊れ、2.8MB を一気に読む。
このスクリプトが Web 用に

  - <!doctype> 以下の殻を被せる
  - data URI 画像29点を外部ファイルに出す（JPEG は WebP に変換）
  - <img> に loading="lazy" を付ける
  - SEO 用の head（meta / OGP / JSON-LD）を足す
  - robots.txt / sitemap.xml / _headers / ogp.jpg を書き出す

を行う。**`lp/index.html` には一切書き戻さない。** Artifact 版はそのまま生き続ける。

使い方:
    python3 lp/tools/build_site.py
    python3 lp/tools/build_site.py --gsc-token XXXX   # site.json に保存して埋め込む
"""
import argparse
import base64
import hashlib
import io
import json
import os
import re
import shutil
import urllib.parse
from datetime import date

from PIL import Image, ImageDraw, ImageFont

LP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(LP_DIR, "index.html")
CONF = os.path.join(LP_DIR, "site.json")
DIST = os.path.join(LP_DIR, "dist")
IMGDIR = os.path.join(DIST, "img")

WEBP_QUALITY = 82
# ⚠ サブタイプは `\w+` では足りない。`svg+xml` の `+` を取りこぼして
#    その画像だけ data URI のまま HTML に residue として残る（無言で）。
DATA_URI_RE = re.compile(r"data:image/([\w+.-]+);base64,([A-Za-z0-9+/=]+)")

# ⚠ `<img[^>]*>` は使えない。属性値の中の `>`（alt="A > B" など）で切れて、
#    そこに loading="lazy" を挿し込むと属性が壊れる。しかも `<img` の個数とは
#    一致してしまうので件数チェックでも検知できない。引用符を跨げる形にする。
IMG_TAG_RE = re.compile(r"""<img\b(?:[^>"']|"[^"]*"|'[^']*')*>""")
QUOTED_ATTR_RE = re.compile(r""""[^"]*"|'[^']*'""")

# OGP画像の文字に使う。macOS標準のものを順に探す。
FONT_CANDIDATES = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Supplemental/Osaka.ttf",
]


# ---------------------------------------------------------------- 画像

def externalize_images(html):
    """data URI を外部ファイルに書き出し、HTML内の参照を差し替える。

    ⚠ <img src> だけでなく CSS の background-image と**カスタムプロパティ**
    （--hero-img / --concept-img）にも data URI が入っている。文脈で見分けると
    取りこぼすので、data URI 文字列そのものを全文置換する。
    """
    os.makedirs(IMGDIR, exist_ok=True)
    mapping = {}   # data URI -> /img/xxx.webp
    raw = {}       # data URI -> 元のバイト列（OGP用に使う）
    saved = kept = 0

    for m in DATA_URI_RE.finditer(html):
        uri = m.group(0)
        if uri in mapping:
            continue
        fmt, b64 = m.group(1).lower(), m.group(2)
        data = base64.b64decode(b64)
        raw[uri] = data

        out, ext = data, ("webp" if fmt == "webp" else "jpg")
        if fmt in ("jpeg", "jpg"):
            # JPEG は WebP にすると大抵小さくなる。ならなければ元のまま使う。
            im = Image.open(io.BytesIO(data))
            buf = io.BytesIO()
            im.save(buf, "WEBP", quality=WEBP_QUALITY, method=6)
            if buf.tell() < len(data):
                out, ext = buf.getvalue(), "webp"
                saved += len(data) - len(out)
            else:
                kept += 1

        name = f"{hashlib.sha256(out).hexdigest()[:12]}.{ext}"
        with open(os.path.join(IMGDIR, name), "wb") as f:
            f.write(out)
        mapping[uri] = f"/img/{name}"

    for uri, path in mapping.items():
        html = html.replace(uri, path)

    # ⚠ 取りこぼしは静かに起きる（正規表現がサブタイプや改行入りbase64に合わないなど）。
    #    残っていたら 2.8MB 側に居座り続けて誰も気づかないので、ここで落とす。
    if "base64," in html:
        leftover = re.search(r"data:[^\"')\s]{0,60}", html)
        raise SystemExit(f"外部化できなかった data URI が残っている: {leftover.group(0) if leftover else '?'}")

    print(f"  画像 {len(mapping)}点を外部化"
          f"（WebP変換で {saved/1024:.0f}KB 削減 / 変換せず据え置き {kept}点）")
    return html, mapping, raw


def add_lazy_loading(html):
    """<img> に loading="lazy" と decoding="async" を足す。

    このLPの <img> 13点は施術写真2点と口コミスクショ11点で、**全部ファーストビュー外**。
    ヒーローとコンセプト写真は CSS 側（--hero-img / --concept-img）なので lazy の対象外であり、
    そちらは head の preload で先に取りに行かせる。
    """
    n = skipped = 0

    def repl(m):
        nonlocal n, skipped
        tag = m.group(0)
        # ⚠ 属性値を潰してから探すこと。alt="loading=x" のような本文で誤スキップする。
        if re.search(r"\bloading\s*=", QUOTED_ATTR_RE.sub('""', tag)):
            skipped += 1        # 既に指定済み（ヒーローを eager にした等）。触らない。
            return tag
        n += 1
        # 自己終了 `<img ... />` の `/` を落としてから属性を足す
        # （残すと `<img ... / loading="lazy">` になり parse error）
        return tag[:-1].rstrip().rstrip("/").rstrip() + ' loading="lazy" decoding="async">'

    total = html.count("<img")
    html = IMG_TAG_RE.sub(repl, html)

    # 上の正規表現は引用符を跨げるので理屈の上では一致するはずだが、
    # 想定外の書き方（引用符なし属性に `>` を含む等）で静かにずれると
    # 属性が壊れたHTMLをそのまま出してしまう。実数と突き合わせて落とす。
    if n + skipped != total:
        raise SystemExit(
            f"<img> の抽出数が合わない（付与 {n} / 既存 {skipped} / 実在 {total}）。"
            f"build_site.py の IMG_TAG_RE を見直すこと")

    note = f"（うち {skipped}点は指定済みのため据え置き）" if skipped else ""
    print(f"  <img> {n}点に loading=\"lazy\" を付与{note}")
    return html


def find_css_image(html, prop):
    """--hero-img: url("/img/xxx.webp") のような宣言から画像パスを取り出す。"""
    m = re.search(re.escape(prop) + r"\s*:\s*url\(\s*[\"']?(/img/[^\"')]+)", html)
    return m.group(1) if m else None


# ---------------------------------------------------------------- OGP

def load_font(size):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return None


def build_ogp(raw, mapping, html, conf):
    """コンセプト写真（施術ルーム）を 1200x630 にして文字を載せる。

    ⚠ og:image に data URI は使えない。SNSのクローラは実ファイルのURLしか読まない。
    """
    # --concept-img（施術ルームの写真）が指している画像を使う。
    # ⚠ 「見つからなければ一番大きい画像」のようなフォールバックは置かない。
    #    OGPは集客の第一印象で、口コミスクショなどが黙って選ばれると事故に気づけない。
    #    見つからなければ落として原因を直す（create_post.py と同じ思想）。
    m = re.search(r"--concept-img\s*:\s*url\(\s*[\"']?(/img/[^\"')]+)", html)
    if not m:
        raise SystemExit("OGP画像の元になる --concept-img が見つからない。"
                         "lp/index.html の変数名が変わっていないか確認すること")

    # 外部化後のWebPではなく元データから起こす（WebP→JPEGの二重劣化を避ける）
    src = None
    for uri, data in raw.items():
        if mapping.get(uri) == m.group(1):
            src = data
            break
    if src is None:
        want = os.path.join(DIST, m.group(1).lstrip("/"))
        if not os.path.exists(want):
            raise SystemExit(f"OGPの元画像が見つからない: {m.group(1)}")
        with open(want, "rb") as f:
            src = f.read()

    im = Image.open(io.BytesIO(src)).convert("RGB")
    # 1200x630 に中央基準でトリミング
    tw, th = 1200, 630
    scale = max(tw / im.width, th / im.height)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    left, top = (im.width - tw) // 2, (im.height - th) // 2
    im = im.crop((left, top, left + tw, top + th))

    # 文字を読ませるための暗幕（下半分にグラデーション）
    veil = Image.new("L", (1, th))
    for y in range(th):
        t = max(0.0, (y - th * 0.35) / (th * 0.65))
        veil.putpixel((0, y), int(165 * (t ** 1.4)))
    veil = veil.resize((tw, th))
    im = Image.composite(Image.new("RGB", (tw, th), (28, 24, 20)), im, veil)

    d = ImageDraw.Draw(im)
    lines = conf.get("og_image_text") or ["MIKI"]
    f_big, f_small = load_font(104), load_font(38)
    if f_big:
        d.text((72, th - 232), lines[0], font=f_big, fill=(255, 252, 246))
        if len(lines) > 1 and f_small:
            d.text((78, th - 96), lines[1], font=f_small, fill=(232, 224, 210))
        # ゴールドの罫線
        d.rectangle([74, th - 250, 74 + 86, th - 246], fill=(176, 138, 70))

    out = os.path.join(DIST, "ogp.jpg")
    im.save(out, "JPEG", quality=86, optimize=True, progressive=True)
    print(f"  ogp.jpg 生成 1200x630 / {os.path.getsize(out)/1024:.0f}KB")
    return "ogp.jpg"


# ---------------------------------------------------------------- head

def build_ga4(conf):
    """GA4 の計測タグと、予約導線のクリック計測を返す。

    ⚠ 目的は PV ではなく**コンバージョン**。「何人来たか」より
    「何人が DM / ホットペッパーに進んだか」が知りたい数字なので、
    アウトバウンドのクリックをイベントとして送る。

    ⚠ 既存の予約導線ロジック（data-hp-target のURL差し替え）には触らない。
    キャプチャ段階の受動的なリスナーで観測するだけ。
    """
    mid = (conf.get("ga4_measurement_id") or "").strip()
    if not mid:
        return ""

    return f"""
<script async src="https://www.googletagmanager.com/gtag/js?id={mid}"></script>
<script>
window.dataLayer=window.dataLayer||[];
function gtag(){{dataLayer.push(arguments)}}
gtag('js',new Date());
gtag('config','{mid}');

// 予約導線のクリック計測。選択中のコースも一緒に送る。
document.addEventListener('click',function(e){{
  var a=e.target.closest&&e.target.closest('a[href]');
  if(!a) return;
  var href=a.getAttribute('href')||'';
  var sel=document.querySelector('[data-hp][aria-pressed="true"]');
  var course=sel?(sel.textContent||'').replace(/\\s+/g,' ').trim().slice(0,40):'未選択';
  if(href.indexOf('ig.me')>-1||href.indexOf('instagram.com/m/')>-1){{
    gtag('event','cta_dm',{{course:course,link_url:href}});
  }} else if(href.indexOf('beauty.hotpepper.jp')>-1){{
    var m=href.match(/couponId=(CP\\d+)/);
    gtag('event','cta_hotpepper',{{course:course,coupon:m?m[1]:'なし',link_url:href}});
  }}
}},true);
</script>"""


GOOGLE_PARTNER_SITES = "https://policies.google.com/technologies/partner-sites"
GA_OPTOUT = "https://tools.google.com/dlpage/gaoptout/"


def build_privacy_notice(conf):
    """GA4を入れる場合だけ、フッターに告知とポリシーへのリンクを出す。

    ⚠ Web版にだけ入る。Artifact版（lp/index.html）には影響しない。
    """
    if not (conf.get("ga4_measurement_id") or "").strip():
        return ""
    return f"""
<div style="background:#F4EDE1;border-top:1px solid rgba(44,39,35,.07);
            padding:18px 20px;text-align:center">
  <p style="margin:0 auto;max-width:52em;font-size:11px;line-height:2;color:#8A8073;
            font-family:'Hiragino Sans','Hiragino Kaku Gothic ProN',sans-serif">
    <span style="display:inline-block">当サイトはアクセス状況の把握のため
      Cookie を用いた Google アナリティクスを利用しています。</span>
    <span style="display:inline-block;white-space:nowrap">
      <a href="/privacy.html" style="color:#8C6D33">プライバシーポリシー</a>
      <span style="opacity:.5;padding:0 .4em">／</span>
      <a href="{GOOGLE_PARTNER_SITES}" target="_blank" rel="noopener noreferrer"
         style="color:#8C6D33">Google による情報の使用について</a>
    </span>
  </p>
</div>"""


def write_privacy_page(conf):
    """Google アナリティクス利用規約 第7条が要求する項目を満たすページ。

    規約が求めるのは次の4点：
      ① プライバシーポリシーを掲示すること
      ② Cookie・端末識別子等の使用を告知すること
      ③ GAの使用と、収集・処理の方法を開示すること
      ④ 「Googleのサービスを使用するサイトからの情報のGoogleによる使用」への
         目立つリンクを置くこと
    ⚠ これはGoogleとの契約上の義務。改正電気通信事業法の外部送信規律とは別物で、
      そちらは「自己の情報発信のためのサイト」は対象外のためこのLPには適用されない。
    ⚠ 法的助言ではない。最終的な妥当性が問われる場面では専門家に確認すること。

    GA4を入れないビルドではこのページ自体を出力しない（嘘の告知を置かないため）。
    """
    if not (conf.get("ga4_measurement_id") or "").strip():
        return
    url = conf["url"]
    body = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>プライバシーポリシー｜MIKI</title>
<meta name="description" content="当サイトにおけるアクセス解析および個人情報の取り扱いについて。">
<link rel="canonical" href="{url}privacy.html">
<link rel="icon" href="{favicon_data_uri()}">
<style>
  :root{{color-scheme:light}}
  body{{margin:0;background:#FBF8F2;color:#2C2723;padding:0 20px 80px;
       font-family:"Hiragino Sans","Hiragino Kaku Gothic ProN","Yu Gothic",sans-serif;
       font-size:15px;line-height:2}}
  .wrap{{max-width:44em;margin:0 auto}}
  header{{padding:56px 0 40px;border-bottom:1px solid rgba(44,39,35,.12);margin-bottom:44px}}
  .brand{{font-family:"Optima","Futura",serif;letter-spacing:.28em;font-size:15px;color:#8C6D33}}
  h1{{font-family:"Hiragino Mincho ProN","Yu Mincho",serif;font-size:27px;font-weight:400;
     margin:.5em 0 0;letter-spacing:.04em}}
  h2{{font-family:"Hiragino Mincho ProN","Yu Mincho",serif;font-size:18px;font-weight:400;
     margin:2.6em 0 .7em;padding-left:.6em;border-left:3px solid #B08A46;letter-spacing:.04em}}
  p,li{{color:#5C534A}}
  ul{{padding-left:1.3em}} li{{margin:.3em 0}}
  a{{color:#8C6D33}}
  .note{{background:#F4EDE1;border-radius:10px;padding:16px 20px;font-size:13px;line-height:1.95}}
  footer{{margin-top:64px;padding-top:28px;border-top:1px solid rgba(44,39,35,.12);
         font-size:13px;color:#8A8073}}
  .date{{margin-top:2.5em;font-size:13px;color:#8A8073}}
</style>
</head>
<body>
<div class="wrap">
<header>
  <div class="brand">MIKI</div>
  <h1>プライバシーポリシー</h1>
</header>

<h2>1. アクセス解析ツールの利用について</h2>
<p>
  当サイトでは、サイトの利用状況を把握し内容を改善するために、Google LLC が提供する
  アクセス解析ツール「Google アナリティクス」を利用しています。
</p>
<p>
  Google アナリティクスは、<strong>Cookie（クッキー）および類似の技術</strong>を用いて、
  お客様のご利用状況に関する情報を収集します。この情報はお客様のブラウザから Google LLC へ送信され、
  同社において保存・処理されます。
</p>

<h2>2. 収集する情報</h2>
<p>Google アナリティクスを通じて、主に次の情報を取得します。</p>
<ul>
  <li>閲覧されたページと閲覧の順序、滞在時間、スクロールの到達状況</li>
  <li>当サイトを訪れる直前に経由したサイトや広告等の参照元</li>
  <li>ご利用の端末の種類、OS、ブラウザ、画面サイズ、言語設定</li>
  <li>IPアドレスから推定される、おおよその地域（国・都道府県程度）</li>
  <li>サイト内のボタン（DMでのご相談、ご予約サイトへの遷移）の操作状況</li>
</ul>
<p class="note">
  これらは<strong>統計的にサイトの利用状況を把握するための情報</strong>であり、
  氏名・住所・電話番号・メールアドレスなど、お客様個人を直接特定できる情報は含まれません。
  当サイトが個人を特定する目的でこれらの情報を利用することはありません。
</p>

<h2>3. Google による情報の使用について</h2>
<p>
  収集された情報が Google LLC においてどのように取り扱われるかについては、
  同社が公開する下記のページをご確認ください。
</p>
<p>
  <a href="{GOOGLE_PARTNER_SITES}" target="_blank" rel="noopener noreferrer">
    Google のサービスを使用するサイトやアプリから収集した情報の Google による使用
  </a>
</p>

<h2>4. 収集を停止したい場合（オプトアウト）</h2>
<p>
  Google アナリティクスによる情報収集は、お客様ご自身で無効にすることができます。
  下記のアドオンをブラウザに導入していただくか、ブラウザの設定で Cookie を無効にしてください。
  無効にした場合でも、当サイトの閲覧やご予約にはお使いいただけます。
</p>
<p>
  <a href="{GA_OPTOUT}" target="_blank" rel="noopener noreferrer">
    Google アナリティクス オプトアウト アドオン
  </a>
</p>

<h2>5. 外部サービスへのリンクについて</h2>
<p>
  当サイトには、Instagram のダイレクトメッセージおよびご予約サイト（ホットペッパービューティー）への
  リンクが含まれています。<strong>リンク先での情報の取り扱いは、各サービスの提供事業者の
  プライバシーポリシーに従います。</strong>当サイトの本ポリシーは適用されません。
</p>

<h2>6. お問い合わせ</h2>
<p>
  本ポリシーに関するお問い合わせは、
  <a href="{conf['instagram']}" target="_blank" rel="noopener noreferrer">Instagram アカウント</a>
  のダイレクトメッセージよりご連絡ください。
</p>

<h2>7. 本ポリシーの変更</h2>
<p>
  本ポリシーの内容は、法令の変更や利用するサービスの変更に応じて、予告なく改定することがあります。
  改定後の内容は本ページに掲載した時点から適用されます。
</p>

<p class="date">制定日：{conf['_last_modified']}</p>

<footer>
  <a href="{url}">← トップページへ戻る</a>
</footer>
</div>
</body>
</html>
"""
    with open(os.path.join(DIST, "privacy.html"), "w", encoding="utf-8") as f:
        f.write(body)
    print("  privacy.html を生成（GA4有効のため）")


def favicon_data_uri():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
           '<text y=".9em" font-size="90">\U0001F33F</text></svg>')
    return "data:image/svg+xml," + urllib.parse.quote(svg)


def build_jsonld(conf):
    url = conf["url"]
    # ⚠ サロン名・住所は入れない（CLAUDE.md の絶対ルール）。
    #    指名検索を取るのが目的なので Person + ProfessionalService で足りる。
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Person",
                "@id": url + "#miki",
                "name": "MIKI",
                "jobTitle": "エステティシャン",
                "image": url + "ogp.jpg",
                "url": url,
                "sameAs": [conf["instagram"]],
                "knowsAbout": ["痩身エステ", "ブライダルエステ", "リンパケア", "フェイシャル"],
                "hasCredential": {
                    "@type": "EducationalOccupationalCredential",
                    "credentialCategory": "certification",
                    "name": "CIDESCO インターナショナルライセンス",
                },
            },
            {
                "@type": "ProfessionalService",
                "@id": url + "#service",
                "name": "MIKI｜痩身・ブライダルエステ",
                "url": url,
                "image": url + "ogp.jpg",
                "description": conf["description"],
                "provider": {"@id": url + "#miki"},
                "areaServed": {"@type": "Place", "name": conf["area"]},
                "priceRange": conf["price_range"],
                "currenciesAccepted": "JPY",
            },
            {
                "@type": "WebSite",
                "@id": url + "#website",
                "url": url,
                "name": conf["title"],
                "inLanguage": "ja",
            },
        ],
    }


def build_head(conf, ogp, preloads):
    url, esc = conf["url"], lambda s: (s.replace("&", "&amp;").replace("<", "&lt;")
                                       .replace(">", "&gt;").replace('"', "&quot;"))
    p = [
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<title>{esc(conf["title"])}</title>',
        f'<meta name="description" content="{esc(conf["description"])}">',
        f'<link rel="canonical" href="{url}">',
        f'<link rel="icon" href="{favicon_data_uri()}">',
        '<meta name="format-detection" content="telephone=no">',
        '<meta name="theme-color" content="#FBF8F2">',
    ]
    if conf.get("google_site_verification"):
        p.append(f'<meta name="google-site-verification" '
                 f'content="{esc(conf["google_site_verification"])}">')

    p += [
        '<meta property="og:type" content="website">',
        f'<meta property="og:url" content="{url}">',
        f'<meta property="og:title" content="{esc(conf.get("og_title", conf["title"]))}">',
        f'<meta property="og:description" content="{esc(conf["description"])}">',
        f'<meta property="og:image" content="{url}{ogp}">',
        '<meta property="og:image:width" content="1200">',
        '<meta property="og:image:height" content="630">',
        '<meta property="og:site_name" content="MIKI">',
        '<meta property="og:locale" content="ja_JP">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{esc(conf.get("og_title", conf["title"]))}">',
        f'<meta name="twitter:description" content="{esc(conf["description"])}">',
        f'<meta name="twitter:image" content="{url}{ogp}">',
    ]
    # ヒーローとコンセプト写真は CSS 背景なので lazy にできない。逆に先に取らせる。
    for href in preloads:
        if href:
            p.append(f'<link rel="preload" as="image" href="{href}">')

    # ⚠ json.dumps は `</script>` をエスケープしない。site.json の文言に紛れ込むと
    #    script が早期に閉じて以降が HTML として解釈される。`<` を割っておく。
    ld = json.dumps(build_jsonld(conf), ensure_ascii=False, separators=(",", ":"))
    ld = ld.replace("</", "<\\/")
    p.append(f'<script type="application/ld+json">{ld}</script>')
    p.append(build_ga4(conf))
    return "\n".join(x for x in p if x)


# ---------------------------------------------------------------- 付随ファイル

def write_robots(conf):
    url = conf["url"]
    # AIクローラは全部許可（ユーザー判断）。ChatGPT/Copilot 経由で見つけてもらう経路を残す。
    body = (
        "# MIKI LP — 検索エンジン・AIクローラともに全面許可\n"
        "User-agent: *\n"
        "Allow: /\n"
        "Content-Signal: search=yes, ai-input=yes, ai-train=yes\n"
        "\n"
        f"Sitemap: {url}sitemap.xml\n"
    )
    with open(os.path.join(DIST, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(body)


def write_sitemap(conf, lastmod):
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        '  <url>\n'
        f'    <loc>{conf["url"]}</loc>\n'
        f'    <lastmod>{lastmod}</lastmod>\n'
        '    <changefreq>monthly</changefreq>\n'
        '    <priority>1.0</priority>\n'
        '  </url>\n'
        '</urlset>\n'
    )
    with open(os.path.join(DIST, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(body)


def write_headers():
    # 画像は内容ハッシュ名なので実質不変。HTMLは短命にして更新を即反映させる。
    # ⚠ セキュリティヘッダは `/` だけに書かないこと。画像・404・robots に掛からない。
    #    nosniff は画像配信にこそ効くので `/*` に分けて全体へ掛ける。
    body = (
        "/*\n"
        "  X-Content-Type-Options: nosniff\n"
        "  Referrer-Policy: strict-origin-when-cross-origin\n"
        "\n"
        "/img/*\n"
        "  Cache-Control: public, max-age=31536000, immutable\n"
        "\n"
        "/ogp.jpg\n"
        "  Cache-Control: public, max-age=86400\n"
        "\n"
        "/\n"
        "  Cache-Control: public, max-age=300, must-revalidate\n"
    )
    with open(os.path.join(DIST, "_headers"), "w", encoding="utf-8") as f:
        f.write(body)


def write_404(conf):
    """1ページサイトなので未定義パスは素直に404を返す。

    ⚠ トップへリダイレクトする「ソフト404」にはしないこと。Google が
    「実在しないURLが200を返すサイト」と判断してインデックス品質が落ちる。
    """
    body = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>ページが見つかりません｜MIKI</title>
<link rel="icon" href="{favicon_data_uri()}">
<style>
  :root{{color-scheme:light}}
  body{{margin:0;min-height:100svh;display:grid;place-items:center;background:#FBF8F2;color:#2C2723;
       font-family:"Hiragino Mincho ProN","Yu Mincho",serif;text-align:center;padding:24px}}
  .n{{font-size:clamp(48px,12vw,88px);color:#B08A46;letter-spacing:.06em;margin:0 0 .2em}}
  p{{color:#5C534A;line-height:2;margin:0 0 2em;font-size:15px}}
  a{{display:inline-block;padding:14px 34px;background:#8C6D33;color:#F3EEE2;text-decoration:none;
     border-radius:999px;font-size:14px;letter-spacing:.08em}}
</style>
</head>
<body>
<div>
  <p class="n">404</p>
  <p>お探しのページは見つかりませんでした。</p>
  <a href="{conf['url']}">トップへ戻る</a>
</div>
</body>
</html>
"""
    with open(os.path.join(DIST, "404.html"), "w", encoding="utf-8") as f:
        f.write(body)


def write_indexnow(conf):
    # ⚠ キーはそのままファイル名になる。形式は validate_conf() で検証済み
    #    （`/` や `..` によるパストラバーサルはそこで弾く）。
    key = (conf.get("indexnow_key") or "").strip()
    if not key:
        return
    with open(os.path.join(DIST, f"{key}.txt"), "w", encoding="utf-8") as f:
        f.write(key)
    print(f"  IndexNow キーファイル {key}.txt を配置")


# ---------------------------------------------------------------- main

def validate_conf(conf):
    """設定の検証は **dist を消す前に** まとめて行う。

    ⚠ 途中で落ちると、動いていた dist/ が中途半端な状態で残る
    （画像だけあって index.html が無い等）。それをデプロイすると事故になる。
    """
    # URLは全箇所で「末尾スラッシュあり」を前提に連結している（url+"ogp.jpg" 等）。
    # 落とすと https://…workers.devogp.jpg がエラーなく生成される。
    if not conf.get("url", "").endswith("/"):
        raise SystemExit(f'site.json の "url" は末尾に / が必要: {conf.get("url")!r}')

    mid = (conf.get("ga4_measurement_id") or "").strip()
    if mid and not re.fullmatch(r"G-[A-Z0-9]{4,20}", mid):
        raise SystemExit(f"ga4_measurement_id の形式が不正（G-XXXXXXXXXX）: {mid!r}")

    key = (conf.get("indexnow_key") or "").strip()
    if key and not re.fullmatch(r"[A-Za-z0-9-]{8,128}", key):
        raise SystemExit(f"indexnow_key が不正（英数字とハイフンのみ・8〜128文字）: {key!r}")

    for field in ("title", "description", "instagram", "area", "price_range"):
        if not conf.get(field):
            raise SystemExit(f'site.json の "{field}" が空。埋めてからビルドすること')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gsc-token", help="Search Console の所有権確認トークン（site.json に保存する）")
    ap.add_argument("--indexnow-key", help="IndexNow のキー（site.json に保存する）")
    ap.add_argument("--ga4-id", help="GA4 の測定ID G-XXXXXXXXXX（site.json に保存する）")
    args = ap.parse_args()

    with open(CONF, encoding="utf-8") as f:
        conf = json.load(f)
    if args.gsc_token:
        conf["google_site_verification"] = args.gsc_token
    if args.indexnow_key:
        conf["indexnow_key"] = args.indexnow_key
    if args.ga4_id:
        conf["ga4_measurement_id"] = args.ga4_id

    # ⚠ URLは全箇所で「末尾スラッシュあり」を前提に連結している
    #    （url+"ogp.jpg" / url+"sitemap.xml"）。落とすと
    #    https://…workers.devogp.jpg のような壊れたURLがエラーなく生成される。
    validate_conf(conf)

    with open(SRC, encoding="utf-8") as f:
        html = f.read()
    src_bytes = len(html.encode())

    # ⚠ lastmod をビルド日にすると、中身が変わっていなくても毎回「更新」の信号を出して
    #    クローラへのシグナルが濁る。ソースの内容ハッシュが変わったときだけ日付を進める。
    src_hash = hashlib.sha256(html.encode()).hexdigest()[:16]
    if conf.get("_source_hash") != src_hash:
        conf["_source_hash"] = src_hash
        conf["_last_modified"] = date.today().isoformat()
    lastmod = conf["_last_modified"]

    with open(CONF, "w", encoding="utf-8") as f:
        json.dump(conf, f, ensure_ascii=False, indent=2)
        f.write("\n")

    if os.path.exists(DIST):
        shutil.rmtree(DIST)
    os.makedirs(IMGDIR, exist_ok=True)

    print(f"入力 lp/index.html: {src_bytes/1024/1024:.2f}MB  (lastmod {lastmod})")

    # 先頭の <title> は head 側で SEO 用に差し替えるので本文からは外す
    html = re.sub(r"^\s*<title>.*?</title>\s*", "", html, count=1, flags=re.S)

    html, mapping, raw = externalize_images(html)
    html = add_lazy_loading(html)

    ogp = build_ogp(raw, mapping, html, conf)
    preloads = [find_css_image(html, "--hero-img"), find_css_image(html, "--concept-img")]

    # ⚠ HANDOFF.md 5章 serve.py の TAIL（reveal 無効化）は撮影用。ここには絶対に入れない。
    page = ("<!doctype html>\n<html lang=\"ja\">\n<head>\n"
            + build_head(conf, ogp, preloads)
            + "\n</head>\n<body>\n" + html
            + build_privacy_notice(conf)
            + "\n</body>\n</html>\n")

    with open(os.path.join(DIST, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    write_robots(conf)
    write_sitemap(conf, lastmod)
    write_headers()
    write_404(conf)
    write_privacy_page(conf)
    write_indexnow(conf)

    html_bytes = len(page.encode())
    img_bytes = sum(os.path.getsize(os.path.join(IMGDIR, f)) for f in os.listdir(IMGDIR))
    print("\n出力 lp/dist/")
    print(f"  index.html : {html_bytes/1024:>7.0f} KB  (元 {src_bytes/1024:.0f} KB / "
          f"{100*(1-html_bytes/src_bytes):.1f}% 削減)")
    print(f"  img/       : {img_bytes/1024:>7.0f} KB  ({len(os.listdir(IMGDIR))} ファイル)")
    print(f"  合計       : {(html_bytes+img_bytes)/1024:>7.0f} KB")


if __name__ == "__main__":
    main()
