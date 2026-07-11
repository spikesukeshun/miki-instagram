"""
fetch_dashboard_data.py
────────────────────────────────────────────────────
AIマーケティングダッシュボード用のデータスナップショットを生成する。
毎週の更新時に実行 → dashboard/data/dashboard_data.json を上書きする。

取得内容:
  - 全投稿のメタデータ（いいね・コメント・カルーセル枚数・キャプション先頭）
  - 直近 INSIGHTS_SINCE 以降の投稿インサイト
    （reach / views / saved / shares / profile_visits / follows など）
  - アカウント日次インサイト（リーチ・フォロワー増減、直近30日）
  - アカウント週次合計（プロフィール閲覧・視聴・エンゲージ、直近16週）
  - テーマ分類（post_classifications.json + キーワードヒューリスティック）

実行:
  /usr/bin/python3 dashboard/fetch_dashboard_data.py

API仕様メモ（2026-07 実測）:
  - impressions は v22+ で廃止 → views を使う
  - FEED系（画像・カルーセル）は全メトリクスを1コールで取得できる
  - VIDEO（リール）は profile_visits / follows 非対応 → 縮小メトリクスで取得
  - アカウントの follower_count 日次は直近30日のみ
  - profile_views 等の合計値は metric_type=total_value なら過去の週でも取得可能
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent
WORKTREE_ROOT = DASHBOARD_DIR.parent
# posts_cache.json / post_classifications.json は gitignore のため
# worktree に存在しないことがある → main repo をフォールバック探索する
REPO_CANDIDATES = [
    WORKTREE_ROOT,
    Path.home() / "Desktop" / "美喜のinstagram",
]

sys.path.insert(0, str(next((p for p in REPO_CANDIDATES if (p / "load_env.py").exists()), WORKTREE_ROOT)))
from load_env import load_from_zshrc  # noqa: E402

load_from_zshrc()

TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN")
ACCOUNT_ID = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
API_BASE = "https://graph.facebook.com/v19.0"
JST = timezone(timedelta(hours=9))

OUTPUT_FILE = DASHBOARD_DIR / "data" / "dashboard_data.json"

# インサイトを取得する期間（それ以前はメタデータのみ）
INSIGHTS_SINCE = "2025-01-01"
# アカウント週次合計を遡る週数
ACCOUNT_WEEKS = 16

FEED_METRICS = "reach,views,saved,shares,likes,comments,total_interactions,profile_visits,follows"
VIDEO_METRICS = "reach,views,saved,shares,likes,comments,total_interactions"

# テーマ分類（post_classifications.json に無い投稿へのヒューリスティック）
THEME_KEYWORDS = [
    ("bridal", ["ブライダル", "花嫁", "挙式", "結婚式", "ウェディング", "ドレス", "前撮り", "プレ花嫁"]),
    ("reward", ["ご褒美", "リラックス", "癒し", "ジャグジー", "ハマム", "休日", "リフレッシュ"]),
    ("lifestyle", ["MIKIです", "mikiです", "私は", "自分語り", "想い", "感謝", "お客様のお声", "日常"]),
    ("menu", ["コース", "メニュー", "施術", "¥", "円", "キャビ", "ラジオ波", "フェイシャル", "毛穴", "小顔"]),
]


def api_get(path: str, **params) -> dict:
    params["access_token"] = TOKEN
    url = f"{API_BASE}/{path}?{urllib.parse.urlencode(params)}"
    return _get_url(url)


def _get_url(url: str, retries: int = 3) -> dict:
    last = {}
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as res:
                return json.load(res)
        except urllib.error.HTTPError as e:
            try:
                last = json.load(e)
            except Exception:
                last = {"error": {"message": str(e)}}
            # 4xx はリトライしても無駄（メトリクス非対応など）
            if e.code < 500:
                return last
        except Exception as e:  # ネットワーク断など
            last = {"error": {"message": str(e)}}
        time.sleep(2 * (attempt + 1))
    return last


def fetch_all_media() -> list[dict]:
    """全投稿のメタデータをページネーションで取得"""
    fields = ("id,caption,timestamp,media_type,media_product_type,"
              "like_count,comments_count,permalink,children{id}")
    posts = []
    data = api_get(f"{ACCOUNT_ID}/media", limit=100, fields=fields)
    while True:
        if "error" in data:
            raise RuntimeError(f"media取得エラー: {data['error'].get('message')}")
        posts.extend(data.get("data", []))
        nxt = data.get("paging", {}).get("next")
        if not nxt:
            break
        data = _get_url(nxt)
    return posts


def fetch_media_insights(media_id: str, media_type: str) -> dict:
    """1投稿のインサイトを取得。combinedで失敗したらメトリクス個別で救済"""
    metrics = VIDEO_METRICS if media_type == "VIDEO" else FEED_METRICS
    data = api_get(f"{media_id}/insights", metric=metrics)
    if "error" not in data:
        return _parse_insights(data)
    # combined が失敗 → 個別取得で取れるものだけ拾う
    result = {}
    for m in metrics.split(","):
        d = api_get(f"{media_id}/insights", metric=m)
        if "error" not in d:
            result.update(_parse_insights(d))
        time.sleep(0.1)
    return result


def _parse_insights(data: dict) -> dict:
    out = {}
    for item in data.get("data", []):
        vals = item.get("values") or [{}]
        v = vals[0].get("value")
        out[item["name"]] = v if isinstance(v, (int, float)) else 0
    return out


def load_theme_map() -> dict[str, str]:
    for root in REPO_CANDIDATES:
        f = root / "post_classifications.json"
        if f.exists():
            data = json.loads(f.read_text(encoding="utf-8"))
            return {c["media_id"]: c["theme"] for c in data.get("classifications", [])}
    return {}


def load_theme_overrides() -> dict[str, str]:
    """ダッシュボード専用の手動上書き（media_id → theme）"""
    f = DASHBOARD_DIR / "data" / "theme_overrides.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {}


def classify_by_caption(caption: str) -> str:
    for theme, words in THEME_KEYWORDS:
        if any(w in caption for w in words):
            return theme
    return "other"


def fetch_account_daily() -> list[dict]:
    """直近30日の日次リーチ・フォロワー純増"""
    now = datetime.now(JST)
    since = now - timedelta(days=30)
    data = api_get(f"{ACCOUNT_ID}/insights", metric="reach,follower_count",
                   period="day", since=int(since.timestamp()), until=int(now.timestamp()))
    if "error" in data:
        print(f"  日次インサイト取得エラー: {data['error'].get('message')}")
        return []
    by_date: dict[str, dict] = {}
    for item in data.get("data", []):
        for v in item.get("values", []):
            day = v.get("end_time", "")[:10]
            by_date.setdefault(day, {"date": day})[item["name"]] = v.get("value") or 0
    return sorted(by_date.values(), key=lambda x: x["date"])


def fetch_account_weekly() -> list[dict]:
    """週次（月曜始まりJST）のアカウント合計値を直近 ACCOUNT_WEEKS 週分"""
    now = datetime.now(JST)
    this_monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    weeks = []
    metrics = "profile_views,views,accounts_engaged,total_interactions,website_clicks,reach"
    for i in range(ACCOUNT_WEEKS):
        start = this_monday - timedelta(weeks=i)
        end = min(start + timedelta(days=7), now)
        d = api_get(f"{ACCOUNT_ID}/insights", metric=metrics, period="day",
                    metric_type="total_value",
                    since=int(start.timestamp()), until=int(end.timestamp()))
        entry = {"week_start": start.strftime("%Y-%m-%d"), "partial": end < start + timedelta(days=7)}
        if "error" in d:
            entry["error"] = d["error"].get("message", "")[:80]
        else:
            for item in d.get("data", []):
                entry[item["name"]] = item.get("total_value", {}).get("value")
        weeks.append(entry)
        time.sleep(0.25)
    return sorted(weeks, key=lambda w: w["week_start"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--insights-since", default=INSIGHTS_SINCE,
                        help="この日付以降の投稿はインサイトも取得（YYYY-MM-DD）")
    args = parser.parse_args()

    if not TOKEN or not ACCOUNT_ID:
        print("❌ INSTAGRAM_ACCESS_TOKEN / INSTAGRAM_BUSINESS_ACCOUNT_ID が未設定です")
        sys.exit(1)

    account = api_get(ACCOUNT_ID, fields="username,followers_count,follows_count,media_count")
    if "error" in account:
        print(f"❌ アカウント情報取得エラー（トークン失効の可能性）: {account['error'].get('message')}")
        sys.exit(1)
    print(f"アカウント: @{account.get('username')} フォロワー{account.get('followers_count')}人 "
          f"投稿{account.get('media_count')}件")

    print("全投稿メタデータを取得中...")
    media = fetch_all_media()
    print(f"  {len(media)}件取得")

    theme_map = load_theme_map()
    overrides = load_theme_overrides()

    posts = []
    targets = [m for m in media if (m.get("timestamp") or "") >= args.insights_since]
    print(f"インサイト取得対象: {len(targets)}件（{args.insights_since}以降）")

    for i, m in enumerate(media):
        mid = m["id"]
        caption = m.get("caption") or ""
        theme = overrides.get(mid) or theme_map.get(mid)
        theme_source = "override" if mid in overrides else ("classified" if theme else "heuristic")
        if not theme:
            theme = classify_by_caption(caption)

        children = m.get("children", {}).get("data", []) if isinstance(m.get("children"), dict) else []
        post = {
            "media_id": mid,
            "timestamp": m.get("timestamp"),
            "media_type": m.get("media_type"),
            "permalink": m.get("permalink"),
            "caption_head": caption[:120].replace("\n", " "),
            "slide_count": len(children) if m.get("media_type") == "CAROUSEL_ALBUM" else 1,
            "likes": m.get("like_count", 0),
            "comments": m.get("comments_count", 0),
            "theme": theme,
            "theme_source": theme_source,
            "insights": None,
        }
        if (m.get("timestamp") or "") >= args.insights_since:
            ins = fetch_media_insights(mid, m.get("media_type", ""))
            post["insights"] = ins or None
            n = sum(1 for p in posts if p["insights"] is not None) + 1
            print(f"  [{n}/{len(targets)}] {m.get('timestamp','')[:10]} "
                  f"reach={ins.get('reach')} saved={ins.get('saved')} pv={ins.get('profile_visits')}")
            time.sleep(0.25)
        posts.append(post)

    print("アカウント日次インサイト取得中...")
    daily = fetch_account_daily()
    print(f"  {len(daily)}日分")

    print(f"アカウント週次合計取得中（{ACCOUNT_WEEKS}週）...")
    weekly = fetch_account_weekly()

    output = {
        "fetched_at": datetime.now(JST).isoformat(timespec="seconds"),
        "account": {
            "username": account.get("username"),
            "followers_count": account.get("followers_count"),
            "media_count": account.get("media_count"),
        },
        "account_daily": daily,
        "account_weekly": weekly,
        "posts": sorted(posts, key=lambda p: p["timestamp"] or "", reverse=True),
        # 毎週の更新時に Claude Code が本物の所見を書き込むための欄（任意）
        "claude_comment": None,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=1), encoding="utf-8")
    with_ins = sum(1 for p in posts if p["insights"])
    print(f"\n✅ 保存完了: {OUTPUT_FILE}")
    print(f"   投稿{len(posts)}件（うちインサイトあり{with_ins}件）/ 日次{len(daily)}日 / 週次{len(weekly)}週")


if __name__ == "__main__":
    main()
