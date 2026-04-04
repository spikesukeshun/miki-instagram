import requests
import os
import time
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN")
ACCOUNT_ID = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
API_BASE = "https://graph.instagram.com/v19.0"


# ───────────────────────────────
# 自分の投稿を全件取得
# ───────────────────────────────
def fetch_all_my_posts():
    print("自分の投稿を取得中...")
    posts = []
    url = f"{API_BASE}/{ACCOUNT_ID}/media"
    params = {
        "access_token": TOKEN,
        "limit": 100,
        "fields": "id,caption,timestamp,like_count,comments_count,media_type,permalink"
    }

    while url:
        res = requests.get(url, params=params)
        data = res.json()
        posts.extend(data.get("data", []))
        url = data.get("paging", {}).get("next")
        params = {}
        print(f"  取得済み: {len(posts)}件", end="\r")

    print(f"  取得完了: {len(posts)}件")
    return posts


# ───────────────────────────────
# 投稿ごとの保存数・リーチ数を取得
# ───────────────────────────────
def fetch_post_insights(post_id: str) -> dict:
    res = requests.get(
        f"{API_BASE}/{post_id}/insights",
        params={
            "metric": "saved,reach,impressions,profile_visits",
            "access_token": TOKEN
        }
    )
    data = res.json()
    result = {}
    for item in data.get("data", []):
        result[item["name"]] = item["values"][0]["value"] if item.get("values") else item.get("value", 0)
    return result


# ───────────────────────────────
# 上位投稿のインサイトを取得
# ───────────────────────────────
def enrich_with_insights(posts, top_n=20):
    print(f"\n上位{top_n}件のインサイト（保存数・リーチ数）を取得中...")
    for i, post in enumerate(posts[:top_n], 1):
        insights = fetch_post_insights(post["id"])
        post["saved"] = insights.get("saved", 0)
        post["reach"] = insights.get("reach", 0)
        post["impressions"] = insights.get("impressions", 0)
        post["profile_visits"] = insights.get("profile_visits", 0)
        print(f"  {i}/{top_n}件完了", end="\r")
        time.sleep(0.3)  # API制限対策
    print(f"  インサイト取得完了！")
    return posts


# ───────────────────────────────
# 投稿を分析してレポート表示
# ───────────────────────────────
def analyze_my_posts(posts):
    print("\n📊 自分の投稿分析")
    print("=" * 50)

    if not posts:
        print("投稿が見つかりませんでした")
        return []

    sorted_by_likes   = sorted(posts, key=lambda x: x.get("like_count", 0), reverse=True)
    sorted_by_saved   = sorted(posts[:20], key=lambda x: x.get("saved", 0), reverse=True)
    sorted_by_reach   = sorted(posts[:20], key=lambda x: x.get("reach", 0), reverse=True)
    sorted_by_comments = sorted(posts, key=lambda x: x.get("comments_count", 0), reverse=True)

    print(f"\n総投稿数: {len(posts)}件")

    print("\n🏆 いいねが多かった投稿 TOP5:")
    for i, post in enumerate(sorted_by_likes[:5], 1):
        caption = (post.get("caption") or "")[:40].replace("\n", " ")
        print(f"  {i}. いいね {post.get('like_count', 0)}件 | {post.get('timestamp', '')[:10]}")
        print(f"     {caption}...")
        print(f"     {post.get('permalink', '')}")

    print("\n🔖 保存数が多かった投稿 TOP5:")
    for i, post in enumerate(sorted_by_saved[:5], 1):
        caption = (post.get("caption") or "")[:40].replace("\n", " ")
        print(f"  {i}. 保存 {post.get('saved', 0)}件 | リーチ {post.get('reach', 0)}人 | {post.get('timestamp', '')[:10]}")
        print(f"     {caption}...")
        print(f"     {post.get('permalink', '')}")

    print("\n👥 リーチ数が多かった投稿 TOP5:")
    for i, post in enumerate(sorted_by_reach[:5], 1):
        caption = (post.get("caption") or "")[:40].replace("\n", " ")
        print(f"  {i}. リーチ {post.get('reach', 0)}人 | いいね {post.get('like_count', 0)}件 | {post.get('timestamp', '')[:10]}")
        print(f"     {caption}...")
        print(f"     {post.get('permalink', '')}")

    print("\n💬 コメントが多かった投稿 TOP5:")
    for i, post in enumerate(sorted_by_comments[:5], 1):
        caption = (post.get("caption") or "")[:40].replace("\n", " ")
        print(f"  {i}. コメント {post.get('comments_count', 0)}件 | {post.get('timestamp', '')[:10]}")
        print(f"     {caption}...")
        print(f"     {post.get('permalink', '')}")

    # メディアタイプ別の集計
    type_count = {}
    type_likes = {}
    for post in posts:
        t = post.get("media_type", "不明")
        type_count[t] = type_count.get(t, 0) + 1
        type_likes[t] = type_likes.get(t, 0) + post.get("like_count", 0)

    print("\n📱 メディアタイプ別集計:")
    for t, count in type_count.items():
        avg = type_likes[t] // count if count > 0 else 0
        print(f"  {t}: {count}件（平均いいね数: {avg}）")

    return sorted_by_likes


