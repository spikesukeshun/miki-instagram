"""
insight_report.py  ── API + オフラインフォールバック版
─────────────────────────────────────────────────────────────
【優先】Instagram Graph API で全投稿のいいね/コメント/タイプと
        保存数・リーチ・視聴数を取得（全件。以前は上位50件のみだった）
【フォールバック】APIが使えない場合は posts_cache.json + report.txt でオフライン分析

分析軸:
  1. テーマ別パフォーマンス (bridal/menu/reward/lifestyle)
  2. コンテンツタイプ別 (CAROUSEL_ALBUM/IMAGE/VIDEO=リール)
  3. 投稿時間帯・曜日別
  4. キャプションスタイル別
  5. 戦略的提言

実行:
  python3 insight_report.py

API仕様メモ（2026-08 実測 / get_recent_insights.py と共通）:
  - impressions は v22+ で廃止 → views を使う
  - VIDEO(リール) に plays は無い。profile_visits / follows も非対応
  - metric に1つでも非対応の名前を混ぜると **リクエスト全体が 400 になり
    全メトリクスが取れなくなる**（値が0になるのではなくデータ自体が返らない）
    → 失敗時はメトリクスを1件ずつ取り直すフォールバックを用意している
"""

import json
import os
import re
import requests
import time
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter

from load_env import load_from_zshrc
from theme_classifier import (
    THEME_LABELS, load_classifications, load_overrides, resolve_theme,
)
load_from_zshrc()

TOKEN      = os.getenv("INSTAGRAM_ACCESS_TOKEN")
ACCOUNT_ID = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
API_BASE   = "https://graph.facebook.com/v19.0"

CACHE_FILE           = "posts_cache.json"
REPORT_SRC           = "report_20260404.txt"
OUTPUT_FILE          = f"insight_report_{datetime.now().strftime('%Y%m%d')}.md"

JST           = timezone(timedelta(hours=9))
WEEKDAY_NAMES = ["月", "火", "水", "木", "金", "土", "日"]

# FEED（画像・カルーセル）とVIDEO（リール）で対応メトリクスが異なる
FEED_METRICS  = ["reach", "views", "saved", "shares", "likes", "comments",
                 "total_interactions", "profile_visits", "follows"]
VIDEO_METRICS = ["reach", "views", "saved", "shares", "likes", "comments",
                 "total_interactions"]


# ────────────────────────────────────────
# API取得
# ────────────────────────────────────────
def _parse_json(res):
    """JSONとして読めなければ None。

    502/503 のときエッジがHTMLを返すことがあり、res.json() が例外を投げる。
    全件取得は400回以上の連続リクエストになるため、1回の不正応答で
    処理全体が落ちないようにする。
    """
    try:
        return res.json()
    except ValueError:
        return None



def fetch_all_posts_api() -> list:
    """Instagram Graph API から全投稿を取得（like_count付き）"""
    print("  Instagram APIから全投稿を取得中...")
    posts = []
    url = f"{API_BASE}/{ACCOUNT_ID}/media"
    params = {
        "access_token": TOKEN,
        "limit": 100,
        "fields": "id,caption,timestamp,like_count,comments_count,media_type,permalink"
    }
    while url:
        res = requests.get(url, params=params)
        data = _parse_json(res)
        if data is None:
            print(f"  APIが不正な応答を返しました（HTTP {res.status_code}）")
            return []
        if "error" in data:
            print(f"  APIエラー: {data['error'].get('message')}")
            return []
        posts.extend(data.get("data", []))
        url = data.get("paging", {}).get("next")
        params = {}
        print(f"  取得済み: {len(posts)}件", end="\r")
    print(f"\n  取得完了: {len(posts)}件")
    return posts


# レート制限系のエラーコード。これらだけは待って再試行する価値がある
THROTTLE_CODES = {4, 17, 32, 613}


