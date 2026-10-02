"""Threads 1か月実験のレポート（継続判断の材料）。2026-10 追加。

  python3 threads_report.py --start 2026-10-06 --end 2026-11-04 [--no-instagram]

出力: threads/report_YYYYMMDD.md

結論は自動で出さない。「継続する／投稿方法を直して継続する／優先度を下げる」を
人が判断するための数値と根拠を、4つの層（認知・エンゲージメント・プロフィールへの関心・
問い合わせ/予約）に分けて並べる。

数値は投稿ごとの「7日時点」を優先し、無ければ「24時間時点」、それも無ければ「最新」を使う。
どれを使ったかは表に出す（経過時間がそろっていない比較を見分けられるように）。
30投稿前後なので、群ごとの差は「傾向」として読む（統計的な有意差は出ない）。
"""

from __future__ import annotations

import argparse
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import mean

from load_env import load_from_zshrc
load_from_zshrc()

import threads_store as store  # noqa: E402
from threads_plan import parse_dt  # noqa: E402

JST = timezone(timedelta(hours=9))
METRICS = ["views", "likes", "replies", "reposts", "quotes", "shares"]


def pick_metrics(r: dict) -> tuple:
    for key, label in (("指標_7d", "7d"), ("指標_24h", "24h"), ("指標_最新", "最新")):
        m = store.loads(r.get(key, ""))
        if m:
            return m, label
    return {}, "なし"


def _num(v) -> float:
    return float(v) if isinstance(v, (int, float)) else 0.0


def _avg(rows: list, key: str) -> str:
    vals = [_num(r["_m"].get(key)) for r in rows if key in r["_m"]]
    return f"{mean(vals):.1f}" if vals else "—"


def _int(s) -> int:
    try:
        return int(str(s).strip() or 0)
    except ValueError:
        return 0


def group_table(title: str, rows: list, key_fn) -> list:
    groups = defaultdict(list)
    for r in rows:
        for k in key_fn(r):
            groups[k].append(r)
    out = [f"### {title}", "",
           "| 区分 | 件数 | views | likes | replies | reposts | quotes | 問い合わせ |",
           "|---|---|---|---|---|---|---|---|"]
    for k in sorted(groups, key=lambda k: -len(groups[k])):
        g = groups[k]
        out.append(f"| {k} | {len(g)} | {_avg(g, 'views')} | {_avg(g, 'likes')} | "
                   f"{_avg(g, 'replies')} | {_avg(g, 'reposts')} | {_avg(g, 'quotes')} | "
                   f"{sum(_int(r.get('問い合わせ件数')) for r in g)} |")
    return out + [""]


def flag_table(rows: list) -> list:
    out = ["### 属性あり／なしの比較", "",
           "| 属性 | あり件数 | あり views | なし views | あり replies | なし replies | あり 問い合わせ | なし 問い合わせ |",
           "|---|---|---|---|---|---|---|---|"]
    for flag in ["地域", "悩み", "問いかけ", "CTA", "空き", "価格"]:
        yes = [r for r in rows if flag in r.get("属性", "").split(",")]
        no = [r for r in rows if r not in yes]
        out.append(f"| {flag} | {len(yes)} | {_avg(yes, 'views')} | {_avg(no, 'views')} | "
                   f"{_avg(yes, 'replies')} | {_avg(no, 'replies')} | "
                   f"{sum(_int(r.get('問い合わせ件数')) for r in yes)} | "
                   f"{sum(_int(r.get('問い合わせ件数')) for r in no)} |")
    return out + [""]


