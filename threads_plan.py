"""Threads 投稿の準備（候補プール・時間枠・機械チェック・シート登録）。2026-10 追加。

週次の流れ（詳細は rules/threads.md）:
  1. python3 threads_plan.py export                     # IG過去投稿から未使用の候補プールを作る
  2. python3 threads_plan.py slots --start 2026-10-06 --days 7   # 各日の時間枠を表示
  3. Claude Code が rules/threads.md を読んで threads/week_YYYY-MM-DD.json を書く
  4. python3 threads_plan.py review threads/week_YYYY-MM-DD.json  # ❌ が出たら直す（省略不可）
  5. python3 threads_plan.py register threads/week_YYYY-MM-DD.json  # タブに「確認待ち」で登録
  6. シートで本文を確認・修正し、ステータスを「承認済み」にする

事実ルール（価格・空き・コピー禁止など）は文章ではなくここのチェックで止める
（rules/incidents.md の「文章だけのルールは守られない」の教訓）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher

import requests

from load_env import load_from_zshrc
load_from_zshrc()

from threads_api import text_length, validate_topic_tag, TEXT_LIMIT  # noqa: E402

JST = timezone(timedelta(hours=9))
POOL_FILE = os.path.join("threads", "pool.json")
SKILL_FILE = "SKILL.md"

# 投稿時間テストの3枠。日ごとに 朝→昼→夜 と回し、週ごとに1つずらす
# （同じ曜日が毎週同じ枠にならないように）。
SLOTS = [("朝", "08:00"), ("昼", "12:30"), ("夜", "21:00")]

POST_TYPES = [
    "悩み起点", "施術紹介", "人柄・こだわり", "利用シーン・季節",
    "価格・キャンペーン", "会話・問いかけ", "当日の空き",
]
# Claude が申告する属性（文面から機械的に判定できないもの）
DECLARED_FLAGS = {"悩み"}
ALL_FLAGS = ["地域", "悩み", "問いかけ", "CTA", "空き", "価格"]

REGION = "六本木"
AVAILABILITY_RE = re.compile(r"空き|空いて|空席|今日.{0,6}(ご案内|行け|入れ)|本日.{0,6}(ご案内|空)|当日予約")
PRICE_RE = re.compile(r"[¥￥]\s?[\d,]+|[\d,]{3,}\s?円")
CTA_RE = re.compile(r"DM|ＤＭ|予約|ご相談|お問い合わせ|プロフィール")
QUESTION_RE = re.compile(r"[？?]")
BAIT_RE = re.compile(r"いいねして|リポストして|フォローして|保存して|拡散して|コメントして")
FORBIDDEN = {
    "AMRTA": "サロン名は書かない（CLAUDE.md 絶対ルール）",
    "Instagram限定": "Instagram の特典なので Threads では出さない",
    "治る": "効果の断定",
    "完治": "効果の断定",
    "100%": "効果の断定",
    "確実に": "効果の断定",
}
SOFT_WARN = ["絶対", "必ず", "最強", "劇的", "今だけ"]

# 元キャプションからのコピー判定：20字以上一致するブロックが本文の何割を占めるか
COPY_BLOCK_MIN = 20
COPY_RATIO_MAX = 0.5


# ── 共通 ─────────────────────────────────────────────

def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def allowed_prices() -> set:
    """価格の正は SKILL.md。ここに書かれた金額だけを使ってよい（数値は転記しない）。"""
    try:
        with open(SKILL_FILE, encoding="utf-8") as f:
            src = f.read()
    except OSError:
        return set()
    return {_price_digits(m) for m in PRICE_RE.findall(src)}


def _price_digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def detect_flags(text: str, declared: list) -> list:
    flags = set(f for f in declared if f in DECLARED_FLAGS)
    if REGION in text:
        flags.add("地域")
    if QUESTION_RE.search(text):
        flags.add("問いかけ")
    if CTA_RE.search(text):
        flags.add("CTA")
    if AVAILABILITY_RE.search(text):
        flags.add("空き")
    if PRICE_RE.search(text):
        flags.add("価格")
    return [f for f in ALL_FLAGS if f in flags]


def copy_ratio(text: str, caption: str) -> float:
    """Threads本文のうち、元キャプションと20字以上連続で一致する部分の割合。"""
    a, b = _norm(text), _norm(caption)
    if not a or not b:
        return 0.0
    sm = SequenceMatcher(None, a, b, autojunk=False)
    copied = sum(m.size for m in sm.get_matching_blocks() if m.size >= COPY_BLOCK_MIN)
    return copied / len(a)


def slot_for(day_index: int) -> tuple:
    return SLOTS[(day_index + day_index // 7) % len(SLOTS)]


def parse_dt(s: str) -> datetime | None:
    try:
        return datetime.strptime(s.strip(), "%Y/%m/%d %H:%M").replace(tzinfo=JST)
    except (ValueError, AttributeError):
        return None


def parse_media_spec(spec: str) -> tuple:
    """'carousel:0,1,2' → ('carousel', [0,1,2])。text / image / video / thumbnail はそのまま。"""
    spec = (spec or "text").strip()
    if spec.startswith("carousel:"):
        idx = [int(x) for x in spec.split(":", 1)[1].split(",") if x.strip().isdigit()]
        return "carousel", idx
    return spec, []


# ── export ───────────────────────────────────────────

def fetch_all_ig_media() -> list:
    """Instagram の全投稿（キャプション・子メディア数つき）を取得する。読み取りのみ。"""
    from instagram_api import API_BASE as IG_API_BASE  # ホスト定数は既存のものを使う
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    account = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    url = f"{IG_API_BASE}/{account}/media"
    params = {
        "access_token": token, "limit": 100,
        "fields": ("id,caption,timestamp,media_type,media_product_type,permalink,"
                   "like_count,comments_count,children{media_type}"),
    }
    out = []
    while url:
        res = requests.get(url, params=params, timeout=60)
        data = res.json()
        if "error" in data:
            raise RuntimeError(f"Instagram 投稿一覧の取得に失敗: {data['error'].get('message')}")
        out.extend(data.get("data", []))
        url = (data.get("paging") or {}).get("next")
        params = None  # next には全パラメータが含まれる
    return out


def suggest_media(item: dict) -> str:
    """Threads に付けるメディアの初期値。

    - カルーセルは先頭から最大4枚。末尾2枚は投稿システムが自動で足す CTA スライド
      （「Instagram限定20%OFF」入り）なので外す
    - リール（VIDEO）は表紙画像（thumbnail）にする。手動投稿のリールは Instagram の
      音源ライブラリを使っており、Threads への再アップロードは権利が不明なため
    """
    mt = item.get("media_type")
    if mt == "CAROUSEL_ALBUM":
        n = len((item.get("children") or {}).get("data", []))
        usable = max(n - 2, 1) if n >= 4 else n
        k = min(usable, 4)
        return "image" if k < 2 else "carousel:" + ",".join(str(i) for i in range(k))
    if mt == "VIDEO":
        return "thumbnail"
    return "image"


def build_pool(media: list, used_ids: set, limit: int) -> list:
    from theme_classifier import load_classifications, load_overrides, resolve_theme
    classifications, overrides = load_classifications(), load_overrides()
    prices_ok = allowed_prices()
    pool = []
    for m in media:
        cap = m.get("caption") or ""
        if m["id"] in used_ids or len(_norm(cap)) < 50 or "AMRTA" in cap.upper():
            continue
        theme, _ = resolve_theme(m["id"], cap, classifications, overrides)
        prices = sorted({_price_digits(p) for p in PRICE_RE.findall(cap)})
        pool.append({
            "ig_id": m["id"],
            "ig_date": (m.get("timestamp") or "")[:10],
            "permalink": m.get("permalink", ""),
            "media_type": m.get("media_type"),
            "children": len((m.get("children") or {}).get("data", [])),
            "media_suggest": suggest_media(m),
            "theme": theme,
            "likes": m.get("like_count", 0),
            "comments": m.get("comments_count", 0),
            "prices_in_caption": prices,
            "outdated_prices": [p for p in prices if p not in prices_ok],
            "caption": cap,
        })
    # 反応の良い順に並べてから、テーマが偏らないよう順番に1件ずつ取る
    pool.sort(key=lambda p: p["likes"] + 3 * p["comments"], reverse=True)
    by_theme = {}
    for p in pool:
        by_theme.setdefault(p["theme"], []).append(p)
    picked = []
    while len(picked) < limit and any(by_theme.values()):
        for theme in sorted(by_theme):
            if by_theme[theme] and len(picked) < limit:
                picked.append(by_theme[theme].pop(0))
    return picked


def used_ig_ids_from_sheet() -> set:
    import threads_store as store
    try:
        tab = store.open_posts(create=False)
    except RuntimeError:
        return set()
    return {r["元IG投稿ID"] for _, r in tab.rows()
            if r.get("元IG投稿ID") and r.get("ステータス") != store.ST_SKIPPED}


def cmd_export(args):
    used = set() if args.no_sheet else used_ig_ids_from_sheet()
    media = fetch_all_ig_media()
    print(f"Instagram 投稿 {len(media)} 件を取得 / 実験で使用済み {len(used)} 件")
    pool = build_pool(media, used, args.limit)
    if args.insights:
        from get_recent_insights import fetch_insights
        for p in pool:
            p["ig_insights"] = fetch_insights(p["ig_id"], p["media_type"])
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"exported_at": datetime.now(JST).isoformat(timespec="seconds"),
                   "allowed_prices": sorted(allowed_prices()),
                   "posts": pool}, f, ensure_ascii=False, indent=1)
    print(f"候補 {len(pool)} 件を {args.out} に書き出しました")


# ── slots ────────────────────────────────────────────

def cmd_slots(args):
    start = date.fromisoformat(args.start)
    first = date.fromisoformat(args.experiment_start or args.start)
    for i in range(args.days):
        d = start + timedelta(days=i)
        name, hm = slot_for((d - first).days)
        print(f"{d.strftime('%Y/%m/%d')} {hm}  {name}  ({'月火水木金土日'[d.weekday()]})")


# ── review ───────────────────────────────────────────

def load_pool(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError:
        return {}
    return {p["ig_id"]: p for p in data.get("posts", [])}


def review_entries(posts: list, pool: dict, prices_ok: set,
                   experiment_start: date = None) -> tuple:
    """(errors, warnings) を返す。各要素は '[n] メッセージ'。"""
    errors, warns = [], []
    seen_ids, seen_dates, openers = set(), set(), {}
    prev_type = None
    cta_count = 0
    for n, p in enumerate(posts, start=1):
        tag = f"[{n}]"
        text = (p.get("text") or "").strip()
        src = pool.get(p.get("ig_id"))
        e = lambda m: errors.append(f"{tag} {m}")  # noqa: E731
        w = lambda m: warns.append(f"{tag} {m}")  # noqa: E731

        if not text:
            e("本文が空です")
            continue
        if text_length(text) > TEXT_LIMIT:
            e(f"本文が{TEXT_LIMIT}字を超えています（{text_length(text)}字換算）")
        elif text_length(text) > 350:
            w(f"本文が長め（{text_length(text)}字）。目安は150〜350字")
        if src is None:
            e(f"ig_id {p.get('ig_id')} が候補プール（{POOL_FILE}）にありません — 事実の出どころを確認できない")
        else:
            r = copy_ratio(text, src["caption"])
            if r >= COPY_RATIO_MAX:
                e(f"元キャプションの単純コピーです（一致率 {r:.0%}）。Threads 向けに書き直す")
            elif r >= 0.3:
                w(f"元キャプションとの一致がやや多い（{r:.0%}）")
        if p.get("ig_id") in seen_ids:
            e(f"同じ Instagram 投稿（{p.get('ig_id')}）を2回使っています")
        seen_ids.add(p.get("ig_id"))

        for word, why in FORBIDDEN.items():
            if word.lower() in text.lower():
                e(f"「{word}」は使えません（{why}）")
        for word in SOFT_WARN:
            if word in text:
                w(f"「{word}」は煽り・断定に見えやすい。本当に必要か確認")
        if BAIT_RE.search(text):
            e("「いいねして」等の反応を求める文言はエンゲージメントベイト扱いになる")
        if "#" in text or "＃" in text:
            e("本文にハッシュタグを書かない（トピックは topic_tag で1つだけ付ける）")

        # 価格：SKILL.md の現行価格にあるものだけ
        for raw in PRICE_RE.findall(text):
            if _price_digits(raw) not in prices_ok:
                e(f"価格「{raw}」が SKILL.md の現行価格にありません")

        # 空き：手入力の空き情報がある投稿だけ
        if AVAILABILITY_RE.search(text) and not (p.get("availability") or "").strip():
            e("空き状況に触れていますが availability（手入力の空き情報）がありません")
        if p.get("type") == "当日の空き" and not (p.get("availability") or "").strip():
            e("型「当日の空き」は availability が必須です")

        # 型・属性
        ptype = p.get("type")
        if ptype not in POST_TYPES:
            e(f"型「{ptype}」が不正です（{' / '.join(POST_TYPES)}）")
        if ptype and ptype == prev_type:
            e(f"型「{ptype}」が2日連続です")
        prev_type = ptype
        flags = detect_flags(text, p.get("flags") or [])
        p["flags"] = flags  # 機械判定で上書きして記録する
        if "CTA" in flags:
            cta_count += 1

        err = validate_topic_tag(p.get("topic_tag", ""))
        if err:
            e(err)
        elif not p.get("topic_tag"):
            e("topic_tag がありません（実験では毎回1つ付ける）")

        opener = _norm(text.splitlines()[0])[:12]
        if opener in openers:
            e(f"書き出しが [{openers[opener]}] と同じです")
        openers[opener] = n

        kind, idx = parse_media_spec(p.get("media", "text"))
        if kind not in ("text", "image", "video", "thumbnail", "carousel"):
            e(f"media「{p.get('media')}」が不正です")
        elif kind == "carousel":
            if len(idx) < 2:
                e("carousel は2枚以上を指定してください")
            elif src and src.get("children") and max(idx) >= src["children"]:
                e(f"carousel の番号が元投稿の枚数（{src['children']}枚）を超えています")
        elif kind == "video":
            w("video は Instagram 音源の権利が不明。自分で撮った音源の動画だけにする")

        dt = parse_dt(p.get("scheduled", ""))
        if not dt:
            e(f"scheduled「{p.get('scheduled')}」は YYYY/MM/DD HH:MM で書く")
        else:
            if dt.date() in seen_dates:
                e(f"{dt.date()} に2件あります（1日1投稿）")
            seen_dates.add(dt.date())
            if experiment_start:
                name, hm = slot_for((dt.date() - experiment_start).days)
                if dt.strftime("%H:%M") != hm or p.get("slot") != name:
                    w(f"時間枠がローテーション（{name} {hm}）と違います")
    if posts and cta_count > len(posts) / 2:
        warns.append(f"CTA 入りが {cta_count}/{len(posts)} 件。半分以下にする（宣伝色を抑える）")
    return errors, warns


def cmd_review(args) -> int:
    with open(args.file, encoding="utf-8") as f:
        week = json.load(f)
    pool = load_pool(args.pool)
    exp = date.fromisoformat(week["experiment_start"]) if week.get("experiment_start") else None
    errors, warns = review_entries(week.get("posts", []), pool, allowed_prices(), exp)
    for p in week.get("posts", []):
        print(f"- {p.get('scheduled')} {p.get('slot', '')} [{p.get('type')}] "
              f"{p.get('topic_tag', '')} {','.join(p.get('flags', []))} "
              f"{text_length(p.get('text', ''))}字")
    for m in warns:
        print(f"⚠ {m}")
    for m in errors:
        print(f"❌ {m}")
    print("✅ 問題なし" if not errors else f"❌ {len(errors)} 件を直してください")
    return 1 if errors else 0


# ── register ─────────────────────────────────────────

def cmd_register(args) -> int:
    import threads_store as store
    if cmd_review(args) != 0:
        print("review に ❌ があるため登録しません")
        return 1
    with open(args.file, encoding="utf-8") as f:
        week = json.load(f)
    pool = load_pool(args.pool)
    # review_entries で属性を機械判定し直したものを使う
    review_entries(week["posts"], pool, allowed_prices())
    tab = store.open_posts(create=True)
    existing = tab.rows()
    used = {r["元IG投稿ID"] for _, r in existing if r.get("ステータス") != store.ST_SKIPPED}
    taken_dates = {r["予定日時"][:10] for _, r in existing
                   if r.get("ステータス") != store.ST_SKIPPED and r.get("予定日時")}
    dup = [p["ig_id"] for p in week["posts"] if p["ig_id"] in used]
    clash = [p["scheduled"] for p in week["posts"] if p["scheduled"][:10] in taken_dates]
    if dup or clash:
        if dup:
            print(f"❌ 実験で使用済みの Instagram 投稿があります: {dup}")
        if clash:
            print(f"❌ その日はすでに登録があります: {clash}")
        return 1
    now = datetime.now(JST).strftime("%Y/%m/%d %H:%M")
    records = []
    for p in week["posts"]:
        src = pool[p["ig_id"]]
        records.append({
            "予定日時": p["scheduled"], "時間枠": p.get("slot", ""),
            "ステータス": store.ST_REVIEW, "型": p["type"], "属性": ",".join(p["flags"]),
            "topic_tag": p["topic_tag"], "本文": p["text"].strip(),
            "本文_生成時": p["text"].strip(), "メディア指定": p.get("media", "text"),
            "元IG投稿ID": p["ig_id"], "元IG投稿日": src.get("ig_date", ""),
            "元IG_URL": src.get("permalink", ""), "生成日時": now,
            "空き情報": p.get("availability", ""),
        })
    tab.append(records)
    print(f"✅ {len(records)} 件を {store.POSTS_TAB} タブに「{store.ST_REVIEW}」で登録しました。"
          f"シートで確認し、ステータスを「{store.ST_APPROVED}」にしてください")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Threads 投稿の準備")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("export", help="IG過去投稿から未使用の候補プールを作る（読み取りのみ）")
    p.add_argument("--out", default=POOL_FILE)
    p.add_argument("--limit", type=int, default=60)
    p.add_argument("--insights", action="store_true", help="候補ごとにIGインサイトも取る")
    p.add_argument("--no-sheet", action="store_true", help="使用済み判定にシートを読まない")

    p = sub.add_parser("slots", help="各日の時間枠を表示")
    p.add_argument("--start", required=True)
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--experiment-start", help="実験初日（ローテーションの基準。省略時は --start）")

    for name in ("review", "register"):
        p = sub.add_parser(name)
        p.add_argument("file")
        p.add_argument("--pool", default=POOL_FILE)

    args = parser.parse_args()
    if args.cmd == "export":
        cmd_export(args)
    elif args.cmd == "slots":
        cmd_slots(args)
    elif args.cmd == "review":
        sys.exit(cmd_review(args))
    elif args.cmd == "register":
        sys.exit(cmd_register(args))


if __name__ == "__main__":
    main()