def _get_insights(post_id: str, metrics: list, attempts: int = 3) -> dict:
    """指定メトリクスを1リクエストで取得。エラー時は {"_error": msg} を返す。

    レート制限（code 4/17/32/613）・5xx・JSONとして読めない応答のときだけ
    バックオフして再試行する。
    メトリクス名の不正（code 100）は再試行しても直らないので即座に返す。
    """
    msg = "unknown error"
    for n in range(attempts):
        res = requests.get(
            f"{API_BASE}/{post_id}/insights",
            params={"metric": ",".join(metrics), "access_token": TOKEN}
        )
        data = _parse_json(res)
        if data is None:
            # 5xx でHTMLが返るケース。一時エラーとみなして再試行する
            msg = f"不正な応答（HTTP {res.status_code}）"
            if n < attempts - 1:
                time.sleep(1.5 * (n + 1))
            continue
        if "error" not in data:
            result = {}
            for item in data.get("data", []):
                vals = item.get("values") or [{}]
                val = vals[0].get("value")
                result[item["name"]] = val if isinstance(val, (int, float)) else 0
            return result

        err = data["error"]
        msg = err.get("message", "unknown error")
        transient = err.get("code") in THROTTLE_CODES or res.status_code >= 500
        if not transient:
            break
        if n < attempts - 1:
            time.sleep(1.5 * (n + 1))
    return {"_error": msg}


def fetch_insights_api(post_id: str, media_type: str) -> dict:
    """1投稿のインサイトを取得。

    メトリクス名を1つでも間違えるとリクエスト全体が失敗して全項目が
    取れなくなるため、失敗時は1件ずつ取り直して取れるものだけ拾う。
    （廃止メトリクスが混ざっても全滅させないための保険）

    ただしプロアカウント移行前（〜2022年前半）の投稿はインサイトが
    そもそも存在せず、どのメトリクスを指定しても "Invalid parameter" になる。
    先に reach 1件だけ試して、それも失敗するなら残りは叩かない。
    """
    metrics = VIDEO_METRICS if media_type == "VIDEO" else FEED_METRICS
    result = _get_insights(post_id, metrics)
    if "_error" not in result:
        return result

    print(f"\n  ⚠ 一括取得に失敗: {result['_error']}")

    # reach は FEED / VIDEO 双方で最も安定して存在するメトリクス。
    # これが単独でも取れないなら投稿自体がインサイト非対応と判断する。
    probe = _get_insights(post_id, [metrics[0]])
    if "_error" in probe:
        print(f"     → {post_id} はインサイト非対応の投稿です"
              f"（移行前の可能性）。0として集計されます")
        return {}

    print(f"     → メトリクスを1件ずつ取り直します")
    merged = dict(probe)
    for m in metrics[1:]:
        one = _get_insights(post_id, [m])
        if "_error" in one:
            print(f"     ⚠ {m}: 取得不可（{one['_error'][:80]}）")
        else:
            merged.update(one)
        time.sleep(0.1)
    return merged


def enrich_posts(posts: list, limit=None) -> list:
    """全投稿のインサイトを取得してマージ。

    以前は「いいね上位50件」だけを取得していたが、集計側は全投稿を分母に
    使っていたため、保存・リーチ・視聴の平均が実態の 1/3〜1/22 に化けていた。
    分母を揃えるため全件取得する（limit は動作確認用）。

    プロアカウント移行前（〜2022年前半）の投稿はインサイトが存在しないので、
    取得できたかどうかを _has_insights に立てて集計側で分母から外す。
    """
    targets = posts[:limit] if limit else posts
    total   = len(targets)
    print(f"  全{total}件のインサイトを取得中（保存/リーチ/視聴数）...")
    ok = 0
    for i, post in enumerate(targets, 1):
        insights = fetch_insights_api(post["id"], post.get("media_type", ""))
        post.update(insights)
        post["_has_insights"] = bool(insights)
        ok += bool(insights)
        print(f"  {i}/{total}件完了（取得成功 {ok}件）", end="\r")
        time.sleep(0.3)
    print(f"\n  インサイト取得完了: {ok}/{total}件")
    if total - ok:
        print(f"  （{total - ok}件はインサイト非対応。平均値の分母から除外します）")
    return posts


# ────────────────────────────────────────
# オフラインデータロード
# ────────────────────────────────────────
def load_posts_cache() -> list:
    """posts_cache.json から投稿一覧を読み込む（like_countなし）"""
    if not os.path.exists(CACHE_FILE):
        return []
    with open(CACHE_FILE, encoding="utf-8") as f:
        data = json.load(f)
    # cache の media_id を id に統一
    posts = []
    for p in data.get("posts", []):
        p["id"] = p.get("media_id", "")
        posts.append(p)
    return posts