def instagram_section(start: date, end: date) -> list:
    """同期間の Instagram 投稿の数値（既存の取得処理を流用・読み取りのみ）。"""
    try:
        from get_recent_insights import fetch_recent_posts, fetch_insights
    except Exception as e:
        return [f"Instagram の取得処理を読み込めません: {e}", ""]
    posts = [p for p in fetch_recent_posts(100)
             if start.isoformat() <= p.get("timestamp", "")[:10] <= end.isoformat()]
    if not posts:
        return ["同期間の Instagram 投稿を取得できませんでした（トークン・期間を確認）", ""]
    rows = []
    for p in posts:
        ins = fetch_insights(p["id"], p.get("media_type"))
        rows.append({"likes": p.get("like_count", 0), "comments": p.get("comments_count", 0), **ins})

    def a(k):
        vals = [_num(r.get(k)) for r in rows if k in r]
        return f"{mean(vals):.1f}" if vals else "—"
    return [f"同期間の Instagram 投稿: {len(rows)} 件（投稿あたり平均）", "",
            "| 層 | 指標 | Instagram |", "|---|---|---|",
            f"| 認知 | reach / views | {a('reach')} / {a('views')} |",
            f"| エンゲージメント | likes / comments / saved / shares | "
            f"{a('likes')} / {a('comments')} / {a('saved')} / {a('shares')} |",
            f"| プロフィールへの関心 | profile_visits / follows | {a('profile_visits')} / {a('follows')} |",
            "",
            "※ Instagram の reach（届いた人数）と Threads の views（表示回数）は定義が違うので、"
            "倍率で優劣を決めない。各層の中で「どちらが伸びたか・どれだけの手間で」を見る。", ""]


