"""
get_recent_insights.py
────────────────────────────────────────────────────
スケジュール組み立て前に実行する「直近10件インサイト取得」スクリプト。

取得内容:
  - 直近10件の投稿（いいね・コメント・保存・リーチ・視聴数）
  - テーマ分類（post_classifications.json → 手動上書き → キャプション推定）
  - 今どのテーマが伸びているか・いないかを判定

出力:
  recent_insights.json  ← Claude Codeがスケジュール組み立て時に参照する

実行:
  python3 get_recent_insights.py

API仕様メモ（2026-08 実測）:
  - impressions は v22+ で廃止 → views を使う
  - VIDEO(リール) に plays は無い。profile_visits / follows も非対応
  - metric に1つでも非対応の名前を混ぜると **リクエスト全体が 400 になり
    全メトリクスが取れなくなる**（値が0になるのではなくデータ自体が返らない）
    → 失敗時はメトリクスを1件ずつ取り直すフォールバックを用意している
"""

import json
import os
import requests
import time
from datetime import datetime, timezone, timedelta

from load_env import load_from_zshrc
from theme_classifier import (
    THEME_LABELS, OVERRIDES_FILE,
    load_classifications, load_overrides, resolve_theme,
)
load_from_zshrc()

TOKEN      = os.getenv("INSTAGRAM_ACCESS_TOKEN")
ACCOUNT_ID = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
API_BASE   = "https://graph.facebook.com/v19.0"

OUTPUT_FILE          = "recent_insights.json"

# FEED（画像・カルーセル）とVIDEO（リール）で対応メトリクスが異なる
FEED_METRICS  = ["reach", "views", "saved", "shares", "likes", "comments",
                 "total_interactions", "profile_visits", "follows"]
VIDEO_METRICS = ["reach", "views", "saved", "shares", "likes", "comments",
                 "total_interactions"]

JST           = timezone(timedelta(hours=9))


def _parse_json(res):
    """JSONとして読めなければ None（5xx でHTMLが返るケースの保険）。"""
    try:
        return res.json()
    except ValueError:
        return None


def fetch_recent_posts(n: int = 10) -> list:
    """直近 n 件の投稿を取得"""
    url = f"{API_BASE}/{ACCOUNT_ID}/media"
    params = {
        "access_token": TOKEN,
        "limit": n,
        "fields": "id,caption,timestamp,like_count,comments_count,media_type,permalink"
    }
    res = requests.get(url, params=params)
    data = _parse_json(res)
    if data is None:
        print(f"  APIが不正な応答を返しました（HTTP {res.status_code}）")
        return []
    if "error" in data:
        print(f"  APIエラー: {data['error'].get('message')}")
        return []
    return data.get("data", [])[:n]


def _get_insights(post_id: str, metrics: list) -> dict:
    """指定メトリクスを1リクエストで取得。エラー時は {"_error": msg} を返す。"""
    res = requests.get(
        f"{API_BASE}/{post_id}/insights",
        params={"metric": ",".join(metrics), "access_token": TOKEN}
    )
    data = _parse_json(res)
    if data is None:
        return {"_error": f"不正な応答（HTTP {res.status_code}）"}
    if "error" in data:
        return {"_error": data["error"].get("message", "unknown error")}
    result = {}
    for item in data.get("data", []):
        vals = item.get("values") or [{}]
        val = vals[0].get("value")
        result[item["name"]] = val if isinstance(val, (int, float)) else 0
    return result


def fetch_insights(post_id: str, media_type: str) -> dict:
    """1投稿のインサイトを取得。

    メトリクス名を1つでも間違えるとリクエスト全体が失敗して全項目が
    取れなくなるため、失敗時は1件ずつ取り直して取れるものだけ拾う。
    （廃止メトリクスが混ざっても全滅させないための保険）
    """
    metrics = VIDEO_METRICS if media_type == "VIDEO" else FEED_METRICS
    result = _get_insights(post_id, metrics)
    if "_error" not in result:
        return result

    print(f"  ⚠ 一括取得に失敗: {result['_error']}")
    print(f"     → メトリクスを1件ずつ取り直します")
    merged = {}
    for m in metrics:
        one = _get_insights(post_id, [m])
        if "_error" in one:
            print(f"     ⚠ {m}: 取得不可（{one['_error'][:80]}）")
        else:
            merged.update(one)
        time.sleep(0.1)
    return merged