def parse_existing_report() -> dict:
    """report_20260404.txt から既知パフォーマンスデータを抽出"""
    if not os.path.exists(REPORT_SRC):
        return {}
    with open(REPORT_SRC, encoding="utf-8") as f:
        text = f.read()
    result = {}
    for m in re.finditer(r"いいね (\d+)件 \| (\d{4}-\d{2}-\d{2})\n.*?\n\s*(https://[^\n]+)", text):
        url = m.group(3).strip()
        result.setdefault(url, {})["likes"] = int(m.group(1))
        result[url]["date"] = m.group(2)
    for m in re.finditer(r"保存 (\d+)件 \| リーチ (\d+)人 \| (\d{4}-\d{2}-\d{2})\n.*?\n\s*(https://[^\n]+)", text):
        url = m.group(4).strip()
        result.setdefault(url, {})["saved"] = int(m.group(1))
        result[url]["reach"] = int(m.group(2))
        result[url].setdefault("date", m.group(3))
    for m in re.finditer(r"リーチ (\d+)人 \| いいね (\d+)件 \| (\d{4}-\d{2}-\d{2})\n.*?\n\s*(https://[^\n]+)", text):
        url = m.group(4).strip()
        result.setdefault(url, {})["reach"] = int(m.group(1))
        result[url].setdefault("likes", int(m.group(2)))
        result[url].setdefault("date", m.group(3))
    return result


# ────────────────────────────────────────
# ユーティリティ
# ────────────────────────────────────────
def to_jst(ts_str: str) -> datetime:
    dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S%z")
    return dt.astimezone(JST)


def safe_avg(total, count):
    return round(total / count, 1) if count > 0 else 0


def caption_style(caption: str) -> str:
    """キャプション冒頭80文字でスタイルを分類"""
    if not caption:
        return "不明"
    head = caption[:80].replace("\n", " ")
    if "閲覧ありがとう" in head or "⭐️" in head[:10]:
        return "テンプレ告知系"
    if "自分語り" in head:
        return "自己語り系（明示）"
    if any(kw in head for kw in ["ブライダルエステ", "花嫁", "プレ花嫁", "結婚式", "前撮り"]):
        return "ブライダル訴求系"
    if any(kw in head for kw in ["30代", "40代", "アラサー", "アラフォー", "ターンオーバー", "コラーゲン"]):
        return "美容情報系"
    if any(kw in head for kw in ["ご褒美", "GW", "旅行", "プライベート", "ホテル"]):
        return "ご褒美・プライベート系"
    # 「mikiです。」が冒頭に来る投稿（自己語り型キャプション）
    head_lower = head.lower()
    if head_lower.startswith("miki") or "mikiです" in head[:20].lower():
        return "自己語り系"
    return "その他"


# ────────────────────────────────────────
# 分析
# ────────────────────────────────────────
def _new_stats(with_posts=False) -> dict:
    """count はいいね・コメント用の分母、insight_count は保存・リーチ・視聴用の分母。

    インサイトはプロアカウント移行前の投稿では取得できないため、
    2つの分母を分けないと取得できなかった投稿が 0 として平均を押し下げる。
    """
    s = {"likes": 0, "comments": 0, "saved": 0, "reach": 0, "views": 0,
         "count": 0, "insight_count": 0}
    if with_posts:
        s["posts"] = []
        s["types"] = defaultdict(int)
    return s


