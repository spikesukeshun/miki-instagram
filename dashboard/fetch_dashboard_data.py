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
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
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
# テーマ手動上書きの読み込み元。後に読むファイルが勝つため、
# main repo 側（get_recent_insights.py が参照する正）を最後に置く。
THEME_OVERRIDE_FILES = [
    DASHBOARD_DIR / "data" / "theme_overrides.json",
    *(root / "theme_overrides.json" for root in REPO_CANDIDATES),
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

# ──────────────────────────────────────────────────────────
# テーマ分類（post_classifications.json に無い投稿へのヒューリスティック）
# get_recent_insights.py と同じ重み付きスコアリング方式。
#
# 旧実装は固定順の先頭一致だったため、旧スタイルの自己紹介に含まれる
# 「ブライダルエステも得意♪」が bridal に一致し、履歴の大半を bridal と
# 誤判定していた（322件の人手ラベルに対し 32件=9.9% しか当たらない。
# 多数派ベースライン 65.5% より低い）。この方式では 234件=72.7%。
#
# 現行のキャプションは CLAUDE.md のルールにより
#   1〜2行目: 主題を要約したSEO導入文
#   3行目以降: 「MIKIです。」から本文
# という構造なので、導入文に出た語を強く重み付けする。
# ──────────────────────────────────────────────────────────

# 全投稿に出る自己紹介・料金表・ハッシュタグはテーマ信号にならないので落とす
BOILERPLATE_MARKERS = [
    "20代～30代の口コミ", "20代〜30代の口コミ", "シデスコ国際ライセンス",
    "〜MIKI〜", ":*:*:*:*", "＼ご予約", "▶︎", "ご予約・お問い合わせ",
]
LEAD_MARKERS = ["MIKIです", "mikiです"]
LEAD_BOOST = 4            # 導入文に出た語の重み倍率
LEAD_FALLBACK_CHARS = 120  # 「MIKIです」が無い旧スタイル用

# (重み, 語) — 重み5は主題を確定させる明示マーカー
THEME_KEYWORDS = {
    "bridal": [
        (3, ["ブライダル", "花嫁", "プレ花嫁", "卒花", "挙式", "結婚式", "ウェディング",
             "前撮り", "フォトウェディング", "婚礼", "式まで", "式当日", "秋婚", "春婚",
             "冬婚", "夏婚", "マリッジ"]),
        (1, ["ドレス", "披露宴", "入籍"]),
    ],
    "reward": [
        (3, ["ご褒美", "労わ", "労る", "ねぎら", "頑張った自分", "頑張ってきた自分",
             "頑張りすぎた自分", "自分を大切", "自分のための時間", "自分時間",
             "自分へのプレゼント"]),
        (1, ["リセット", "疲れ", "癒し", "リフレッシュ", "リラックス", "解放"]),
    ],
    "lifestyle": [
        (5, ["自分語り", "プライベート投稿", "お休みの日", "原点", "ぼやか", "私自身の話"]),
        (3, ["プライベート", "休日の過ごし方", "大切にしている", "大切なこと",
             "ライフプラン", "教わる", "教えてくれた", "私の話", "きっかけ", "初心",
             "お客様のお声", "子供の頃", "ご機嫌", "習慣"]),
        (1, ["想い", "日常", "本音", "正直", "感謝", "趣味"]),
    ],
    "menu": [
        (3, ["コース", "メニュー", "料金", "キャビテーション", "ラジオ波", "EMS",
             "痩身", "フェイシャル", "マシン", "ハーブピーリング", "ご質問",
             "よくある質問", "予約方法", "アクセス", "契約", "キャンペーン",
             "オプション", "毛穴", "小顔", "対策"]),
        (1, ["施術", "ケア", "肌", "むくみ", "予約", "円"]),
    ],
}
# 同点時の優先順（主題としての具体性が高い順）
THEME_PRIORITY = ["bridal", "reward", "lifestyle", "menu"]


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


# Graph API のレート制限エラーコード（この場合は個別取得に降りず待って再試行する）
RATE_LIMIT_CODES = {4, 17, 32, 613}


def _is_rate_limited(data: dict) -> bool:
    return data.get("error", {}).get("code") in RATE_LIMIT_CODES


def fetch_media_insights(media_id: str, media_type: str) -> dict:
    """1投稿のインサイトを取得。
    レート制限 → バックオフして再試行（個別取得に降りると呼び出しが9倍になるため）。
    メトリクス非対応などの4xx → 個別取得で取れるものだけ拾う。"""
    metrics = VIDEO_METRICS if media_type == "VIDEO" else FEED_METRICS
    for attempt in range(3):
        data = api_get(f"{media_id}/insights", metric=metrics)
        if "error" not in data:
            return _parse_insights(data)
        if not _is_rate_limited(data):
            break
        wait = 60 * (attempt + 1)
        print(f"  レート制限を検知 → {wait}秒待機して再試行 ({attempt + 1}/3)")
        time.sleep(wait)
    else:
        return {}
    # combined がメトリクス非対応等で失敗 → 個別取得で取れるものだけ拾う
    result = {}
    for m in metrics.split(","):
        d = api_get(f"{media_id}/insights", metric=m)
        if _is_rate_limited(d):
            break
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
    """テーマの手動上書き（media_id → theme）を全ソースからマージする。

    ダッシュボード側と main repo 側で別々に育って分類がずれた実績があるため
    （2026-08: 直近7投稿が誤ラベル）、片方だけを読まず常に両方をマージし、
    重複した media_id は main repo 側を採用する。
    `_comment` 等のアンダースコア始まりのキーはメタ情報なので除外する。
    """
    merged: dict[str, str] = {}
    for f in THEME_OVERRIDE_FILES:
        if not f.exists():
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        merged.update({k: v for k, v in data.items() if not k.startswith("_")})
    return merged


def _strip_boilerplate(caption: str) -> str:
    """定型の自己紹介・料金表・ハッシュタグを落として主題部分だけ残す。"""
    cut = len(caption)
    for m in BOILERPLATE_MARKERS:
        i = caption.find(m)
        if i != -1:
            cut = min(cut, i)
    # 冒頭すぐに定型文が来る場合は切ると何も残らないので全文を使う
    body = caption[:cut] if cut > 40 else caption
    return re.sub(r"#\S+", "", body)


def _split_lead(body: str) -> tuple[str, str]:
    """SEO導入文（主題）と本文に分ける。"""
    for m in LEAD_MARKERS:
        i = body.find(m)
        if 0 < i <= 400:
            return body[:i], body[i:]
    return body[:LEAD_FALLBACK_CHARS], body[LEAD_FALLBACK_CHARS:]


def classify_by_caption(caption: str) -> str:
    body = _strip_boilerplate(caption or "")
    lead, rest = _split_lead(body)
    score = Counter()
    for theme, groups in THEME_KEYWORDS.items():
        for weight, words in groups:
            for w in words:
                score[theme] += weight * (lead.count(w) * LEAD_BOOST + rest.count(w))
    best = max(score.values()) if score else 0
    if best == 0:
        return "other"
    return next(t for t in THEME_PRIORITY if score[t] == best)


def fetch_account_daily() -> list[dict]:
    """直近30日の日次リーチ・フォロワー純増。
    follower_count の「直近30日まで」制約に秒単位で抵触しないよう29日で要求する。
    end_time は「その時刻に終わる期間」を指すため、値の帰属日は end_time の前日。"""
    now = datetime.now(JST)
    since = now - timedelta(days=29)
    data = api_get(f"{ACCOUNT_ID}/insights", metric="reach,follower_count",
                   period="day", since=int(since.timestamp()), until=int(now.timestamp()))
    if "error" in data:
        print(f"  日次インサイト取得エラー: {data['error'].get('message')}")
        return []
    by_date: dict[str, dict] = {}
    for item in data.get("data", []):
        for v in item.get("values", []):
            end = v.get("end_time", "")
            if not end:
                continue
            try:
                day = (datetime.strptime(end[:10], "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
            except ValueError:
                continue
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
    print(f"テーマ手動上書き: {len(overrides)}件"
          f"（{sum(1 for f in THEME_OVERRIDE_FILES if f.exists())}ファイルをマージ）")

    media = [m for m in media if m.get("timestamp")]  # timestamp欠損は分析不能のため除外
    posts = []
    targets = [m for m in media if (m.get("timestamp") or "") >= args.insights_since]
    print(f"インサイト取得対象: {len(targets)}件（{args.insights_since}以降）")

    done = 0
    failed = 0
    for m in media:
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
            done += 1
            if not ins:
                failed += 1
            print(f"  [{done}/{len(targets)}] {m.get('timestamp','')[:10]} "
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
    if failed:
        print(f"   ⚠️ インサイト取得に失敗した投稿が{failed}件あります（レート制限の可能性。時間をおいて再実行を推奨）")


if __name__ == "__main__":
    main()
