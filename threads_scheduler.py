"""Threads の定時投稿とインサイト記録（GitHub Actions: .github/workflows/threads.yml）。2026-10 追加。

  python3 threads_scheduler.py post [--dry-run]       # 予定時刻を過ぎた「承認済み」を1件投稿
  python3 threads_scheduler.py insights [--dry-run]   # 投稿別とアカウント日次の数値を記録

Instagram の post_scheduler.py とは独立している（シートの1枚目にも触れない）。
THREADS_ACCESS_TOKEN が未設定なら何もせず終了する（セットアップ前に動いても失敗通知を出さない）。

二重投稿対策（post_scheduler.py と同じ考え方）:
  - 1回の起動で投稿するのは最大1件。JSTの同じ日にすでに投稿済みなら何もしない
  - 公開に成功したら、真っ先にステータスを「投稿済み」にする。その後の
    permalink 取得などが失敗しても「エラー：」は書かない（書くと再投稿される）
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

from load_env import load_from_zshrc
load_from_zshrc()

import threads_api as api  # noqa: E402
import threads_store as store  # noqa: E402
from threads_plan import AVAILABILITY_RE, parse_dt, parse_media_spec  # noqa: E402

JST = timezone(timedelta(hours=9))
# 予定時刻からこれ以上遅れた行は自動では出さない（朝枠の投稿が翌日に出るなどを防ぐ）
MAX_DELAY = timedelta(hours=6)
# 7日時点の数値を取り終えた後も、この日数までは「最新」を更新し続ける
TRACK_DAYS = 14


def _notify(message: str):
    try:
        from line_notify import send_line_message
        send_line_message(message)
    except Exception as e:  # 通知の失敗で処理を止めない
        print(f"LINE通知に失敗: {e}")


def _enabled() -> bool:
    if not (os.getenv("THREADS_ACCESS_TOKEN") and os.getenv("THREADS_USER_ID")):
        print("THREADS_ACCESS_TOKEN / THREADS_USER_ID が未設定のため Threads 処理をスキップします")
        return False
    return True


# ── メディアの解決 ───────────────────────────────────

def resolve_media(ig_id: str, spec: str) -> list:
    """元 Instagram 投稿から、投稿直前に media_url を取り直す。

    Instagram の media_url は署名つきで期限があるため、保存せず毎回取得する。
    返り値は threads_api.post_thread に渡す [{"type", "url"}]。
    """
    kind, idx = parse_media_spec(spec)
    if kind == "text":
        return []
    from instagram_api import API_BASE as IG_API_BASE
    res = requests.get(
        f"{IG_API_BASE}/{ig_id}",
        params={"fields": "media_type,media_url,thumbnail_url,children{media_type,media_url}",
                "access_token": os.getenv("INSTAGRAM_ACCESS_TOKEN")},
        timeout=30)
    data = res.json()
    if "error" in data:
        raise RuntimeError(f"Instagram メディア取得失敗: {data['error'].get('message')}")

    def one(item):
        if item.get("media_type") == "VIDEO":
            return {"type": "VIDEO", "url": item["media_url"]}
        return {"type": "IMAGE", "url": item["media_url"]}

    if kind == "thumbnail":
        url = data.get("thumbnail_url") or (data.get("media_url") if data.get("media_type") == "IMAGE" else None)
        if not url:
            raise RuntimeError("表紙画像（thumbnail_url）が取得できません")
        return [{"type": "IMAGE", "url": url}]
    children = (data.get("children") or {}).get("data", [])
    if kind == "carousel":
        picked = [children[i] for i in idx if i < len(children)]
        if len(picked) < 2:
            raise RuntimeError(f"カルーセルの子メディアが足りません（指定 {idx} / 実際 {len(children)}枚）")
        return [one(c) for c in picked]
    # image / video: 単体投稿ならそれ自体、カルーセルなら1枚目
    item = children[0] if children else data
    m = one(item)
    if kind == "image" and m["type"] != "IMAGE":
        url = data.get("thumbnail_url")
        if not url:
            raise RuntimeError("画像指定ですが元投稿が動画で、表紙画像も取れません")
        m = {"type": "IMAGE", "url": url}
    return [m]


def media_label(media: list) -> str:
    if not media:
        return "text"
    if len(media) > 1:
        return f"carousel({len(media)})"
    return media[0]["type"].lower()


# ── post ─────────────────────────────────────────────

def pick_row(rows: list, now: datetime) -> tuple:
    """投稿する行を1つ選ぶ。(行番号, レコード, 理由) を返す。対象が無ければ (None, None, 理由)。"""
    today = now.date()
    for _, r in rows:
        if r.get("ステータス") == store.ST_POSTED:
            posted = parse_dt(r.get("投稿日時_実際", ""))
            if posted and posted.date() == today:
                return None, None, f"本日（{today}）はすでに投稿済みです（1日1投稿）"
    candidates = []
    for row, r in rows:
        st = r.get("ステータス", "")
        if st != store.ST_APPROVED and not st.startswith(store.ST_ERROR_PREFIX):
            continue
        dt = parse_dt(r.get("予定日時", ""))
        if not dt or dt > now:
            continue
        if dt.date() != today or now - dt > MAX_DELAY:
            continue  # 古い行は自動で出さない（日付と時間枠の実験条件が崩れるため）
        candidates.append((dt, row, r))
    if not candidates:
        return None, None, "投稿対象の行はありません"
    candidates.sort(key=lambda c: c[0])
    _, row, r = candidates[0]
    return row, r, ""


def guard(r: dict, rows: list) -> str:
    """投稿前の最終チェック。問題があれば理由を返す。"""
    text = (r.get("本文") or "").strip()
    if not text:
        return "本文が空です"
    if api.text_length(text) > api.TEXT_LIMIT:
        return f"本文が{api.TEXT_LIMIT}字を超えています"
    if "AMRTA" in text.upper():
        return "本文にサロン名があります"
    if AVAILABILITY_RE.search(text) and not (r.get("空き情報") or "").strip():
        return "空き状況に触れていますが「空き情報」欄が空です（事実確認できない空きは書かない）"
    for _, other in rows:
        if (other is not r and other.get("ステータス") == store.ST_POSTED
                and other.get("元IG投稿ID") == r.get("元IG投稿ID")):
            return f"元IG投稿 {r.get('元IG投稿ID')} は実験中に投稿済みです"
    return ""


def cmd_post(dry_run: bool) -> int:
    if not _enabled():
        return 0
    try:
        tab = store.open_posts(create=False)
    except RuntimeError as e:
        print(e)
        return 0
    rows = tab.rows()
    now = datetime.now(JST)
    row, r, reason = pick_row(rows, now)
    if row is None:
        print(reason)
        return 0
    print(f"行{row}: {r['予定日時']} [{r.get('型')}] topic={r.get('topic_tag')} media={r.get('メディア指定')}")

    problem = guard(r, rows)
    if problem:
        print(f"行{row}: 投稿しません — {problem}")
        if not dry_run:
            # 「エラー：」にすると次の起動で再試行され同じ通知が続くので、人が直すまで止める
            tab.update(row, {"ステータス": store.ST_HOLD_PREFIX + problem[:80], "エラー内容": problem})
            _notify(f"⚠️ Threads 投稿を止めました（行{row} {r['予定日時']}）\n{problem}")
        return 1

    media_note = ""
    try:
        media = resolve_media(r["元IG投稿ID"], r.get("メディア指定", "text"))
    except Exception as e:
        # 画像が取れなくても実験を止めない。テキストのみで出し、記録に残す
        media, media_note = [], f"メディア取得失敗→テキストのみ: {e}"
        print(f"  ⚠ {media_note}")

    if dry_run:
        print(f"  [dry-run] 投稿内容（{api.text_length(r['本文'])}字・{media_label(media)}）:\n{r['本文']}")
        return 0

    try:
        thread_id = api.post_thread(r["本文"].strip(), media, r.get("topic_tag", "").strip())
    except Exception as e:
        msg = str(e)
        print(f"行{row}: 投稿失敗 → {msg}")
        try:
            tab.update(row, {"ステータス": store.ST_ERROR_PREFIX + msg[:80], "エラー内容": msg[:500]})
        except Exception as e2:
            print(f"  ステータス記録にも失敗: {e2}")
        _notify(f"❌ Threads 投稿失敗（{r['予定日時']}）\n{msg[:300]}")
        return 1

    # ここから先は失敗しても「エラー：」を書かない（再投稿を防ぐ）
    posted_at = datetime.now(JST).strftime("%Y/%m/%d %H:%M")
    edited = "Y" if _norm(r.get("本文")) != _norm(r.get("本文_生成時")) else "N"
    try:
        tab.update(row, {"ステータス": store.ST_POSTED, "Threads投稿ID": thread_id,
                         "投稿日時_実際": posted_at, "修正あり": edited,
                         "投稿メディア_実際": media_label(media) + (f"（{media_note}）" if media_note else ""),
                         "エラー内容": ""})
    except Exception as e:
        print(f"⚠ 投稿は成功しましたが記録に失敗: {e}")
        _notify(f"⚠️ Threads 投稿は成功、シート記録に失敗（行{row}）。"
                f"ステータスを手で「投稿済み」にしてください。ID={thread_id}")
        return 1
    try:
        info = api.get_post(thread_id)
        tab.update(row, {"Threads_URL": info.get("permalink", "")})
    except Exception as e:
        print(f"  permalink の取得に失敗（投稿は成功）: {e}")
    print(f"✅ Threads 投稿完了: {thread_id}")
    _notify(f"🧵 Threads に投稿しました（{posted_at}・{r.get('型')}）")
    return 0


def _norm(s: str) -> str:
    return "".join((s or "").split())


# ── insights ─────────────────────────────────────────

def cmd_insights(dry_run: bool) -> int:
    if not _enabled():
        return 0
    try:
        tab = store.open_posts(create=False)
    except RuntimeError as e:
        print(e)
        return 0
    now = datetime.now(JST)
    stamp = now.strftime("%Y/%m/%d %H:%M")
    failures = 0
    for row, r in tab.rows():
        if r.get("ステータス") != store.ST_POSTED or not r.get("Threads投稿ID"):
            continue
        posted = parse_dt(r.get("投稿日時_実際", ""))
        if not posted or now - posted > timedelta(days=TRACK_DAYS):
            continue
        try:
            m = api.get_media_insights(r["Threads投稿ID"])
        except Exception as e:
            failures += 1
            print(f"行{row}: インサイト取得失敗 {e}")
            continue
        fields = {"指標_最新": store.dumps(m), "指標_取得日時": stamp}
        age = now - posted
        if age >= timedelta(hours=24) and not r.get("指標_24h"):
            fields["指標_24h"] = store.dumps({**m, "_age_h": round(age.total_seconds() / 3600)})
        if age >= timedelta(days=7) and not r.get("指標_7d"):
            fields["指標_7d"] = store.dumps({**m, "_age_h": round(age.total_seconds() / 3600)})
        print(f"行{row}: {m}")
        if not dry_run:
            tab.update(row, fields)

    # アカウント日次（前日分）。followers_count は現在値しか取れないので毎日記録して増減を見る
    yesterday = (now - timedelta(days=1)).date()
    since = int(datetime(yesterday.year, yesterday.month, yesterday.day, tzinfo=JST).timestamp())
    until = since + 86400
    try:
        u = api.get_user_insights(since, until)
    except Exception as e:
        print(f"アカウントのインサイト取得失敗: {e}")
        _notify(f"⚠️ Threads インサイト取得失敗（トークン期限切れの可能性）\n{str(e)[:200]}")
        return 1
    views = u.get("views")
    profile_views = sum(v["value"] for v in views) if isinstance(views, list) else views
    rec = {"日付": yesterday.isoformat(), "followers_count": u.get("followers_count", ""),
           "profile_views": profile_views if profile_views is not None else "",
           "likes": u.get("likes", ""), "replies": u.get("replies", ""),
           "reposts": u.get("reposts", ""), "quotes": u.get("quotes", ""),
           "clicks": store.dumps(u.get("clicks") or {}), "取得日時": stamp}
    print(f"アカウント {yesterday}: {rec}")
    if not dry_run:
        daily = store.open_daily(create=True)
        if yesterday.isoformat() not in {d.get("日付") for _, d in daily.rows()}:
            daily.append([rec])
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description="Threads の定時投稿とインサイト記録")
    parser.add_argument("cmd", choices=["post", "insights"])
    parser.add_argument("--dry-run", action="store_true", help="API投稿・シート書き込みをしない")
    args = parser.parse_args()
    sys.exit(cmd_post(args.dry_run) if args.cmd == "post" else cmd_insights(args.dry_run))


if __name__ == "__main__":
    main()