def analyze(posts: list, classifications: dict, overrides: dict = None) -> dict:
    overrides     = overrides or {}
    theme_stats   = defaultdict(lambda: _new_stats(with_posts=True))
    type_stats    = defaultdict(_new_stats)
    hour_stats    = defaultdict(lambda: {"likes": 0, "count": 0})
    weekday_stats = defaultdict(lambda: {"likes": 0, "count": 0})
    style_stats   = defaultdict(lambda: {"likes": 0, "count": 0})
    theme_sources = Counter()

    for post in posts:
        mid      = post.get("id", "")
        mtype    = post.get("media_type", "不明")
        likes    = post.get("like_count", 0) or 0
        comments = post.get("comments_count", 0) or 0
        saved    = post.get("saved", 0) or 0
        reach    = post.get("reach", 0) or 0
        views    = post.get("views", 0) or 0
        ts       = post.get("timestamp", "")
        caption  = post.get("caption", "") or ""
        # 棚卸し（post_classifications.json）は 2026-04-06 で止まっているため、
        # 未登録の投稿はキャプションから推定する（＝全部「未分類」になるのを防ぐ）
        theme, source = resolve_theme(mid, caption, classifications, overrides)
        theme_sources[source] += 1
        # インサイトを取得できた投稿だけを保存・リーチ・視聴の分母に数える
        measured = 1 if post.get("_has_insights") else 0

        s = theme_stats[theme]
        s["likes"] += likes; s["comments"] += comments
        s["saved"] += saved; s["reach"] += reach; s["views"] += views
        s["count"] += 1; s["insight_count"] += measured
        s["posts"].append(post)
        s["types"][mtype] += 1

        t = type_stats[mtype]
        t["likes"] += likes; t["comments"] += comments
        t["saved"] += saved; t["reach"] += reach; t["views"] += views
        t["count"] += 1; t["insight_count"] += measured

        if ts:
            dt = to_jst(ts)
            hour_stats[dt.hour]["likes"] += likes
            hour_stats[dt.hour]["count"] += 1
            weekday_stats[dt.weekday()]["likes"] += likes
            weekday_stats[dt.weekday()]["count"] += 1

        style = caption_style(caption)
        style_stats[style]["likes"] += likes
        style_stats[style]["count"] += 1

    return {
        "theme": theme_stats, "type": type_stats,
        "hour": hour_stats, "weekday": weekday_stats, "style": style_stats,
        "theme_sources": theme_sources,
    }


