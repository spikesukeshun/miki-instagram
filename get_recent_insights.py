"""
get_recent_insights.py
直近10件の投稿のインサイトを取得し、テーマ別集計と戦略ヒントを出力する。
出力: recent_insights.json
CLAUDE.md 必須スクリプト（スケジュール組成前に必ず実行）

メトリクス更新（v22.0準拠）:
- impressions は廃止 → views に置き換え
- 取得指標: reach / saved / views / profile_visits / follows / shares / comments / total_interactions

DM予約導線視点:
- profile_visits（PV）と follows を中間指標として強調表示
- PV順でテーマランキング（いいね順だけでなく予約導線スコアも評価）
"""
import os
import json
import time
from datetime import datetime
import requests

from load_env import load_from_zshrc

load_from_zshrc()

USER_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN")
ACCOUNT_ID = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
API_BASE = "https://graph.facebook.com/v19.0"

# 親リポジトリの post_classifications.json を参照
_REPO_ROOT_GUESS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
CLASSIFICATIONS_PATH_CANDIDATES = [
    os.path.join(_REPO_ROOT_GUESS, "post_classifications.json"),
    "/Users/shunsuke/Desktop/美喜のinstagram/post_classifications.json",
    "post_classifications.json",
]
OUTPUT_PATH = "recent_insights.json"

THEME_LABELS = {
    "lifestyle": "ライフスタイル・自己語り",
    "menu": "メニュー・サービス",
    "bridal": "ブライダルエステ",
    "reward": "ご褒美エステ",
    "before_after": "Before/After",
    "voice": "お客様の声",
    "empathy": "悩み共感",
}

# DM予約導線テーマ（業界推奨60%目安）
DM_FUNNEL_THEMES = {"before_after", "voice", "menu"}
EDUCATION_THEMES = {"empathy"}
LIFESTYLE_THEMES = {"lifestyle", "reward", "bridal"}  # bridal は文脈で動くがリーチ燃料寄り


def get_page_token():
    """ユーザートークンからページアクセストークンを取得"""
    res = requests.get(
        f"{API_BASE}/me/accounts",
        params={"access_token": USER_TOKEN},
    ).json()
    if "error" in res:
        raise Exception(f"me/accounts 取得失敗: {res['error']}")
    for page in res.get("data", []):
        ig = requests.get(
            f"{API_BASE}/{page['id']}",
            params={
                "fields": "instagram_business_account",
                "access_token": page["access_token"],
            },
        ).json()
        if ig.get("instagram_business_account", {}).get("id") == ACCOUNT_ID:
            return page["access_token"]
    raise Exception("Instagram Business Account に紐づく Page Token が見つからない")


def fetch_recent_posts(page_token, limit=10):
    """直近の投稿を limit 件取得"""
    res = requests.get(
        f"{API_BASE}/{ACCOUNT_ID}/media",
        params={
            "access_token": page_token,
            "limit": limit,
            "fields": "id,caption,timestamp,like_count,comments_count,media_type,permalink",
        },
    ).json()
    if "error" in res:
        raise Exception(f"media 取得失敗: {res['error']}")
    return res.get("data", [])


def fetch_post_insights(post_id, page_token):
    """投稿のインサイトを取得"""
    metrics = "reach,saved,views,total_interactions,profile_visits,shares,comments,follows"
    res = requests.get(
        f"{API_BASE}/{post_id}/insights",
        params={"metric": metrics, "access_token": page_token},
    ).json()
    out = {}
    for it in res.get("data", []):
        try:
            out[it["name"]] = it["values"][0]["value"]
        except (KeyError, IndexError):
            pass
    if "error" in res and not out:
        out["_error"] = res["error"].get("message", "")[:120]
    return out


def load_classifications():
    """投稿分類辞書を返す（media_id → theme）"""
    for path in CLASSIFICATIONS_PATH_CANDIDATES:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {c["media_id"]: c["theme"] for c in data.get("classifications", [])}
    return {}


def classify_by_caption(caption):
    """post_classifications.json に無い投稿を caption からヒューリスティック分類"""
    cap = (caption or "").lower()
    # Before/After 検出
    if any(k in cap for k in ["before", "after", "ビフォー", "アフター", "変化前", "変化後"]):
        return "before_after"
    # お客様の声
    if any(k in cap for k in ["お客様の声", "体験談", "お客様から", "卒花嫁様"]):
        return "voice"
    if any(k in cap for k in ["ブライダル", "花嫁", "結婚式", "挙式", "ウェディング"]):
        return "bridal"
    if any(k in cap for k in ["ご褒美", "自分時間", "リセット", "週末", "休日"]):
        return "reward"
    if any(k in cap for k in ["メニュー", "コース", "料金", "vipコース", "施術内容"]):
        return "menu"
    if any(k in cap for k in ["仕事", "キャリア", "働き方", "ライフプラン", "自己肯定"]):
        return "empathy"
    return "lifestyle"


def compute_theme_aggregates(posts):
    """テーマ別の平均値を計算"""
    by_theme = {}
    for p in posts:
        t = p.get("theme", "unknown")
        if t not in by_theme:
            by_theme[t] = {
                "count": 0,
                "likes": 0,
                "saved": 0,
                "reach": 0,
                "views": 0,
                "pv": 0,
                "follows": 0,
            }
        by_theme[t]["count"] += 1
        by_theme[t]["likes"] += p.get("like_count", 0) or 0
        by_theme[t]["saved"] += p.get("saved", 0) or 0
        by_theme[t]["reach"] += p.get("reach", 0) or 0
        by_theme[t]["views"] += p.get("views", 0) or 0
        by_theme[t]["pv"] += p.get("profile_visits", 0) or 0
        by_theme[t]["follows"] += p.get("follows", 0) or 0
    for v in by_theme.values():
        c = v["count"] or 1
        v["avg_likes"] = round(v["likes"] / c, 1)
        v["avg_saved"] = round(v["saved"] / c, 1)
        v["avg_reach"] = round(v["reach"] / c, 1)
        v["avg_views"] = round(v["views"] / c, 1)
        v["avg_pv"] = round(v["pv"] / c, 2)
        v["avg_follows"] = round(v["follows"] / c, 2)
    return by_theme