def main():
    print("直近10件のインサイトを取得中...")

    posts = fetch_recent_posts(10)
    if not posts:
        print("投稿を取得できませんでした")
        return

    classifications = load_classifications()
    overrides       = load_overrides()

    enriched = []
    for i, post in enumerate(posts, 1):
        mid   = post.get("id", "")
        mtype = post.get("media_type", "")
        insights = fetch_insights(mid, mtype)
        post.update(insights)

        ts  = datetime.strptime(post["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone(JST)
        caption = post.get("caption") or ""
        cap = caption[:60].replace("\n", " ")
        theme, theme_source = resolve_theme(mid, caption, classifications, overrides)
        theme_label = THEME_LABELS.get(theme, theme)
        type_label  = {"CAROUSEL_ALBUM": "カルーセル", "IMAGE": "単体画像", "VIDEO": "リール"}.get(mtype, mtype)

        entry = {
            "rank":         i,
            "media_id":     mid,
            "date":         ts.strftime("%Y-%m-%d"),
            "media_type":   type_label,
            "theme":        theme_label,
            "theme_source": theme_source,
            "like_count":   post.get("like_count", 0),
            "comments":     post.get("comments_count", 0),
            "saved":        post.get("saved", 0),
            "reach":        post.get("reach", 0),
            "views":        post.get("views", 0),
            "shares":       post.get("shares", 0),
            "total_interactions": post.get("total_interactions", 0),
            "profile_visits":     post.get("profile_visits", 0),
            "follows":            post.get("follows", 0),
            "caption_head": cap,
            "permalink":    post.get("permalink", ""),
        }
        enriched.append(entry)

        mark = {"override": "", "classified": "", "estimated": "*"}[theme_source]
        print(f"  [{i}/{len(posts)}] {ts.strftime('%m/%d')} {type_label} {theme_label}{mark} "
              f"いいね{post.get('like_count',0)} 保存{entry['saved']} "
              f"リーチ{entry['reach']} 視聴{entry['views']}")
        time.sleep(0.3)

    # サマリー計算
    avg_likes   = round(sum(e["like_count"] for e in enriched) / len(enriched), 1)
    avg_reach   = round(sum(e["reach"] for e in enriched) / len(enriched), 1)
    avg_saved   = round(sum(e["saved"] for e in enriched) / len(enriched), 1)
    avg_views   = round(sum(e["views"] for e in enriched) / len(enriched), 1)

    # インサイトが丸ごと取れていない場合に黙って0のまま進まないようにする
    # （メトリクス名の廃止でリクエストが400になると全件0になる）
    if avg_reach == 0:
        print("\n⚠ 全投稿でリーチが0です。メトリクス名が廃止された可能性があります。")
        print("  https://developers.facebook.com/docs/instagram-api/reference/ig-media/insights")
        print("  で対応メトリクスを確認し FEED_METRICS / VIDEO_METRICS を更新してください。")

    # テーマ別集計
    theme_summary = {}
    for e in enriched:
        t = e["theme"]
        theme_summary.setdefault(t, {"count": 0, "likes": 0, "reach": 0})
        theme_summary[t]["count"] += 1
        theme_summary[t]["likes"] += e["like_count"]
        theme_summary[t]["reach"] += e["reach"]

    # 戦略ヒント生成
    hints = []
    top_theme = max(theme_summary.items(), key=lambda x: x[1]["likes"] / max(x[1]["count"], 1), default=None)
    low_theme = min(theme_summary.items(), key=lambda x: x[1]["likes"] / max(x[1]["count"], 1), default=None)
    if top_theme:
        avg = round(top_theme[1]["likes"] / top_theme[1]["count"], 1)
        hints.append(f"直近で最も反応が良いテーマ: 【{top_theme[0]}】平均いいね{avg}件 → 次回もこのテーマを優先")
    if low_theme and low_theme[0] != top_theme[0]:
        avg = round(low_theme[1]["likes"] / low_theme[1]["count"], 1)
        hints.append(f"直近で最も反応が低いテーマ: 【{low_theme[0]}】平均いいね{avg}件 → 比率を下げるか別切り口を検討")
    if avg_likes < 15:
        hints.append("直近10件の平均いいね数が低め（15未満）→ 自己語り・プライベート投稿を追加することを検討")
    if avg_likes >= 25:
        hints.append("直近10件の平均いいね数が高い（25以上）→ 現在の投稿スタイルを維持")

    output = {
        "fetched_at":    datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "post_count":    len(enriched),
        "avg_likes":     avg_likes,
        "avg_reach":     avg_reach,
        "avg_saved":     avg_saved,
        "avg_views":     avg_views,
        "theme_summary": {
            t: {"count": v["count"],
                "avg_likes": round(v["likes"] / v["count"], 1),
                "avg_reach": round(v["reach"] / v["count"], 1)}
            for t, v in theme_summary.items()
        },
        "strategy_hints": hints,
        "posts": enriched,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 保存完了: {OUTPUT_FILE}")
    print(f"\n【直近{len(enriched)}件サマリー】")
    print(f"  平均いいね: {avg_likes}件 / 平均リーチ: {avg_reach}人 / "
          f"平均保存: {avg_saved}件 / 平均視聴: {avg_views}回")
    print(f"\n【テーマ別】")
    for t, v in sorted(theme_summary.items(), key=lambda x: x[1]["likes"] / max(x[1]["count"], 1), reverse=True):
        avg = round(v["likes"] / v["count"], 1)
        avg_r = round(v["reach"] / v["count"], 1)
        print(f"  {t}: 平均いいね{avg}件 / 平均リーチ{avg_r}人（{v['count']}投稿）")

    n_est = sum(1 for e in enriched if e["theme_source"] == "estimated")
    if n_est:
        print(f"\n  ＊印の{n_est}件はキャプションからの推定テーマです。")
        print(f"    誤りがあれば {OVERRIDES_FILE} に \"media_id\": \"theme\" を書けば上書きされます。")
        print(f"    （theme は bridal / menu / reward / lifestyle）")
    if hints:
        print(f"\n【戦略ヒント】")
        for h in hints:
            print(f"  ・{h}")


if __name__ == "__main__":
    main()