# ───────────────────────────────
# レポートをファイルに保存
# ───────────────────────────────
def save_report(posts):
    filename = f"report_{datetime.now().strftime('%Y%m%d')}.txt"
    sorted_by_likes  = sorted(posts, key=lambda x: x.get("like_count", 0), reverse=True)
    sorted_by_saved  = sorted(posts[:20], key=lambda x: x.get("saved", 0), reverse=True)
    sorted_by_reach  = sorted(posts[:20], key=lambda x: x.get("reach", 0), reverse=True)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"Instagram分析レポート　{datetime.now().strftime('%Y/%m/%d')}\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"総投稿数: {len(posts)}件\n\n")

        f.write("【いいね TOP5】\n")
        for i, post in enumerate(sorted_by_likes[:5], 1):
            caption = (post.get("caption") or "")[:80].replace("\n", " ")
            f.write(f"{i}. いいね {post.get('like_count', 0)}件 | {post.get('timestamp', '')[:10]}\n")
            f.write(f"   {caption}...\n")
            f.write(f"   {post.get('permalink', '')}\n\n")

        f.write("【保存数 TOP5】\n")
        for i, post in enumerate(sorted_by_saved[:5], 1):
            caption = (post.get("caption") or "")[:80].replace("\n", " ")
            f.write(f"{i}. 保存 {post.get('saved', 0)}件 | リーチ {post.get('reach', 0)}人 | {post.get('timestamp', '')[:10]}\n")
            f.write(f"   {caption}...\n")
            f.write(f"   {post.get('permalink', '')}\n\n")

        f.write("【リーチ TOP5】\n")
        for i, post in enumerate(sorted_by_reach[:5], 1):
            caption = (post.get("caption") or "")[:80].replace("\n", " ")
            f.write(f"{i}. リーチ {post.get('reach', 0)}人 | いいね {post.get('like_count', 0)}件 | {post.get('timestamp', '')[:10]}\n")
            f.write(f"   {caption}...\n")
            f.write(f"   {post.get('permalink', '')}\n\n")

    print(f"\n📄 レポートを保存しました: {filename}")
    return filename


# ───────────────────────────────
# メイン実行
# ───────────────────────────────
if __name__ == "__main__":
    posts = fetch_all_my_posts()
    # いいね上位20件のインサイトを取得
    posts_sorted = sorted(posts, key=lambda x: x.get("like_count", 0), reverse=True)
    posts_enriched = enrich_with_insights(posts_sorted, top_n=20)
    # 残りの投稿も元のリストに戻す
    top_ids = {p["id"] for p in posts_enriched}
    all_posts = posts_enriched + [p for p in posts if p["id"] not in top_ids]
    analyze_my_posts(all_posts)
    save_report(all_posts)
    print("\n✅ 分析完了！")
