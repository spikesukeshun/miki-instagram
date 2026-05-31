"""
get_recent_insights.py
────────────────────────────────────────────────────
スケジュール組み立て前に実行する「直近10件インサイト取得」スクリプト。

取得内容:
  - 直近10件の投稿（いいね・コメント・保存・リーチ・再生数）
  - テーマ分類との照合（post_classifications.json）
  - 今どのテーマが伸びているか・いないかを判定

出力:
  recent_insights.json  ← Claude Codeがスケジュール組み立て時に参照する

実行:
  python3 get_recent_insights.py
"""

import json
import os
import requests
import time
from datetime import datetime, timezone, timedelta

from load_env import load_from_zshrc
load_from_zshrc()

TOKEN      = os.getenv("INSTAGRAM_ACCESS_TOKEN")
ACCOUNT_ID = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
API_BASE   = "https://graph.facebook.com/v19.0"

CLASSIFICATIONS_FILE = "post_classifications.json"
OUTPUT_FILE          = "recent_insights.json"

JST           = timezone(timedelta(hours=9))
THEME_LABELS  = {
    "bridal":    "ブライダル",
    "menu":      "メニュー・サービス",
    "reward":    "ご褒美エステ",
    "lifestyle": "ライフスタイル・自己語り",
}


def fetch_recent_posts(n: int = 10) -> list:
    """直近 n 件の投稿を取得"""
    url = f"{API_BASE}/{ACCOUNT_ID}/media"
    params = {
        "access_token": TOKEN,
        "limit": n,
        "fields": "id,caption,timestamp,like_count,comments_count,media_type,permalink"
    }
    res = requests.get(url, params=params)
    data = res.json()
    if "error" in data:
        print(f"  APIエラー: {data['error'].get('message')}")
        return []
    return data.get("data", [])[:n]


def fetch_insights(post_id: str, media_type: str) -> dict:
    metrics = "saved,reach,impressions,profile_visits"
    if media_type == "VIDEO":
        metrics += ",plays"
    res = requests.get(
        f"{API_BASE}/{post_id}/insights",
        params={"metric": metrics, "access_token": TOKEN}
    )
    data = res.json()
    result = {}
    for item in data.get("data", []):
        val = (item.get("values") or [{}])[0].get("value") if item.get("values") else item.get("value")
        result[item["name"]] = val or 0
    return result


def load_classifications() -> dict:
    if not os.path.exists(CLASSIFICATIONS_FILE):
        return {}
    with open(CLASSIFICATIONS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return {c["media_id"]: c["theme"] for c in data.get("classifications", [])}


def main():
    print("直近10件のインサイトを取得中...")

    posts = fetch_recent_posts(10)
    if not posts:
        print("投稿を取得できませんでした")
        return

    classifications = load_classifications()

    enriched = []
    for i, post in enumerate(posts, 1):
        mid   = post.get("id", "")
        mtype = post.get("media_type", "")
        insights = fetch_insights(mid, mtype)
        post.update(insights)

        ts  = datetime.strptime(post["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone(JST)
        cap = (post.get("caption") or "")[:60].replace("\n", " ")
        intro = next((l.strip() for l in (post.get("caption") or "").split("\n") if l.strip()), "")
        theme = classifications.get(mid, "未分類")
        theme_label = THEME_LABELS.get(theme, theme)
        type_label  = {"CAROUSEL_ALBUM": "カルーセル", "IMAGE": "単体画像", "VIDEO": "リール"}.get(mtype, mtype)

        entry = {
            "rank":         i,
            "media_id":     mid,
            "date":         ts.strftime("%Y-%m-%d"),
            "media_type":   type_label,
            "theme":        theme_label,
            "like_count":   post.get("like_count", 0),
            "comments":     post.get("comments_count", 0),
            "saved":        post.get("saved", 0),
            "reach":        post.get("reach", 0),
            "impressions":  post.get("impressions", 0),
            "plays":        post.get("plays", "") if mtype == "VIDEO" else "",
            "caption_head": cap,
            "intro":        intro,
            "permalink":    post.get("permalink", ""),
        }
        enriched.append(entry)

        print(f"  [{i}/10] {ts.strftime('%m/%d')} {type_label} {theme_label} "
              f"いいね{post.get('like_count',0)} 保存{insights.get('saved',0)} "
              f"リーチ{insights.get('reach',0)}")
        time.sleep(0.3)

    # サマリー計算
    avg_likes   = round(sum(e["like_count"] for e in enriched) / len(enriched), 1)
    avg_reach   = round(sum(e["reach"] for e in enriched) / len(enriched), 1)
    avg_saved   = round(sum(e["saved"] for e in enriched) / len(enriched), 1)

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
        "theme_summary": {
            t: {"count": v["count"], "avg_likes": round(v["likes"] / v["count"], 1)}
            for t, v in theme_summary.items()
        },
        "strategy_hints": hints,
        "posts": enriched,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 保存完了: {OUTPUT_FILE}")
    print(f"\n【直近10件サマリー】")
    print(f"  平均いいね: {avg_likes}件 / 平均リーチ: {avg_reach}人 / 平均保存: {avg_saved}件")
    print(f"\n【テーマ別】")
    for t, v in sorted(theme_summary.items(), key=lambda x: x[1]["likes"] / max(x[1]["count"], 1), reverse=True):
        avg = round(v["likes"] / v["count"], 1)
        print(f"  {t}: 平均いいね{avg}件（{v['count']}投稿）")
    if hints:
        print(f"\n【戦略ヒント】")
        for h in hints:
            print(f"  ・{h}")


if __name__ == "__main__":
    main()