# ────────────────────────────────────────
# レポート生成
# ────────────────────────────────────────
def build_report(posts, stats, known_perf, total, has_live_data: bool) -> str:
    lines = []
    wn = WEEKDAY_NAMES

    def h2(t):   lines.append(f"\n## {t}\n")
    def h3(t):   lines.append(f"\n### {t}\n")
    def row(*c): lines.append("| " + " | ".join(str(x) for x in c) + " |")
    def sep(n):  lines.append("| " + " | ".join(["---"] * n) + " |")

    now = datetime.now(JST).strftime("%Y/%m/%d")
    lines.append(f"# Instagram インサイト分析レポート　{now}")
    data_note = "Instagram Graph API（ライブデータ）" if has_live_data else "posts_cache.json（キャッシュ）+ report_20260404.txt"
    lines.append(f"\n総投稿数: **{total}件** | データソース: {data_note}\n")
    if has_live_data:
        measured = sum(1 for p in posts if p.get("_has_insights"))
        lines.append(f"> ※ いいね・コメントは全{total}件が母数。"
                     f"保存・リーチ・視聴はインサイトを取得できた{measured}件が母数\n")
        lines.append("> （プロアカウント移行前の投稿はインサイトが存在しないため分母から除外）\n")
    else:
        lines.append("> ※ いいね数なし（オフライン）。保存/リーチは既存レポートTOP5のみ参照\n")

    # ── 1. テーマ別 ──────────────────────
    h2("1. テーマ別パフォーマンス")
    if has_live_data:
        row("テーマ", "投稿数", "計測済", "平均いいね", "平均コメント", "平均保存", "平均リーチ")
        sep(7)
    else:
        row("テーマ", "投稿数", "割合", "カルーセル", "画像", "動画")
        sep(6)

    theme_order = sorted(stats["theme"].items(),
                         key=lambda x: safe_avg(x[1]["likes"], x[1]["count"]) if has_live_data else x[1]["count"],
                         reverse=True)
    for theme, s in theme_order:
        label = THEME_LABELS.get(theme, theme)
        cnt = s["count"]
        icnt = s.get("insight_count", 0)
        if has_live_data:
            row(label, cnt, icnt, safe_avg(s["likes"], cnt), safe_avg(s["comments"], cnt),
                safe_avg(s["saved"], icnt), safe_avg(s["reach"], icnt))
        else:
            pct = round(cnt / total * 100, 1)
            tc = s["types"]
            row(label, cnt, f"{pct}%", tc.get("CAROUSEL_ALBUM", 0), tc.get("IMAGE", 0), tc.get("VIDEO", 0))

    if has_live_data:
        h3("テーマ別 TOP3投稿（いいね順）")
        for theme, s in theme_order:
            label = THEME_LABELS.get(theme, theme)
            lines.append(f"\n**{label}**\n")
            top3 = sorted(s["posts"], key=lambda x: x.get("like_count", 0), reverse=True)[:3]
            for i, p in enumerate(top3, 1):
                ts = to_jst(p["timestamp"]).strftime("%Y-%m-%d") if p.get("timestamp") else "不明"
                cap = (p.get("caption") or "")[:50].replace("\n", " ")
                extra = ""
                if p.get("saved"): extra += f" | 保存{p['saved']}件"
                if p.get("reach"): extra += f" | リーチ{p['reach']}人"
                if p.get("views"): extra += f" | 視聴{p['views']}回"
                lines.append(f"{i}. いいね{p.get('like_count',0)}件{extra} | {ts}")
                lines.append(f"   {cap}...")
                lines.append(f"   {p.get('permalink', '')}")
            lines.append("")

    # ── 2. コンテンツタイプ別 ────────────
    h2("2. コンテンツタイプ別パフォーマンス")
    if has_live_data:
        row("タイプ", "投稿数", "計測済", "平均いいね", "平均コメント", "平均保存", "平均リーチ", "平均視聴")
        sep(8)
    else:
        row("タイプ", "投稿数", "割合")
        sep(3)

    type_order = sorted(stats["type"].items(),
                        key=lambda x: safe_avg(x[1]["likes"], x[1]["count"]) if has_live_data else x[1]["count"],
                        reverse=True)
    for mtype, s in type_order:
        label = {"CAROUSEL_ALBUM": "カルーセル", "IMAGE": "単体画像", "VIDEO": "リール動画"}.get(mtype, mtype)
        cnt = s["count"]
        icnt = s.get("insight_count", 0)
        if has_live_data:
            # views は v22+ でリール専用ではなくフィード投稿でも取れる
            row(label, cnt, icnt, safe_avg(s["likes"], cnt), safe_avg(s["comments"], cnt),
                safe_avg(s["saved"], icnt), safe_avg(s["reach"], icnt),
                safe_avg(s["views"], icnt))
        else:
            pct = round(cnt / total * 100, 1)
            row(label, cnt, f"{pct}%")

    lines.append("\n> **ストーリーズについて**: ストーリーズは24時間で消えるため、過去の数値データはAPIから取得できません。\n> 現在アクティブなストーリーズのみ `/{media_id}/insights` で取得可能です。\n")

    # ── 3. 時間帯別 ──────────────────────
    h2("3. 投稿時間帯別（JST）")
    has_likes = has_live_data
    if has_likes:
        row("時間帯", "投稿数", "平均いいね")
        sep(3)
        hour_avg = {h: safe_avg(s["likes"], s["count"]) for h, s in stats["hour"].items() if s["count"] >= 3}
        for h, avg in sorted(hour_avg.items(), key=lambda x: x[1], reverse=True)[:8]:
            row(f"{h:02d}時台", stats["hour"][h]["count"], avg)
    else:
        row("時間帯", "投稿数")
        sep(2)
        for h, s in sorted(stats["hour"].items(), key=lambda x: x[1]["count"], reverse=True)[:10]:
            row(f"{h:02d}時台", s["count"])

    # ── 4. 曜日別 ────────────────────────
    h2("4. 曜日別")
    if has_likes:
        row("曜日", "投稿数", "平均いいね")
        sep(3)
        weekday_sorted = sorted(stats["weekday"].items(),
                                key=lambda x: safe_avg(x[1]["likes"], x[1]["count"]), reverse=True)
        for w, s in weekday_sorted:
            row(f"{wn[w]}曜日", s["count"], safe_avg(s["likes"], s["count"]))
    else:
        row("曜日", "投稿数")
        sep(2)
        for w, s in sorted(stats["weekday"].items(), key=lambda x: x[1]["count"], reverse=True):
            row(f"{wn[w]}曜日", s["count"])

    # ── 5. キャプションスタイル別 ──────────
    h2("5. キャプションスタイル別")
    if has_likes:
        row("スタイル", "投稿数", "平均いいね")
        sep(3)
        style_order = sorted(stats["style"].items(),
                             key=lambda x: safe_avg(x[1]["likes"], x[1]["count"]), reverse=True)
    else:
        row("スタイル", "投稿数")
        sep(2)
        style_order = sorted(stats["style"].items(), key=lambda x: x[1]["count"], reverse=True)
    for style, s in style_order:
        if has_likes:
            row(style, s["count"], safe_avg(s["likes"], s["count"]))
        else:
            row(style, s["count"])

    # ── 6. 既存レポートTOP投稿まとめ ────────
    h2("6. 高パフォーマンス投稿まとめ（report_20260404.txt より）")
    if not has_live_data and known_perf:
        h3("いいね TOP5")
        row("順位", "いいね", "保存", "リーチ", "日付", "URL")
        sep(6)
        for i, (url, d) in enumerate(
            sorted(known_perf.items(), key=lambda x: x[1].get("likes", 0), reverse=True)[:5], 1
        ):
            row(i, d.get("likes","-"), d.get("saved","-"), d.get("reach","-"), d.get("date","-"), url)

    lines.append("""
**高パフォーマンス投稿の共通点**

| 指標 | 最高値 | 投稿タイプ | 特徴 |
|---|---|---|---|
| いいね | **451件** | 2023-02-01 | 自己語り（美容学校〜現在のストーリー） |
| いいね2位 | **378件** | 2022-08-05 | プライベート（結婚式エピソード） |
| リーチ | **937人** | 2024-06-18 | プライベート（久々の近況） |
| 保存 | **14件** | 2023-02-01 | 自己語り（キャリアストーリー） |
| 保存3位 | **4件** | 2022-04-19 | 美容情報（ヒト幹細胞成分の具体解説） |
""")

    # ── 7. 戦略的提言 ────────────────────
    h2("7. 戦略的提言")

    if has_live_data:
        theme_best = theme_order[0]
        theme_worst = theme_order[-1]
        best_label = THEME_LABELS.get(theme_best[0], theme_best[0])
        worst_label = THEME_LABELS.get(theme_worst[0], theme_worst[0])
        best_avg = safe_avg(theme_best[1]["likes"], theme_best[1]["count"])
        worst_avg = safe_avg(theme_worst[1]["likes"], theme_worst[1]["count"])

        type_best = type_order[0]
        best_type_label = {"CAROUSEL_ALBUM": "カルーセル", "IMAGE": "単体画像", "VIDEO": "リール動画"}.get(type_best[0], type_best[0])

        hour_avg = {h: safe_avg(s["likes"], s["count"]) for h, s in stats["hour"].items() if s["count"] >= 3}
        best_hours = sorted(hour_avg.items(), key=lambda x: x[1], reverse=True)[:3]
        weekday_sorted = sorted(stats["weekday"].items(),
                                key=lambda x: safe_avg(x[1]["likes"], x[1]["count"]), reverse=True)

        lines.append(f"""
### コンテンツ戦略

**テーマ推奨**
- 最高エンゲージメント: **{best_label}**（平均いいね {best_avg}件）→ 次回優先
- 最低エンゲージメント: **{worst_label}**（平均いいね {worst_avg}件）→ 単独投稿より他テーマに組み込む

**フォーマット推奨**
- 最高パフォーマンス: **{best_type_label}**（平均いいね {safe_avg(type_best[1]['likes'], type_best[1]['count'])}件）

### 投稿タイミング

- **推奨時間帯**: {' / '.join([f'{h:02d}時台（平均{a}いいね）' for h, a in best_hours])}
- **推奨曜日**: {' / '.join([f'{wn[w]}曜日' for w, _ in weekday_sorted[:2]])}
""")

    lines.append("""
### 共通の投稿改善ポイント

**1. 自己語り投稿を月1〜2回必ず入れる**
- いいね・保存・リーチ全指標のトップが「自己語り型」
- MIKIのキャリア・想い・体験談は数字で見ても圧倒的に反応が高い

**2. テンプレ告知（⭐️閲覧ありがとう）の比率を下げる**
- コース紹介を冒頭に持ってくる投稿は反応が下がる傾向
- コース情報はキャプション末尾に移し、冒頭は共感フレーズから

**3. プライベート投稿でリーチを拡大**
- リーチ937人はシンプルな近況報告投稿
- 月1回「MIKIの素の日常」を見せる投稿でフォロワー外にリーチ

**4. 保存率を上げる情報設計**
- 美容成分・ケアスケジュール・逆算プランなど「後で使える情報」でカルーセルを作る

**5. リールは積極的に活用する価値あり**
- 現在の投稿数は少ないが、リール特有の再生数・リーチ拡大効果が期待できる
- 月1本、30〜60秒のショートリールを追加することを推奨

### 次回投稿チェックリスト

- [ ] キャプション1〜2行目にテーマキーワードが自然に入っているか
- [ ] 冒頭がテンプレ告知になっていないか（「⭐️閲覧ありがとう」禁止）
- [ ] MIKIの体験・感情が伝わる書き出しになっているか
- [ ] カルーセルに「保存したくなる情報」があるか
- [ ] CTA（DM/指名割引）が末尾に明確にあるか
- [ ] 今月の自己語り投稿は済んでいるか（月1〜2回ペース）
""")

    lines.append(f"\n---\n\n*生成: {datetime.now(JST).strftime('%Y/%m/%d %H:%M')} JST*")
    return "\n".join(lines)


