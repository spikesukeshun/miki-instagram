"""
fetch_ga4_data.py
────────────────────────────────────────────────────
コンバージョンLP（www.esthe-miki.workers.dev）の GA4 / Search Console 実測を取得する。
fetch_dashboard_data.py から呼ばれ、dashboard_data.json の "lp" に入る。

これが埋まると、ダッシュボードのファネルが
  リーチ → プロフィール閲覧 → 【LP訪問】 → 【予約導線クリック】 → 予約
まで実数でつながる（従来は「プロフィール閲覧」の次が推定値だった）。

実行（単体テスト）:
  /usr/bin/python3 dashboard/fetch_ga4_data.py

必要な環境変数（~/.zshrc に置く。→ load_env.py が読む）:
  GA4_PROPERTY_ID              例: 549776757   ← GA4のURL a404550589p<これ>
  GOOGLE_APPLICATION_CREDENTIALS  サービスアカウントJSONの絶対パス
  SEARCH_CONSOLE_SITE_URL      任意。例: https://www.esthe-miki.workers.dev/
                               未設定ならSearch Consoleはスキップする

⚠ 未設定でも例外を投げない。None を返して週次更新を止めないこと（LPは後付けの計測なので、
  ここで落ちると Instagram 側の更新まで巻き添えになる）。

⚠ 依存は google.oauth2 + google.auth のみ（gspread が既に入れている）。
  google-analytics-data ライブラリは使わない。REST を直接叩けば追加インストール不要。

API仕様メモ（2026-08 実測）:
  - GA4 Data API の date ディメンションは「プロパティのタイムゾーン」基準で YYYYMMDD 文字列
  - 週の切り方は fetch_dashboard_data.py の fetch_account_weekly と揃える（月曜始まりJST）
  - Search Console は最新2〜3日ぶんが未確定（遅延）。当日を含めても0で返るのが正常
  - サービスアカウントは GA4 と Search Console の**両方**に閲覧者として追加が要る

⚠ ローカルは /usr/bin/python3 = 3.9。`dict | None` 記法は3.10+なので使えない。
  `from __future__ import annotations` を入れて注釈を文字列化している（→ local_python_env）。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent
# load_env.py は gitignore で worktree に無いことがある → main repo までフォールバック探索
# （fetch_dashboard_data.py の REPO_CANDIDATES と同じ考え方）
REPO_CANDIDATES = [
    DASHBOARD_DIR.parent,
    Path.home() / "Desktop" / "美喜のinstagram",
]
JST = timezone(timedelta(hours=9))

# LP公開日。これより前の週は取りに行かない（全部ゼロで表が伸びるだけなので）
LP_LAUNCH_DATE = "2026-08-14"
# 遡る最大週数。fetch_dashboard_data.py の ACCOUNT_WEEKS と揃えている
MAX_WEEKS = 16

GA4_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"

GA4_ENDPOINT = "https://analyticsdata.googleapis.com/v1beta/properties/{pid}:runReport"
GSC_ENDPOINT = "https://searchconsole.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"

# 予約導線のイベント。build_site.py の gtag('event', ...) と一致させること
CTA_EVENTS = ("cta_dm", "cta_hotpepper", "generate_lead")


def _session(scopes: list[str]):
    """サービスアカウントJSONから認証済みHTTPセッションを作る。未設定なら None。"""
    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not key_path or not Path(key_path).expanduser().exists():
        return None
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
    except ImportError:
        return None
    creds = service_account.Credentials.from_service_account_file(
        str(Path(key_path).expanduser()), scopes=scopes
    )
    return AuthorizedSession(creds)


def _monday(d: datetime) -> datetime:
    return (d - timedelta(days=d.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _week_starts() -> list[str]:
    """LP公開週から今週まで、月曜始まりJSTの week_start を古い順に返す。"""
    now = datetime.now(JST)
    launch = datetime.strptime(LP_LAUNCH_DATE, "%Y-%m-%d").replace(tzinfo=JST)
    first, this = _monday(launch), _monday(now)
    out, cur = [], first
    while cur <= this and len(out) < MAX_WEEKS:
        out.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(weeks=1)
    return out


def _is_instagram(source_medium: str) -> bool:
    """Instagram経由をひとまとめに判定する。

    ⚠ utm_medium 欠落の名残で `instagram / (not set)` が過去分に残っている。
      2026-08-30 に `utm_medium=social` を付けたので以降は `instagram / social` だが、
      期間比較のときに分断されないよう前方一致でまとめる（→ lp/PUBLISH.md）。
    """
    return source_medium.lower().startswith("instagram")


def _run_report(sess, pid: str, body: dict) -> dict:
    res = sess.post(GA4_ENDPOINT.format(pid=pid), json=body, timeout=60)
    if res.status_code != 200:
        return {"_error": f"HTTP {res.status_code}: {res.text[:200]}"}
    return res.json()


def _rows(report: dict) -> list[tuple[list[str], list[str]]]:
    """runReport の戻りを (ディメンション値, 指標値) の並びに均す。"""
    return [
        ([d.get("value", "") for d in r.get("dimensionValues", [])],
         [m.get("value", "0") for m in r.get("metricValues", [])])
        for r in report.get("rows", [])
    ]


def fetch_ga4(pid: str, start: str) -> dict | None:
    """日別×参照元/メディアのセッション指標と、CTAイベント数をまとめて取る。"""
    sess = _session([GA4_SCOPE])
    if sess is None:
        return None

    # ① セッション指標（日 × 参照元/メディア）
    traffic = _run_report(sess, pid, {
        "dateRanges": [{"startDate": start, "endDate": "today"}],
        "dimensions": [{"name": "date"}, {"name": "sessionSourceMedium"}],
        "metrics": [
            {"name": "sessions"},
            {"name": "engagedSessions"},
            {"name": "userEngagementDuration"},
        ],
        "limit": 10000,
    })
    if "_error" in traffic:
        return {"error": traffic["_error"]}

    # ② 予約導線イベント（日 × 参照元/メディア × イベント名）
    events = _run_report(sess, pid, {
        "dateRanges": [{"startDate": start, "endDate": "today"}],
        "dimensions": [{"name": "date"}, {"name": "sessionSourceMedium"},
                       {"name": "eventName"}],
        "metrics": [{"name": "eventCount"}],
        "dimensionFilter": {
            "filter": {
                "fieldName": "eventName",
                "inListFilter": {"values": list(CTA_EVENTS)},
            }
        },
        "limit": 10000,
    })
    if "_error" in events:
        return {"error": events["_error"]}

    return {"traffic": _rows(traffic), "events": _rows(events)}


def fetch_search_console(site_url: str, start: str, end: str) -> dict | None:
    """検索の表示回数・クリック・掲載順位と、上位クエリ。母数が少ないとクエリは空で返る。"""
    sess = _session([GSC_SCOPE])
    if sess is None:
        return None
    url = GSC_ENDPOINT.format(site=urllib.parse.quote(site_url, safe=""))

    def _q(dimensions: list[str]) -> dict:
        res = sess.post(url, json={
            "startDate": start, "endDate": end,
            "dimensions": dimensions, "rowLimit": 25,
        }, timeout=60)
        if res.status_code != 200:
            return {"_error": f"HTTP {res.status_code}: {res.text[:200]}"}
        return res.json()

    totals = _q([])
    if "_error" in totals:
        return {"error": totals["_error"]}
    row = (totals.get("rows") or [{}])[0]

    queries = _q(["query"])
    return {
        "clicks": row.get("clicks", 0),
        "impressions": row.get("impressions", 0),
        "ctr": round(row.get("ctr", 0.0), 4),
        "position": round(row.get("position", 0.0), 1),
        # 表示回数が少ないうちは Google 側が返さない（匿名化）。空配列が正常。
        "queries": [
            {"query": r["keys"][0], "clicks": r.get("clicks", 0),
             "impressions": r.get("impressions", 0),
             "position": round(r.get("position", 0.0), 1)}
            for r in (queries.get("rows") or [])
        ],
    }


def _aggregate(ga4: dict, week_starts: list[str]) -> tuple[list[dict], list[dict]]:
    """日別の生データを、月曜始まりの週サマリ と 参照元/メディア別サマリ に畳む。"""
    by_week = {
        w: {"week_start": w, "sessions": 0, "engaged_sessions": 0,
            "engagement_sec": 0, "instagram_sessions": 0,
            "instagram_engaged_sessions": 0,
            **{e: 0 for e in CTA_EVENTS},
            **{f"instagram_{e}": 0 for e in CTA_EVENTS}}
        for w in week_starts
    }
    by_source: dict[str, dict] = {}

    def week_of(yyyymmdd: str) -> str | None:
        try:
            d = datetime.strptime(yyyymmdd, "%Y%m%d").replace(tzinfo=JST)
        except ValueError:
            return None
        w = _monday(d).strftime("%Y-%m-%d")
        return w if w in by_week else None

    for dims, mets in ga4.get("traffic", []):
        date, sm = dims[0], dims[1]
        sessions, engaged, dur = (int(float(m)) for m in mets)
        src = by_source.setdefault(sm, {
            "source_medium": sm, "sessions": 0, "engaged_sessions": 0,
            "engagement_sec": 0, **{e: 0 for e in CTA_EVENTS}})
        src["sessions"] += sessions
        src["engaged_sessions"] += engaged
        src["engagement_sec"] += dur
        w = week_of(date)
        if w:
            b = by_week[w]
            b["sessions"] += sessions
            b["engaged_sessions"] += engaged
            b["engagement_sec"] += dur
            if _is_instagram(sm):
                b["instagram_sessions"] += sessions
                b["instagram_engaged_sessions"] += engaged

    for dims, mets in ga4.get("events", []):
        date, sm, ev = dims[0], dims[1], dims[2]
        count = int(float(mets[0]))
        if ev not in CTA_EVENTS:
            continue
        by_source.setdefault(sm, {
            "source_medium": sm, "sessions": 0, "engaged_sessions": 0,
            "engagement_sec": 0, **{e: 0 for e in CTA_EVENTS}})[ev] += count
        w = week_of(date)
        if w:
            by_week[w][ev] += count
            if _is_instagram(sm):
                by_week[w][f"instagram_{ev}"] += count

    def finish(d: dict) -> dict:
        s = d.pop("engagement_sec", 0)
        n = d.get("sessions", 0)
        d["avg_engagement_sec"] = round(s / n) if n else 0
        return d

    now_week = _monday(datetime.now(JST)).strftime("%Y-%m-%d")
    weeks = []
    for w in week_starts:
        e = finish(by_week[w])
        e["partial"] = (w == now_week)
        weeks.append(e)
    sources = sorted((finish(v) for v in by_source.values()),
                     key=lambda x: -x["sessions"])
    return weeks, sources


def fetch_lp_data() -> dict | None:
    """dashboard_data.json の "lp" に入れる辞書。未設定なら None（週次更新は止めない）。"""
    pid = os.getenv("GA4_PROPERTY_ID")
    if not pid:
        return None

    week_starts = _week_starts()
    if not week_starts:
        return None
    start = week_starts[0]

    ga4 = fetch_ga4(pid, start)
    if ga4 is None:
        return None
    if "error" in ga4:
        return {"fetched_at": datetime.now(JST).isoformat(timespec="seconds"),
                "error": ga4["error"]}

    weeks, sources = _aggregate(ga4, week_starts)
    out = {
        "fetched_at": datetime.now(JST).isoformat(timespec="seconds"),
        "property_id": pid,
        "since": start,
        "weeks": weeks,
        "sources": sources,
    }

    site = os.getenv("SEARCH_CONSOLE_SITE_URL")
    if site:
        end = datetime.now(JST).strftime("%Y-%m-%d")
        sc = fetch_search_console(site, start, end)
        if sc is not None:
            out["search_console"] = sc
    return out


def main() -> int:
    for root in REPO_CANDIDATES:
        if (root / "load_env.py").exists():
            sys.path.insert(0, str(root))
            break
    try:
        from load_env import load_from_zshrc
        load_from_zshrc()
    except ImportError:
        pass

    if not os.getenv("GA4_PROPERTY_ID"):
        print("⚠️ GA4_PROPERTY_ID が未設定です。~/.zshrc に設定してください。")
        print("   （GA4のURL analytics.google.com/.../a404550589p<ここ> の数字）")
        return 1
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        print("⚠️ GOOGLE_APPLICATION_CREDENTIALS が未設定です。")
        print("   サービスアカウントJSONの絶対パスを ~/.zshrc に設定してください。")
        return 1

    data = fetch_lp_data()
    if data is None:
        print("⚠️ 設定が不足しているため取得できませんでした。")
        return 1
    if "error" in data:
        print(f"❌ 取得エラー: {data['error']}")
        return 1

    print(json.dumps(data, ensure_ascii=False, indent=1))
    tot = sum(w["sessions"] for w in data["weeks"])
    ig = sum(w["instagram_sessions"] for w in data["weeks"])
    hp = sum(w["cta_hotpepper"] for w in data["weeks"])
    print(f"\n✅ {len(data['weeks'])}週分 / セッション{tot}（うちInstagram経由{ig}）"
          f" / cta_hotpepper {hp}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