def build_report(rows: list, daily: list, start: date, end: date, ig_lines: list) -> str:
    in_range = [r for r in rows if (parse_dt(r.get("予定日時", "")) or datetime.min.replace(tzinfo=JST)).date() >= start
                and (parse_dt(r.get("予定日時", "")) or datetime.max.replace(tzinfo=JST)).date() <= end]
    posted = [r for r in in_range if r.get("ステータス") == store.ST_POSTED]
    failed = [r for r in in_range if r.get("ステータス", "").startswith((store.ST_ERROR_PREFIX, store.ST_HOLD_PREFIX))]
    for r in posted:
        r["_m"], r["_basis"] = pick_metrics(r)
    basis = defaultdict(int)
    for r in posted:
        basis[r["_basis"]] += 1
    missing = sorted({k for r in posted for k in r["_m"].get("_missing", [])})
    edited = [r for r in posted if r.get("修正あり") == "Y"]
    inquiries = sum(_int(r.get("問い合わせ件数")) for r in posted)

    d_in = [d for d in daily if start.isoformat() <= d.get("日付", "") <= end.isoformat()]
    followers = [(_int(d.get("followers_count")), d["日付"]) for d in d_in if d.get("followers_count")]
    f_change = (f"{followers[0][0]} → {followers[-1][0]}（{followers[-1][0] - followers[0][0]:+d}）"
                if len(followers) >= 2 else "記録不足")
    profile_views = sum(_int(d.get("profile_views")) for d in d_in)
    clicks = defaultdict(int)
    for d in d_in:
        for url, n in store.loads(d.get("clicks", "")).items():
            clicks[url] += _int(n)
    minutes = sum(_int(d.get("作業時間_分")) for d in d_in)

    L = [f"# Threads 1か月実験レポート（{start} 〜 {end}）", "",
         f"作成: {datetime.now(JST).strftime('%Y/%m/%d %H:%M')}", "",
         "## 1. 全体", "",
         f"- 予定 {len(in_range)} 件 / 投稿済み {len(posted)} 件 / 失敗・保留 {len(failed)} 件"
         f"（投稿失敗率 {len(failed) / len(in_range):.0%}）" if in_range else "- 予定なし",
         f"- 数値の基準: " + "、".join(f"{k} {v}件" for k, v in basis.items()),
         f"- 取得できなかった指標: {', '.join(missing) or 'なし'}"
         "（投稿単位の views / shares は公式に開発中と表記）",
         f"- 自動生成文の修正率: {len(edited)}/{len(posted)}"
         + (f"（{len(edited) / len(posted):.0%}）" if posted else ""),
         f"- 運用の作業時間（手入力合計）: {minutes} 分", "",
         "## 2. 4つの層", "",
         "| 層 | 指標 | Threads |", "|---|---|---|",
         f"| 認知 | 投稿あたり views | {_avg(posted, 'views')} |",
         f"| エンゲージメント | 投稿あたり likes / replies / reposts / quotes | "
         f"{_avg(posted, 'likes')} / {_avg(posted, 'replies')} / {_avg(posted, 'reposts')} / {_avg(posted, 'quotes')} |",
         f"| プロフィールへの関心 | プロフィール閲覧（期間合計） / フォロワー推移 / リンククリック | "
         f"{profile_views} / {f_change} / {sum(clicks.values())} |",
         f"| 問い合わせ・予約 | 「Threadsを見て」（手入力） | {inquiries} 件 |", ""]
    L += group_table("投稿タイプ別", posted, lambda r: [r.get("型") or "不明"])
    L += group_table("時間枠別（予定）", posted, lambda r: [r.get("時間枠") or "不明"])
    L += group_table("実際の投稿時刻（時）別", posted,
                     lambda r: [f"{parse_dt(r['投稿日時_実際']).hour}時台"] if parse_dt(r.get("投稿日時_実際", "")) else ["不明"])
    L += group_table("メディア別（実際）", posted, lambda r: [(r.get("投稿メディア_実際") or "不明").split("（")[0]])
    L += group_table("トピック別", posted, lambda r: [r.get("topic_tag") or "なし"])
    L += flag_table(posted)
    L += ["※ 時間枠の比較は、型・メディア・曜日が枠ごとに完全にはそろっていない。"
          "差が小さい場合は「時間の効果」と断定しない。", ""]

    L += ["## 3. 問い合わせ・予約につながった投稿", ""]
    hits = [r for r in posted if _int(r.get("問い合わせ件数")) > 0]
    L += [f"- {r['予定日時']} [{r.get('型')}] {r.get('Threads_URL', '')} — {r.get('問い合わせ件数')} 件" for r in hits] or ["- なし（または未記入）"]
    L += ["", "## 4. 反応の大きかった投稿（replies + reposts + quotes 上位5）", ""]
    top = sorted(posted, key=lambda r: -(_num(r["_m"].get("replies")) + _num(r["_m"].get("reposts")) + _num(r["_m"].get("quotes"))))[:5]
    L += [f"- {r['予定日時']} [{r.get('型')}] {r.get('属性')} views={r['_m'].get('views', '—')} "
          f"replies={r['_m'].get('replies', '—')} {r.get('Threads_URL', '')}" for r in top] or ["- なし"]
    L += ["", "## 5. Instagram との比較", ""] + ig_lines
    L += ["## 6. 判断材料（結論は人が決める）", "",
          "| 選択肢 | この結果なら支持される |", "|---|---|",
          "| 継続する | 問い合わせが1件以上ある、またはフォロワー・プロフィール閲覧が週ごとに増えており、作業時間が許容範囲 |",
          "| 投稿方法を直して継続 | 特定の型・時間枠・属性だけ明らかに反応が良い／修正率が高く生成ルールの手直しで改善できそう |",
          "| 優先度を下げる | 問い合わせ0件で、views・フォロワーもほぼ横ばい。かつ同じ手間を Instagram（リール等）に回した方が効果が見込める |",
          "",
          "確認すべき問い:",
          "1. Threads 経由の問い合わせ・予約は何件あったか（手入力の記録漏れはないか）",
          "2. 認知（views）は伸びたが来店につながらなかったのか、そもそも届いていないのか",
          "3. どの型・属性（地域名・悩み・問いかけ・空き）が反応と関係していそうか",
          "4. 生成文の修正率と作業時間は、続けられる水準か", ""]
    return "\n".join(L)


def main():
    parser = argparse.ArgumentParser(description="Threads 1か月実験のレポート")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--no-instagram", action="store_true")
    parser.add_argument("--out")
    args = parser.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    rows = [r for _, r in store.open_posts().rows()]
    try:
        daily = [d for _, d in store.open_daily().rows()]
    except RuntimeError:
        daily = []
    ig = ["（--no-instagram のため省略）", ""] if args.no_instagram else instagram_section(start, end)
    text = build_report(rows, daily, start, end, ig)
    out = args.out or os.path.join("threads", f"report_{datetime.now(JST).strftime('%Y%m%d')}.md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write(text)
    print(f"✅ {out} を作成しました")


if __name__ == "__main__":
    main()