def print_strategy_hints(by_theme, posts):
    """戦略ヒントを出力（DM予約導線視点）"""
    print()
    print("=" * 70)
    print("📊 テーマ別 中間指標サマリー（直近投稿）")
    print("=" * 70)

    rows = []
    for t, v in by_theme.items():
        label = THEME_LABELS.get(t, t)
        rows.append((t, label, v))

    print(
        f"{'テーマ':<22s} {'件数':>4s} {'いいね':>6s} {'保存':>5s} {'リーチ':>6s} {'PV':>5s} {'follows':>7s}"
    )
    print("-" * 70)

    # PV順にソート（DM導線視点）
    rows.sort(key=lambda x: x[2].get("avg_pv", 0), reverse=True)
    for _, label, v in rows:
        print(
            f"{label:<22s} {v['count']:>4d} {v.get('avg_likes',0):>6.1f} "
            f"{v.get('avg_saved',0):>5.1f} {v.get('avg_reach',0):>6.1f} "
            f"{v.get('avg_pv',0):>5.2f} {v.get('avg_follows',0):>7.2f}"
        )

    print()
    print("💡 戦略ヒント（DM予約導線視点・最終KPI=初DM獲得）")
    print("-" * 70)

    # PV(プロフィール訪問)トップ → DM導線最有力
    if rows:
        top_pv = rows[0]
        print(f"・PV(プロフィール訪問) トップ: {top_pv[1]}（avg {top_pv[2].get('avg_pv',0):.2f}）")
        print(f"  → このテーマは DM導線に最も近い。次回も継続投稿を検討")

    # いいね最大のテーマ（リーチ燃料候補）
    rows_likes = sorted(rows, key=lambda x: x[2].get("avg_likes", 0), reverse=True)
    if rows_likes and rows_likes[0][0] != rows[0][0]:
        top_likes = rows_likes[0]
        print(f"・いいねトップ: {top_likes[1]}（avg {top_likes[2].get('avg_likes',0):.1f}）")
        print(f"  → リーチ拡大の燃料として有効。DM導線とは別軸として両立を狙う")

    # 配分の確認
    funnel_ct = sum(v["count"] for t, _, v in rows if t in DM_FUNNEL_THEMES)
    edu_ct = sum(v["count"] for t, _, v in rows if t in EDUCATION_THEMES)
    life_ct = sum(v["count"] for t, _, v in rows if t in LIFESTYLE_THEMES)
    total = funnel_ct + edu_ct + life_ct
    if total > 0:
        print()
        print(f"・配分（直近{total}件）: 予約導線{funnel_ct}件 / 教育{edu_ct}件 / 日常{life_ct}件")
        print(
            f"  → 黄金比目標: 60% / 20% / 20%（実態 "
            f"{int(funnel_ct/total*100)}% / {int(edu_ct/total*100)}% / {int(life_ct/total*100)}%）"
        )

    print()
    print("💡 長期戦略（391件分析・2026-04-14時点）との照合")
    print("-" * 70)
    print("・ライフスタイル・自己語り: 月2〜3本必須（リーチ燃料）")
    print("・メニュー・サービス: 全体の50%以下（飽きられやすい）")
    print("・予約導線テーマ（B/A・お客様声・施術詳細）: 月60%目安")
    print("・DM未獲得時の最優先施策: bio・ハイライト整備＋CTA文言テーマ別出し分け")


def main():
    print("📥 ページアクセストークンを取得中...")
    page_token = get_page_token()

    print("📥 直近の投稿を取得中（最大10件）...")
    posts = fetch_recent_posts(page_token, limit=10)
    print(f"   取得: {len(posts)}件")

    classifications = load_classifications()
    if classifications:
        print(f"   既存分類: {len(classifications)}件読み込み")

    print("📥 各投稿のインサイトを取得中...")
    for i, p in enumerate(posts, 1):
        ins = fetch_post_insights(p["id"], page_token)
        p.update(ins)
        if p["id"] in classifications:
            p["theme"] = classifications[p["id"]]
            p["theme_source"] = "classifications"
        else:
            p["theme"] = classify_by_caption(p.get("caption"))
            p["theme_source"] = "heuristic"
        print(f"   {i}/{len(posts)} 完了", end="\r")
        time.sleep(0.3)
    print()

    # 投稿一覧
    print()
    print("=" * 70)
    print("📋 直近10件の投稿（新しい順）")
    print("=" * 70)
    for p in posts:
        ts = p["timestamp"][:10]
        cap = (p.get("caption") or "")[:38].replace("\n", " ")
        theme_label = THEME_LABELS.get(p.get("theme"), p.get("theme", "?"))
        print(
            f"  {ts} | {theme_label[:14]:<14s} | "
            f"likes={p.get('like_count',0):>3d} saved={p.get('saved',0):>2d} "
            f"reach={p.get('reach',0):>4d} PV={p.get('profile_visits',0):>2d} | {cap}"
        )

    # テーマ別集計
    by_theme = compute_theme_aggregates(posts)
    print_strategy_hints(by_theme, posts)

    # JSON保存
    output = {
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "post_count": len(posts),
        "posts": posts,
        "by_theme": by_theme,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print()
    print(f"💾 {OUTPUT_PATH} に保存しました")


if __name__ == "__main__":
    main()