# ────────────────────────────────────────
# メイン
# ────────────────────────────────────────
def main():
    print("=" * 55)
    print("Instagram インサイト分析レポート生成")
    print("=" * 55)

    # API取得を試みる
    has_live_data = False
    posts = []

    if TOKEN and ACCOUNT_ID:
        print(f"  TOKEN: 設定あり（{len(TOKEN)}文字）")
        posts = fetch_all_posts_api()
        if posts:
            posts = enrich_posts(posts)
            has_live_data = True

            # インサイトが丸ごと取れていない場合に黙って0のまま進まないようにする
            # （メトリクス名の廃止でリクエストが400になると全件0になる）
            if not any(p.get("reach", 0) for p in posts):
                print("\n⚠ 全投稿でリーチが0です。メトリクス名が廃止された可能性があります。")
                print("  https://developers.facebook.com/docs/instagram-api/reference/ig-media/insights")
                print("  で対応メトリクスを確認し FEED_METRICS / VIDEO_METRICS を更新してください。")
    else:
        print("  TOKEN/ACCOUNT_ID が未設定のためオフラインモードで実行")

    # フォールバック: キャッシュデータ
    if not posts:
        print("  → posts_cache.json からオフラインデータを読み込みます")
        posts = load_posts_cache()

    total = len(posts)
    print(f"  投稿数: {total}件（{'ライブAPI' if has_live_data else 'キャッシュ'}）")

    classifications = load_classifications()
    overrides       = load_overrides()
    matched = sum(1 for p in posts if p.get("id") in classifications)
    print(f"  テーマ分類マッチ: {matched}/{total}件"
          f"（残りはキャプションから推定）")

    known_perf = parse_existing_report()
    print(f"  既存レポート参照: {len(known_perf)}投稿")

    print("\n分析中...")
    stats = analyze(posts, classifications, overrides)
    src = stats["theme_sources"]
    print(f"  テーマ内訳: 棚卸し済み {src['classified']}件 / "
          f"手動上書き {src['override']}件 / キャプション推定 {src['estimated']}件")

    report = build_report(posts, stats, known_perf, total, has_live_data)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n✅ レポート生成: {OUTPUT_FILE}")

    print("\n" + "=" * 55)
    print(f"【テーマ別 {'平均いいね' if has_live_data else '投稿数'}】")
    theme_order = sorted(stats["theme"].items(),
                         key=lambda x: safe_avg(x[1]["likes"], x[1]["count"]) if has_live_data else x[1]["count"],
                         reverse=True)
    for theme, s in theme_order:
        label = THEME_LABELS.get(theme, theme)
        if has_live_data:
            icnt = s.get("insight_count", 0)
            print(f"  {label}: 平均いいね {safe_avg(s['likes'], s['count'])}件 "
                  f"/ 平均リーチ {safe_avg(s['reach'], icnt)}人 "
                  f"({s['count']}投稿・うち計測済{icnt})")
        else:
            print(f"  {label}: {s['count']}件 ({round(s['count']/total*100,1)}%)")

    print("\n【コンテンツタイプ別投稿数】")
    for mtype, s in sorted(stats["type"].items(), key=lambda x: x[1]["count"], reverse=True):
        label = {"CAROUSEL_ALBUM": "カルーセル", "IMAGE": "単体画像", "VIDEO": "リール動画"}.get(mtype, mtype)
        if has_live_data:
            icnt = s.get("insight_count", 0)
            extra = f" | 平均いいね {safe_avg(s['likes'], s['count'])}件"
            if s.get("views", 0):
                extra += f" | 平均視聴 {safe_avg(s['views'], icnt)}回"
        else:
            extra = ""
        print(f"  {label}: {s['count']}件{extra}")


if __name__ == "__main__":
    main()
