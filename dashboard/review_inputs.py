"""
review_inputs.py
────────────────────────────────────────────────────
ダッシュボードの5つのセクション（先週のまとめ／振り返り／今週の投稿と狙い／LP／投稿の成績）に
使う数字を、データのスナップショット（dashboard_data.json）から1回だけ計算する。

画面（dashboard/src）はここで計算した `derived` を表示するだけにする。週次タスクの Claude も
同じ数字を `digest` で読む。画面と Claude が別々に計算すると、言っていることがずれるため。

使い方（週次タスクから）:
  /usr/bin/python3 dashboard/review_inputs.py digest            # 振り返りを書く前に読む
  /usr/bin/python3 dashboard/review_inputs.py check [下書き]    # 振り返りの下書きの機械チェック
                                                                 # （省略時 dashboard/data/review_draft.json）

判定の考え方:
  - 判定は投稿から MATURE_DAYS 日たってから。それより新しい投稿は「集計中」
  - 「いつもの範囲」は直近の確定した USUAL_POSTS 本（週の数字は USUAL_WEEKS 週）の真ん中半分。
    上回れば high、下回れば low。小さな数を%で比べると暴れるので、増減の%は出さない
  - 保存とプロフィールは率（÷届いた人）で比べる

⚠ /usr/bin/python3 は 3.9。`X | None` の注釈は from __future__ で文字列化している。
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import sys
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent
WORKTREE_ROOT = DASHBOARD_DIR.parent
# credentials.json などは gitignore のため worktree に無いことがある → main repo まで探す
REPO_CANDIDATES = [WORKTREE_ROOT, Path.home() / "Desktop" / "美喜のinstagram"]
DATA_FILE = DASHBOARD_DIR / "data" / "dashboard_data.json"
REVIEWS_DIR = DASHBOARD_DIR / "reviews"
DRAFT_FILE = DASHBOARD_DIR / "data" / "review_draft.json"
JST = timezone(timedelta(hours=9))

sys.path.insert(0, str(WORKTREE_ROOT))
# 変えてよい項目と狙う数字の正は review_post.py（同じ一覧を2か所に持たない）
from review_post import (TRIAL_LEVERS, TRIAL_METRICS, TRIAL_NONE, TRIAL_TAG_RE,  # noqa: E402
                         fixed_items_in)

# 判定は投稿からこの日数がたってから。土曜朝の週次更新で、前の週の月・木・金の3本がそろって判定できる
MATURE_DAYS = 7
# 「いつもの範囲」に使う数（投稿は直近の確定した本数、週は直近の週数）
USUAL_POSTS = 12
USUAL_WEEKS = 12
# これより少ないと範囲を出さない
USUAL_MIN_N = 4
# 画面の「投稿の成績」に出す本数
RECENT_POSTS = 9
# 「人の修正」を数える期間（週）
EDIT_WEEKS = 4
# LP の内訳を合計する期間（週）。週2〜5件と少ないので週ごとには分けない
LP_BREAKDOWN_WEEKS = 4
# 投稿・修正の記録を読む範囲（これより古い投稿は画面に出ない）
RECORD_WEEKS = 20
# 振り返りの「次に試すこと」の上限と、同じ施策に「もう一度」を出せる回数
MAX_NEXT = 3
MAX_AGAIN = 2
DECISIONS = {"standard": "標準にする", "again": "もう一度", "stop": "やめる"}
# いつもの範囲との比較の呼び方（画面と digest で同じ言葉を使う）
VERDICTS = {"high": "多い", "usual": "いつもどおり", "low": "少ない"}
# 標準の出どころ。edits（ご本人の修正から取り入れたもの）は2本以上の同じ種類の修正か、
# 依頼の文に「今後も」などがあった時だけ（1回きりの事情を全部の投稿に広げないため）
STANDARD_SOURCES = {"practice": "これまでの型", "result": "結果から", "edits": "修正から"}
EDITS_MIN_POSTS = 2
FEED_TYPES = ("CAROUSEL_ALBUM", "IMAGE")
# シートで「まだ投稿されていない」予定とみなすステータス
UPCOMING_STATUSES = ("確認待ち", "承認済み", "未投稿", "手動投稿待ち")
# このうち、校閲（review_post.py）を通っているはずのステータス。前回版が無ければ
# 週次タスクが登録まで進んで校閲の途中で止まった名残（手動投稿のリールは対象外）
REVIEW_NEEDED_STATUSES = ("確認待ち", "承認済み", "未投稿")
POSTED_STATUS = "投稿済み"
# trial.metric → 投稿の数字のキー
METRIC_FIELDS = {"reach": "reach", "saved": "saved_rate",
                 "profile_visits": "pv_rate", "follows": "follows"}
# 振り返りの公開される欄に、修正依頼の文がこの文字数以上そのまま入っていたら止める
# （依頼の文は digest にだけ出し、公開ページには載せない）
LEAK_MIN_CHARS = 12
CAPTION_KEY_CHARS = 40

SCHEMA_HELP = """\
振り返りの下書き（dashboard/data/review_draft.json）の形:
{
  "written_on": "YYYY-MM-DD",            # 書いた日（週次タスクの実行日）
  "summary": "2〜3文。数字を入れる。修正依頼の文はそのまま書かない（公開ページに出る）",
  "verdicts": [                           # 判定（判定できる投稿がある施策だけ）
    {"tag": "cover-question", "decision": "standard | again | stop",
     "evidence": "数字の入った根拠（例: 11/2 保存率1.9%・いつも0.6〜1.1%）", "note": "任意"}
  ],
  "standards": [                          # いまの標準（毎回入れる型）。前回の分も書き写す
    {"tag": "save-list", "what": "保存用のリストを1枚入れる", "since": "YYYY-MM-DD",
     "source": "practice | result | edits",
     "based_on": ["YYYY-MM-DD-HHMM", "..."],  # source=edits のとき2本以上（"explicit": true なら1本で可）
     "explicit": false}
  ],
  "stopped": [{"tag": "...", "what": "...", "since": "YYYY-MM-DD"}],   # やめたこと。前回の分も書き写す
  "next": [                               # 次に試すこと（1〜3個）。投稿1本につき1つ割り当てる
    {"tag": "cover-question", "lever": "cover", "what": "表紙を疑問形にする",
     "metric": "saved", "why": "数字の入った根拠"}
  ]
}"""


# ───────── 文字と日時の小道具 ─────────

def _norm(text) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", str(text or "")))


def caption_key(text) -> str:
    """キャプションの冒頭（空白・改行を除いた先頭40字）の指紋。シートと Instagram の投稿を結ぶ鍵。

    CLAUDE.md の「1〜2行目は毎回固有の一文」のルールで、投稿ごとに違う値になる。
    キャプションの本文を公開ページに載せないよう、文そのものではなく指紋で持つ。
    """
    head = _norm(text)[:CAPTION_KEY_CHARS]
    return hashlib.sha1(head.encode("utf-8")).hexdigest()[:12] if head else ""


def caption_sig(caption, hashtags="") -> str:
    """投稿されるキャプション（本文＋ハッシュタグ）の指紋。空白・改行は無視する。

    post_scheduler.build_caption は「本文 + 空行 + ハッシュタグ」で投稿するので、
    シートの D列+E列・content の caption+hashtags・Instagram のキャプションが同じ値になる。
    違えば、どこかで直接書き換えられている。
    """
    body = _norm(caption) + _norm(hashtags)
    return hashlib.sha1(body.encode("utf-8")).hexdigest()[:12] if body else ""


def _parse_ts(value):
    """Instagram の timestamp（+0000）・ISO 文字列・シートの日時を JST の datetime にする。"""
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y/%m/%d %H:%M"):
        try:
            d = datetime.strptime(text, fmt)
            return d.astimezone(JST) if d.tzinfo else d.replace(tzinfo=JST)
        except ValueError:
            pass
    try:
        d = datetime.fromisoformat(text)
    except ValueError:
        return None
    return d.astimezone(JST) if d.tzinfo else d.replace(tzinfo=JST)


def _monday(d: datetime) -> str:
    return (d - timedelta(days=d.weekday())).strftime("%Y-%m-%d")


def _quantile(sorted_vals: list, q: float):
    pos = (len(sorted_vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def usual_range(values) -> dict | None:
    """「いつもの範囲」（真ん中半分）。数が USUAL_MIN_N 未満なら None。"""
    vals = sorted(v for v in values if v is not None)
    if len(vals) < USUAL_MIN_N:
        return None
    return {"low": _quantile(vals, 0.25), "median": _quantile(vals, 0.5),
            "high": _quantile(vals, 0.75), "n": len(vals)}


def compare(value, usual: dict | None) -> str | None:
    if value is None or usual is None:
        return None
    if value > usual["high"]:
        return "high"
    if value < usual["low"]:
        return "low"
    return "usual"


def _median(values):
    vals = sorted(v for v in values if v is not None)
    return _quantile(vals, 0.5) if vals else None


def _sum(values):
    vals = [v for v in values if v is not None]
    return sum(vals) if vals else None


_GREETING = re.compile(r"^(miki|MIKI|ミキ|美喜)(です|だよ)?[。｡\s]*$|閲覧ありがとう|ご覧いただき")


def first_sentence(caption) -> str:
    """キャプションから、挨拶・装飾を飛ばした意味のある最初の一文を取る（投稿一覧の見出し用）。"""
    text = re.sub(r"@[\w.]+", " ", str(caption or ""))
    text = re.sub(r"[⁠-⁤​-‍﻿]", "", text)
    text = re.sub(r"[:*・=~〜\-]{2,}[:*・=~〜\-\s]*", " ", text)
    segs = []
    for s in re.split(r"[。｡\n]", text):
        s = re.sub(r"^[\s⭐☆★~〜・:*.#️]+|[\s⭐☆★~〜・:*.#️]+$", "", s).strip()
        if len(re.findall(r"[ぁ-んァ-ヶ一-龠々a-zA-Z0-9]", s)) >= 6:
            segs.append(s)
    head = next((s for s in segs if len(s) >= 8 and not _GREETING.search(s)), segs[0] if segs else "")
    if len(head) > 42:
        return head[:42] + "…"
    return head or "(キャプションなし)"


# ───────── 読み込み（fetch_dashboard_data.py から呼ぶ） ─────────

@contextmanager
def _cwd(path: Path):
    prev = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


def load_sheet_rows():
    """シートの全行から、ダッシュボードに要る値だけを返す。戻り値 (rows, error)。

    投稿メモ（F列）とキャプション本文は公開ページに載せない（指紋と冒頭の鍵だけ）。
    読めなくても週次更新は止めない（LP と同じ扱い）。
    """
    root = next((p for p in REPO_CANDIDATES if (p / "credentials.json").exists()), None)
    if root is None:
        return None, "credentials.json が見つかりません"
    try:
        sys.path.insert(0, str(root))
        from sheet_client import get_all_values_with_retry, open_sheet
        from check_week_slots import parse_sheet_datetime
        with _cwd(root):  # open_sheet は credentials.json をカレントから読む
            values = get_all_values_with_retry(open_sheet())
    except Exception as e:  # pragma: no cover - ネットワーク/認証エラー
        return None, f"シートを読めませんでした: {str(e)[:120]}"
    if not values or not values[0] or values[0][0].strip() != "投稿日時":
        return None, "シートのヘッダーが想定と違います（A1が『投稿日時』でない）"

    rows = []
    for r in values[1:]:
        if not r or not r[0].strip():
            continue
        dt = parse_sheet_datetime(r[0])
        if dt is None:
            continue

        def cell(i: int) -> str:
            return r[i].strip() if len(r) > i else ""

        rows.append({
            "slug": dt.strftime("%Y-%m-%d-%H%M"),
            "post_datetime": dt.strftime("%Y/%m/%d %H:%M"),
            "menu": cell(1),
            "status": cell(6),
            "preview_url": cell(7),
            "caption_key": caption_key(cell(3)),
            "caption_sig": caption_sig(cell(3), cell(4)),
        })
    return rows, None


def _record_summary(content: dict | None, hist: dict | None) -> dict:
    """前回版と修正の記録を、公開ページに載せてよい形にまとめる（修正依頼の文は入れない）。"""
    content = content or {}
    slides = [s for s in (content.get("slides") or []) if isinstance(s, dict)]
    first = slides[0] if slides else {}
    title = first.get("title") or first.get("phrase") or ""
    hist = hist or {}
    base = hist.get("base") or {}
    trial = content.get("trial")
    return {
        "cover_title": re.sub(r"\s*\n\s*", "", str(title)).strip(),
        "post_style": content.get("post_style") or "standard",
        "trial": trial if isinstance(trial, dict) else None,
        "caption_sig": caption_sig(content.get("caption"), content.get("hashtags")) if content else "",
        "base_origin": base.get("origin"),
        "revisions": [{"at": e.get("at"), "changes": e.get("changes") or []}
                      for e in (hist.get("events") or [])],
    }


def load_records(now: datetime | None = None) -> dict:
    """直近 RECORD_WEEKS 週〜先の枠について、最後に校閲を通った版と修正の記録を読む。"""
    from content_baseline import list_slugs, load_baseline, load_history
    now = now or datetime.now(JST)
    lo = (now - timedelta(weeks=RECORD_WEEKS)).strftime("%Y-%m-%d")
    out = {}
    for slug in list_slugs():
        if slug[:10] < lo:
            continue
        out[slug] = _record_summary(load_baseline(slug), load_history(slug))
    return out


def load_reviews(include_draft: bool = True) -> list:
    """コミット済みの振り返り（dashboard/reviews/*.json）と下書きを、書いた日の順に返す。

    下書きの日付がコミット済みと同じなら下書きを使う（あとから直した方が新しい）。
    """
    found = {}
    for p in sorted(REVIEWS_DIR.glob("*.json")):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(r, dict) and r.get("written_on"):
            found[str(r["written_on"])] = r
    if include_draft and DRAFT_FILE.exists():
        try:
            d = json.loads(DRAFT_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = None
        if isinstance(d, dict) and d.get("written_on"):
            found[str(d["written_on"])] = {**d, "_draft": True}
    return [found[k] for k in sorted(found)]


# ───────── 派生値 ─────────

def _posts(data: dict, now: datetime) -> list:
    """Instagram の投稿を新しい順に並べ、数字・経過日数・いつもの範囲との比較を付ける。"""
    out = []
    for p in data.get("posts") or []:
        t = _parse_ts(p.get("timestamp"))
        if t is None:
            continue
        ins = p.get("insights") or None
        reach = (ins or {}).get("reach")

        def rate(key: str):
            v = (ins or {}).get(key)
            return v / reach if (v is not None and reach) else None

        age = (now - t).total_seconds() / 86400
        out.append({
            "media_id": p.get("media_id"),
            "date": t.isoformat(timespec="minutes"),
            "_t": t,
            "week_start": _monday(t),
            "weekday": t.weekday(),
            "media_type": p.get("media_type"),
            "permalink": p.get("permalink"),
            "theme": p.get("theme"),
            "title": first_sentence(p.get("caption_head")),
            "caption_key": p.get("caption_key") or caption_key(p.get("caption_head")),
            "caption_sig": p.get("caption_sig") or "",
            "has_insights": bool(ins),
            "age_days": round(age, 1),
            "mature": age >= MATURE_DAYS,
            "metrics": {
                "reach": reach,
                "saved": (ins or {}).get("saved"),
                "saved_rate": rate("saved"),
                "profile_visits": (ins or {}).get("profile_visits"),
                "pv_rate": rate("profile_visits"),
                "follows": (ins or {}).get("follows"),
            },
            "usual": {},
            "vs": {},
            "slug": None, "scheduled_at": None, "delay_min": None, "menu": None,
            "trial": None, "cover_title": "", "edits": None,
        })
    out.sort(key=lambda x: x["_t"], reverse=True)

    # いつもの範囲は「その投稿より前の、確定した同じ種類の投稿」から作る
    # （リールはプロフィール閲覧が取れず、届き方もカルーセルと違うので混ぜない）
    for i, p in enumerate(out):
        if not p["has_insights"]:
            continue
        is_feed = p["media_type"] in FEED_TYPES
        pool = [q for q in out[i + 1:]
                if q["has_insights"] and q["mature"] and (q["media_type"] in FEED_TYPES) == is_feed]
        for key in METRIC_FIELDS.values():
            vals = [q["metrics"][key] for q in pool if q["metrics"][key] is not None][:USUAL_POSTS]
            usual = usual_range(vals)
            p["usual"][key] = usual
            p["vs"][key] = compare(p["metrics"][key], usual) if p["mature"] else None
    return out


def _record_view(rec: dict | None, row_sig: str = "", post_sig: str = "") -> dict:
    """1本の投稿について、試すこと・表紙・修正の有無を画面向けにまとめる。"""
    if not rec:
        return {"trial": None, "cover_title": "", "edits": None}
    revs = rec.get("revisions") or []
    labels = list(dict.fromkeys(label for e in revs for label in e.get("changes") or []))
    direct = None
    if post_sig and row_sig and post_sig != row_sig:
        direct = "app"      # 投稿されたキャプションがシートと違う（アプリで書き換えた等）
    elif row_sig and rec.get("caption_sig") and row_sig != rec["caption_sig"]:
        direct = "sheet"    # シートが最後に校閲を通った版と違う（シートで直接編集か、校閲前の作り直し）
    return {
        "trial": rec.get("trial"),
        "cover_title": rec.get("cover_title") or "",
        "edits": {
            "count": len(revs),
            "changes": labels,
            "base_origin": rec.get("base_origin"),
            "last_at": revs[-1].get("at") if revs else None,
            "direct": direct,
        },
    }


def _attach_sheet(posts: list, rows: list, records: dict, now: datetime) -> None:
    """Instagram の投稿にシートの行（枠）を結び、試すこと・修正の記録を付ける。

    キャプションの冒頭で結ぶ。合わなければ（アプリで書き換えた等）予定日時の近さで補う。
    """
    by_key: dict = {}
    for r in rows:
        if r.get("caption_key"):
            by_key.setdefault(r["caption_key"], []).append(r)
    used = set()
    cut = now - timedelta(weeks=RECORD_WEEKS)
    for p in posts:
        if p["_t"] < cut:
            break
        cands = [r for r in by_key.get(p["caption_key"], []) if r["slug"] not in used]
        matched_by = "caption"
        if not cands:
            matched_by = "time"
            cands = [r for r in rows
                     if r["slug"] not in used and r.get("status") == POSTED_STATUS
                     and timedelta(hours=-6) <= p["_t"] - _parse_ts(r["post_datetime"]) <= timedelta(hours=72)]
        if not cands:
            continue
        row = min(cands, key=lambda r: abs(p["_t"] - _parse_ts(r["post_datetime"])))
        used.add(row["slug"])
        p["slug"] = row["slug"]
        p["scheduled_at"] = row["post_datetime"]
        p["delay_min"] = int((p["_t"] - _parse_ts(row["post_datetime"])).total_seconds() // 60)
        p["menu"] = row.get("menu")
        p["matched_by"] = matched_by
        p.update(_record_view(records.get(row["slug"]), row.get("caption_sig") or "", p["caption_sig"]))


def _weeks(data: dict, posts: list) -> list:
    """週ごとの数字（アカウント合計＋その週に出した投稿の保存＋LP）を古い順に。"""
    lp_by_week = {w.get("week_start"): w for w in ((data.get("lp") or {}).get("weeks") or [])}
    posts_by_week: dict = {}
    for p in posts:
        posts_by_week.setdefault(p["week_start"], []).append(p)
    out = []
    for w in sorted(data.get("account_weekly") or [], key=lambda x: x.get("week_start") or ""):
        if w.get("error") or not w.get("week_start"):
            continue
        ws = w["week_start"]
        wp = [p for p in posts_by_week.get(ws, []) if p["has_insights"]]
        saved = sum(p["metrics"]["saved"] or 0 for p in wp) if wp else None
        post_reach = sum(p["metrics"]["reach"] or 0 for p in wp)
        reach, pv = w.get("reach"), w.get("profile_views")
        lp = lp_by_week.get(ws)
        out.append({
            "week_start": ws,
            "partial": bool(w.get("partial")),
            "posts": len(posts_by_week.get(ws, [])),
            "reach": reach,
            "profile_views": pv,
            "pv_rate": pv / reach if (reach and pv is not None) else None,
            "link_taps": w.get("website_clicks"),
            "saved": saved,
            "saved_rate": saved / post_reach if (saved is not None and post_reach) else None,
            "lp_arrivals": lp.get("instagram_sessions") if lp else None,
            "lp_engaged": lp.get("instagram_engaged_sessions") if lp else None,
            "lp_cta_dm": lp.get("instagram_cta_dm") if lp else None,
            "lp_cta_hotpepper": lp.get("instagram_cta_hotpepper") if lp else None,
        })
    return out


# (キー, 表示名, 比べる値, 件数として並べる値)
TILES = (
    ("reach", "届いた人", "reach", None),
    ("saved", "保存", "saved_rate", "saved"),
    ("profile_views", "プロフィールを見た人", "pv_rate", "profile_views"),
    ("lp", "LPに来た人", "lp_arrivals", None),
)


def _summary(weeks: list, data: dict) -> dict | None:
    """確定した先週の4つの数字を、その前の12週の「いつもの範囲」と並べる。"""
    complete = [w for w in weeks if not w["partial"]]
    if not complete:
        return None
    target = complete[-1]
    prior = complete[:-1][-USUAL_WEEKS:]
    tiles = []
    for key, label, field, count_field in TILES:
        value = target.get(field)
        usual = usual_range([w.get(field) for w in prior])
        tiles.append({
            "key": key, "label": label, "is_rate": field.endswith("_rate"),
            "value": value,
            "count": target.get(count_field) if count_field else None,
            "usual": usual,
            "verdict": compare(value, usual),
            "spark": [{"week_start": w["week_start"], "value": w.get(field)}
                      for w in complete[-USUAL_WEEKS:]],
        })
    daily = data.get("account_daily") or []
    return {
        "week_start": target["week_start"],
        "tiles": tiles,
        "current_week": next((w for w in reversed(weeks) if w["partial"]), None),
        "followers": (data.get("account") or {}).get("followers_count"),
        "followers_gain": _sum(d.get("follower_count") for d in daily),
        "followers_days": len(daily),
    }


def _review_view(reviews: list) -> dict:
    """最新の振り返りと、施策ごとの判定の積み上げ（「もう一度」の回数・最後の判定）。"""
    decisions: dict = {}
    for r in reviews:
        for v in r.get("verdicts") or []:
            d = decisions.setdefault(v.get("tag"), {"again": 0, "last": None})
            if v.get("decision") == "again":
                d["again"] += 1
            d["last"] = v.get("decision")
    return {
        "latest": reviews[-1] if reviews else None,
        "history": [{"written_on": r.get("written_on"), "summary": r.get("summary")}
                    for r in reversed(reviews[:-1])][:8],
        "decisions": decisions,
    }


def _trial_stats(posts: list, decisions: dict) -> list:
    """施策（tag）ごとの通算: 試した本数、判定できた本数、いつもとの比較、試さなかった投稿との比較。"""
    groups: dict = {}
    for p in posts:
        t = p.get("trial") or {}
        if t.get("lever") in (None, "", TRIAL_NONE) or not t.get("tag"):
            continue
        groups.setdefault(t["tag"], []).append(p)
    out = []
    for tag, ps in groups.items():
        latest = ps[0]["trial"]
        field = METRIC_FIELDS.get(latest.get("metric"))
        judged = [p for p in ps if p["mature"] and field and p["metrics"].get(field) is not None]
        vs = [p["vs"].get(field) for p in judged]
        others = []
        if judged and field:
            since = min(p["_t"] for p in judged) - timedelta(weeks=4)
            others = [p for p in posts
                      if p["mature"] and p["has_insights"] and p["media_type"] in FEED_TYPES
                      and p["_t"] >= since and (p.get("trial") or {}).get("tag") != tag]
        d = decisions.get(tag) or {}
        out.append({
            "tag": tag,
            "lever": latest.get("lever"),
            "metric": latest.get("metric"),
            "what": latest.get("what"),
            "count": len(ps),
            "judged": len(judged),
            "high": vs.count("high"), "usual": vs.count("usual"), "low": vs.count("low"),
            "median_with": _median(p["metrics"][field] for p in judged) if field else None,
            "median_without": _median(p["metrics"][field] for p in others) if field else None,
            "posts": [p["slug"] for p in ps if p.get("slug")],
            "last_posted": ps[0]["date"],
            "decision": d.get("last"),
            "again": d.get("again", 0),
        })
    out.sort(key=lambda x: x["last_posted"], reverse=True)
    return out


def _edit_stats(rows: list, records: dict, now: datetime) -> dict:
    """直近 EDIT_WEEKS 週の枠のうち、ご本人の修正が入った本数と、よく直された箇所。"""
    lo, hi = now - timedelta(weeks=EDIT_WEEKS), now + timedelta(days=14)
    window = [r for r in rows if lo <= _parse_ts(r["post_datetime"]) <= hi]
    known = [records[r["slug"]] for r in window if r["slug"] in records]
    counter: dict = {}
    for rec in known:
        for e in rec.get("revisions") or []:
            for label in e.get("changes") or []:
                kind = re.sub(r"スライド\d+", "スライド", label)
                counter[kind] = counter.get(kind, 0) + 1
    top = sorted(counter.items(), key=lambda kv: -kv[1])[:6]
    return {
        "weeks": EDIT_WEEKS,
        "slots": len(window),
        "known": len(known),
        "edited": sum(1 for rec in known if rec.get("revisions")),
        "top_changes": [{"label": k, "count": v} for k, v in top],
    }


def unreviewed_upcoming(upcoming: list) -> list:
    """校閲を通った前回版が無い予定の枠（登録まで進んで、校閲の途中で止まった名残）。"""
    return [u for u in upcoming if u.get("needs_review")]


def _upcoming(rows: list, records: dict, now: datetime) -> list:
    """シートの予定行（まだ投稿されていない枠）を、修正後の最新の内容で。"""
    out = []
    for r in rows:
        if r.get("status") not in UPCOMING_STATUSES:
            continue
        dt = _parse_ts(r["post_datetime"])
        if dt < now - timedelta(days=3) or dt > now + timedelta(days=21):
            continue
        rec = records.get(r["slug"])
        out.append({
            "slug": r["slug"],
            "post_datetime": r["post_datetime"],
            "weekday": dt.weekday(),
            "status": r["status"],
            "menu": r.get("menu"),
            "preview_url": r.get("preview_url"),
            # 校閲を通っているはずなのに前回版が無い（画面と digest が警告を出す）
            "needs_review": rec is None and r["status"] in REVIEW_NEEDED_STATUSES,
            **_record_view(rec, r.get("caption_sig") or ""),
        })
    out.sort(key=lambda x: x["post_datetime"])
    return out


def _lp(data: dict, weeks: list) -> dict:
    """LP（予約導線）。Instagram 経由だけを数える（(direct)/(none) に海外の自動アクセスが混ざるため）。"""
    lp = data.get("lp")
    if not lp:
        return {"available": False, "reason": "GA4が未設定か、取得できませんでした"}
    if lp.get("error"):
        return {"available": False, "reason": "GA4の取得に失敗しました"}
    lw = lp.get("weeks") or []
    complete = [w for w in lw if not w.get("partial")]
    recent = complete[-LP_BREAKDOWN_WEEKS:]
    account = {w["week_start"]: w for w in weeks}

    def funnel(ws: list) -> dict:
        return {
            "profile_views": _sum(account.get(w["week_start"], {}).get("profile_views") for w in ws),
            "link_taps": _sum(account.get(w["week_start"], {}).get("link_taps") for w in ws),
            "arrivals": _sum(w.get("instagram_sessions") for w in ws),
            "engaged": _sum(w.get("instagram_engaged_sessions") for w in ws),
            "cta_dm": _sum(w.get("instagram_cta_dm") for w in ws),
            "cta_hotpepper": _sum(w.get("instagram_cta_hotpepper") for w in ws),
            "bounced": _sum(w.get("instagram_hotpepper_bounced") for w in ws),
        }

    devices: dict = {}
    courses: dict = {}
    sources: dict = {}
    new = returning = eng_sec = eng_n = 0
    # 平均滞在は 2026-11 に足した項目。古いスナップショットの週には無いので「0秒」と出さない
    has_engagement = any("instagram_avg_engagement_sec" in w for w in recent)
    for w in recent:
        for k, v in (w.get("instagram_devices") or {}).items():
            devices[k] = devices.get(k, 0) + v
        new += w.get("instagram_new") or 0
        returning += w.get("instagram_returning") or 0
        for c in w.get("instagram_courses") or []:
            acc = courses.setdefault(c["course"], {"course": c["course"], "cta_dm": 0, "cta_hotpepper": 0})
            acc["cta_dm"] += c.get("cta_dm") or 0
            acc["cta_hotpepper"] += c.get("cta_hotpepper") or 0
        for s in w.get("sources") or []:
            acc = sources.setdefault(s["source_medium"], {"source_medium": s["source_medium"],
                                                          "sessions": 0, "engaged_sessions": 0})
            acc["sessions"] += s.get("sessions") or 0
            acc["engaged_sessions"] += s.get("engaged_sessions") or 0
        n = w.get("instagram_sessions") or 0
        eng_sec += (w.get("instagram_avg_engagement_sec") or 0) * n
        eng_n += n

    has_audience = bool(lp.get("audience_available")) and any("instagram_devices" in w for w in recent)
    has_courses = bool(lp.get("courses_available")) and any("instagram_courses" in w for w in recent)
    has_week_sources = any("sources" in w for w in recent)
    sc = lp.get("search_console") or {}
    return {
        "available": True,
        "period_weeks": len(recent),
        "period_start": recent[0]["week_start"] if recent else None,
        "since": lp.get("since"),
        "funnel": funnel(recent),
        "funnel_all": funnel(complete),
        "trend": [{
            "week_start": w["week_start"],
            "partial": bool(w.get("partial")),
            "link_taps": account.get(w["week_start"], {}).get("link_taps"),
            "arrivals": w.get("instagram_sessions"),
            "engaged": w.get("instagram_engaged_sessions"),
            "cta": (w.get("instagram_cta_dm") or 0) + (w.get("instagram_cta_hotpepper") or 0),
        } for w in lw[-USUAL_WEEKS:]],
        "avg_engagement_sec": round(eng_sec / eng_n) if (eng_n and has_engagement) else None,
        "devices": sorted(({"device": k, "sessions": v} for k, v in devices.items()),
                          key=lambda x: -x["sessions"]) if has_audience else None,
        "visitors": {"new": new, "returning": returning} if has_audience else None,
        "courses": sorted(courses.values(), key=lambda x: -(x["cta_dm"] + x["cta_hotpepper"]))
        if has_courses else None,
        "courses_note": None if has_courses else "GA4で course が未登録のため、まだ出せません（登録した日以降の分から出ます）",
        "sources": sorted(sources.values(), key=lambda x: -x["sessions"])[:6] if has_week_sources
        else [{"source_medium": s.get("source_medium"), "sessions": s.get("sessions"),
               "engaged_sessions": s.get("engaged_sessions")} for s in (lp.get("sources") or [])[:6]],
        "sources_period": "recent" if has_week_sources else "all",
        "search": None if (not sc or sc.get("error")) else {
            "clicks": sc.get("clicks"), "impressions": sc.get("impressions"), "position": sc.get("position")},
    }


def _themes(posts: list, now: datetime) -> list:
    """直近 USUAL_WEEKS 週の、確定した投稿のテーマ別の中央値（テーマを決める材料。digest で読む）。"""
    cut = now - timedelta(weeks=USUAL_WEEKS)
    groups: dict = {}
    for p in posts:
        if p["has_insights"] and p["mature"] and p["_t"] >= cut and p["media_type"] in FEED_TYPES:
            groups.setdefault(p.get("theme") or "other", []).append(p)
    return [{
        "theme": k, "count": len(v),
        "median_reach": _median(p["metrics"]["reach"] for p in v),
        "median_saved_rate": _median(p["metrics"]["saved_rate"] for p in v),
        "median_pv_rate": _median(p["metrics"]["pv_rate"] for p in v),
    } for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))]


_PUBLIC_POST_KEYS = ("media_id", "date", "week_start", "weekday", "media_type", "permalink", "theme",
                     "title", "age_days", "mature", "metrics", "usual", "vs", "slug", "scheduled_at",
                     "delay_min", "menu", "trial", "cover_title", "edits")


def _public(p: dict) -> dict:
    return {k: p.get(k) for k in _PUBLIC_POST_KEYS}


def derive(data: dict, now: datetime | None = None) -> dict:
    """スナップショットから、画面と digest が使う数字をまとめて作る。"""
    now = now or _parse_ts(data.get("fetched_at")) or datetime.now(JST)
    posts = _posts(data, now)
    rows = (data.get("sheet") or {}).get("rows") or []
    records = data.get("records") or {}
    _attach_sheet(posts, rows, records, now)
    weeks = _weeks(data, posts)
    summary = _summary(weeks, data)
    review = _review_view(data.get("reviews") or [])
    judged_week = summary["week_start"] if summary else None
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "mature_days": MATURE_DAYS,
        "usual_posts": USUAL_POSTS,
        "usual_weeks": USUAL_WEEKS,
        "summary": summary,
        "judged_week": judged_week,
        "judged": [_public(p) for p in posts if p["week_start"] == judged_week and p["mature"]],
        "posts": [_public(p) for p in posts[:RECENT_POSTS]],
        "upcoming": _upcoming(rows, records, now),
        "trial_stats": _trial_stats(posts, review["decisions"]),
        "edits": _edit_stats(rows, records, now),
        "lp": _lp(data, weeks),
        "review": review,
        "themes": _themes(posts, now),
        "sheet_error": (data.get("sheet") or {}).get("error"),
        # 画面の言葉。正はこのファイルと review_post.py（画面側に同じ一覧を持たない）
        "labels": {"levers": TRIAL_LEVERS, "metrics": TRIAL_METRICS, "metric_fields": METRIC_FIELDS,
                   "decisions": DECISIONS, "verdicts": VERDICTS, "standard_sources": STANDARD_SOURCES},
    }


# ───────── digest（週次タスクの Claude が振り返りを書く前に読む） ─────────

WEEKDAYS = "月火水木金土日"


def _fmt(v, is_rate: bool = False) -> str:
    if v is None:
        return "—"
    if is_rate:
        return f"{v * 100:.1f}%"
    # 画面（Math.round）と同じ四捨五入にする。f"{2.5:.0f}" は偶数丸めで "2" になり、
    # 「2人 → いつも 2〜5 なのに少ない」と食い違って見える
    return f"{int(v + 0.5) if v >= 0 else -int(-v + 0.5):,}"


def _fmt_usual(u: dict | None, is_rate: bool = False) -> str:
    if not u:
        return "範囲なし（数が足りない）"
    return f"いつも {_fmt(u['low'], is_rate)}〜{_fmt(u['high'], is_rate)}（n={u['n']}）"


VS_LABEL = {**VERDICTS, None: "判定なし"}


def _post_line(p: dict) -> str:
    t = _parse_ts(p["date"])
    head = f"{t:%m/%d}({WEEKDAYS[t.weekday()]}) {p.get('slug') or '枠不明'} [{p.get('theme')}] " \
           f"{p.get('cover_title') or p.get('title')}"
    m = p["metrics"]
    nums = (f"届いた人 {_fmt(m['reach'])}（{VS_LABEL[p['vs'].get('reach')]}）／"
            f"保存率 {_fmt(m['saved_rate'], True)}（{VS_LABEL[p['vs'].get('saved_rate')]}・"
            f"{_fmt_usual(p['usual'].get('saved_rate'), True)}）／"
            f"プロフィール率 {_fmt(m['pv_rate'], True)}（{VS_LABEL[p['vs'].get('pv_rate')]}）")
    trial = p.get("trial") or {}
    if trial.get("lever") and trial.get("lever") != TRIAL_NONE:
        t_line = f"試したこと: [{trial.get('tag')}] {TRIAL_LEVERS.get(trial.get('lever'), trial.get('lever'))}｜" \
                 f"{trial.get('what')}（狙い: {TRIAL_METRICS.get(trial.get('metric'), trial.get('metric'))}）"
    elif trial:
        t_line = f"試したこと: なし（{trial.get('why')}）"
    else:
        t_line = "試したこと: 記録なし（この仕組みの前の投稿）"
    edits = p.get("edits") or {}
    e_line = ""
    if edits.get("count"):
        e_line = f"\n      修正 {edits['count']}回: {'・'.join(edits['changes'])}"
    if edits.get("direct"):
        e_line += "\n      ⚠ " + ("投稿後にキャプションが書き換えられています" if edits["direct"] == "app"
                                   else "シートが最後に校閲を通った版と違います")
    return f"  - {head}\n      {nums}\n      {t_line}{e_line}"


def digest(data: dict) -> str:
    d = data.get("derived") or derive(data)
    out = [f"# 振り返りの材料（データ取得 {data.get('fetched_at', '')[:16]}）", ""]

    s = d.get("summary")
    if s:
        out.append(f"## 確定した先週（{s['week_start']}の週）の数字")
        for t in s["tiles"]:
            unit = "件" if t["key"] == "saved" else "人"
            count = f"・{_fmt(t['count'])}{unit}" if t.get("count") is not None else ""
            out.append(f"  - {t['label']}: {_fmt(t['value'], t['is_rate'])}{count}"
                       f"（{VS_LABEL[t['verdict']]}・{_fmt_usual(t['usual'], t['is_rate'])}）")
        out.append(f"  - フォロワー {s.get('followers')}人（直近{s.get('followers_days')}日で"
                   f" +{s.get('followers_gain') or 0}）")
        out.append("")

    out.append(f"## 判定できる投稿（{d.get('judged_week')}の週・投稿から{MATURE_DAYS}日以上）")
    out += [_post_line(p) for p in d.get("judged") or []] or ["  （なし）"]
    out.append("")
    pending = [p for p in d.get("posts") or [] if not p["mature"]]
    out.append("## 集計中の投稿（途中の数字。判定はまだしない）")
    out += [_post_line(p) for p in pending] or ["  （なし）"]
    out.append("")

    out.append("## 施策の通算（試した投稿の結果）")
    for t in d.get("trial_stats") or []:
        field = METRIC_FIELDS.get(t["metric"])
        is_rate = bool(field and field.endswith("_rate"))
        out.append(f"  - [{t['tag']}] {t['what']}（{TRIAL_LEVERS.get(t['lever'], t['lever'])}・"
                   f"狙い {TRIAL_METRICS.get(t['metric'], t['metric'])}）: {t['count']}本・判定{t['judged']}本"
                   f"（多い{t['high']}／いつもどおり{t['usual']}／少ない{t['low']}）"
                   f" 中央値 {_fmt(t['median_with'], is_rate)}・試さなかった投稿 {_fmt(t['median_without'], is_rate)}"
                   f"／これまでの判定: {DECISIONS.get(t['decision'], 'なし')}・もう一度{t['again']}回")
    if not d.get("trial_stats"):
        out.append("  （まだない）")
    out.append("")

    reviews = data.get("reviews") or []
    committed = [r for r in reviews if not r.get("_draft")]
    prev = committed[-1] if committed else None
    out.append("## 前回の振り返り" + (f"（{prev['written_on']}）" if prev else "（まだない＝初回）"))
    if prev:
        out.append("  いまの標準:")
        out += [f"    - [{x.get('tag')}] {x.get('what')}（{STANDARD_SOURCES.get(x.get('source'), x.get('source'))}）"
                for x in prev.get("standards") or []] or ["    （なし）"]
        out.append("  やめたこと:")
        out += [f"    - [{x.get('tag')}] {x.get('what')}" for x in prev.get("stopped") or []] or ["    （なし）"]
        out.append("  前回の「次に試すこと」:")
        out += [f"    - [{x.get('tag')}] {x.get('what')}" for x in prev.get("next") or []] or ["    （なし）"]
    else:
        out.append("  初回は、直近の投稿メモ（シートF列・content の memo）から「毎回入れている型」を")
        out.append("  standards（source: practice）に書き出し、試験扱いにしないこと。")
    out.append("")

    out.append("## 前回の振り返りのあとに入ったご本人の修正（依頼の文は公開ページに書かない）")
    out += _edit_lines(data, prev["written_on"] if prev else None) or ["  （なし）"]
    e = d.get("edits") or {}
    out.append(f"  直近{e.get('weeks')}週の枠 {e.get('slots')}本のうち、記録あり{e.get('known')}本・"
               f"修正あり{e.get('edited')}本。よく直された箇所: "
               + ("・".join(f"{x['label']}{x['count']}回" for x in e.get("top_changes") or []) or "なし"))
    out.append("")

    lp = d.get("lp") or {}
    out.append(f"## LP（Instagram経由・直近{lp.get('period_weeks', 0)}週の合計）")
    if lp.get("available"):
        f = lp["funnel"]
        out.append(f"  プロフィールを見た {_fmt(f['profile_views'])} → リンクのタップ {_fmt(f['link_taps'])}"
                   f" → LPに着いた {_fmt(f['arrivals'])} → しっかり見た {_fmt(f['engaged'])}"
                   f" → 予約ボタン DM {_fmt(f['cta_dm'])}・ホットペッパー {_fmt(f['cta_hotpepper'])}"
                   f"（ホットペッパーから戻った {_fmt(f['bounced'])}）")
    else:
        out.append(f"  {lp.get('reason')}")
    out.append("")

    out.append(f"## テーマ別の中央値（直近{USUAL_WEEKS}週・確定した投稿）")
    for t in d.get("themes") or []:
        out.append(f"  - {t['theme']}: {t['count']}本・届いた人 {_fmt(t['median_reach'])}・"
                   f"保存率 {_fmt(t['median_saved_rate'], True)}・プロフィール率 {_fmt(t['median_pv_rate'], True)}")
    out.append("")

    out.append("## 予定（シート上でまだ投稿されていない枠）")
    for u in d.get("upcoming") or []:
        trial = u.get("trial") or {}
        out.append(f"  - {u['post_datetime']} {u['status']} {u.get('cover_title') or ''}"
                   f"（試すこと: {trial.get('tag') or trial.get('lever') or '記録なし'}）")
    if not d.get("upcoming"):
        out.append("  （なし）")
    pending_review = unreviewed_upcoming(d.get("upcoming") or [])
    if pending_review:
        out.append("  ⚠ 校閲を通っていない予定の枠: " + "・".join(u["slug"] for u in pending_review))
        out.append("    → 手順4で空き枠を作る前に、その枠の content を review_post.py --origin weekly で"
                   "校閲し直す（❌ なら直して create_post.py から）")
    if d.get("sheet_error"):
        out.append(f"  ⚠ {d['sheet_error']}")
    out.append("")

    out.append("## 書き方")
    out.append(f"  - 変えてよい項目（lever）: {' / '.join(f'{k}={v}' for k, v in TRIAL_LEVERS.items())}")
    out.append(f"  - 狙う数字（metric）: {' / '.join(f'{k}={v}' for k, v in TRIAL_METRICS.items())}")
    out.append(f"  - 次に試すことは1〜{MAX_NEXT}個。標準とやめたことに入っている tag は書けない。"
               f"「もう一度」は同じ tag に{MAX_AGAIN}回まで")
    out.append("  - 投稿時刻・CTAの文言・枚数の上限・プロフィール文・リール・LPは、変えられないので提案しない")
    out.append(SCHEMA_HELP)
    return "\n".join(out)


def _edit_lines(data: dict, since: str | None) -> list:
    """修正の記録を、依頼の文つきで（ローカルの記録から直接読む。スナップショットには文を入れない）。"""
    from content_baseline import load_history
    lines = []
    for slug in sorted((data.get("records") or {}).keys()):
        hist = load_history(slug) or {}
        for e in hist.get("events") or []:
            if since and str(e.get("at") or "")[:10] <= since:
                continue
            req = (e.get("request") or "").replace("\n", " ")
            lines.append(f"  - {slug}（{str(e.get('at'))[:16]}）{'・'.join(e.get('changes') or [])}"
                         + (f"\n      依頼: {req[:200]}" if req else ""))
    return lines


# ───────── check（振り返りの下書きの機械チェック） ─────────

def _has_digit(text) -> bool:
    return bool(re.search(r"[0-9０-９]", str(text or "")))


def _leaked_request(text, requests) -> str | None:
    """text に修正依頼の文が LEAK_MIN_CHARS 字以上そのまま入っていれば、その部分を返す。"""
    t = _norm(text)
    for req in requests:
        r = _norm(req)
        if len(r) < 6 or not t:
            continue
        need = min(LEAK_MIN_CHARS, len(r))
        m = difflib.SequenceMatcher(None, t, r, autojunk=False).find_longest_match(0, len(t), 0, len(r))
        if m.size >= need:
            return r[m.b:m.b + m.size]
    return None


def _public_texts(draft: dict) -> list:
    """振り返りのうち公開ページに出る文（どこの欄か, 文）。"""
    out = [("summary", draft.get("summary"))]
    for key, fields in (("verdicts", ("evidence", "note")), ("next", ("what", "why")),
                        ("standards", ("what",)), ("stopped", ("what",))):
        for x in draft.get(key) or []:
            if isinstance(x, dict):
                out += [(f"{key}[{x.get('tag')}].{f}", x.get(f)) for f in fields if x.get(f)]
    return out


def check_review(draft: dict, past: list, trial_tags: set, requests=()) -> list:
    """下書きを検査して (ok, msg) の並びを返す。

    past はコミット済みの振り返り（下書きの日付より前）。requests は手元の修正の記録にある
    修正依頼の文（公開される欄にそのまま写していないかを見る）。
    """
    res = []
    if not isinstance(draft, dict):
        return [(False, "下書きが JSON オブジェクトではありません")]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(draft.get("written_on") or "")):
        res.append((False, "written_on は YYYY-MM-DD で書いてください"))
    summary = str(draft.get("summary") or "").strip()
    if not summary:
        res.append((False, "summary が空です"))
    elif len(summary) > 300:
        res.append((False, f"summary が長すぎます（{len(summary)}字・300字まで）"))
    elif not _has_digit(summary):
        res.append((False, "summary に数字を入れてください（何がどれだけだったか）"))
    for where, text in _public_texts(draft):
        leaked = _leaked_request(text, requests)
        if leaked:
            res.append((False, f"{where} に修正依頼の文がそのまま入っています（「{leaked[:20]}…」）。"
                               "公開ページに出るので、言い換えてください"))

    def tag_ok(tag) -> bool:
        return bool(TRIAL_TAG_RE.fullmatch(str(tag or "")))

    standards = draft.get("standards") or []
    stopped = draft.get("stopped") or []
    std_tags = {x.get("tag") for x in standards if isinstance(x, dict)}
    stop_tags = {x.get("tag") for x in stopped if isinstance(x, dict)}
    for x in standards:
        if not isinstance(x, dict) or not tag_ok(x.get("tag")) or not str(x.get("what") or "").strip():
            res.append((False, f"standards の項目に tag（英小文字・数字・ハイフン）と what が要ります: {x}"))
            continue
        src = x.get("source")
        if src not in STANDARD_SOURCES:
            res.append((False, f"standards[{x['tag']}].source は {' / '.join(STANDARD_SOURCES)} のどれか"))
        if src == "edits":
            based = [b for b in (x.get("based_on") or []) if b]
            need = 1 if x.get("explicit") else EDITS_MIN_POSTS
            if len(set(based)) < need:
                res.append((False, f"standards[{x['tag']}] は修正から取り入れる項目です。根拠の投稿（based_on）を"
                                   f"{need}本以上書いてください（1回きりの事情を全部の投稿に広げないため。"
                                   f"依頼の文に「今後も」などがあった時だけ explicit: true で1本可）"))
    for x in stopped:
        if not isinstance(x, dict) or not tag_ok(x.get("tag")):
            res.append((False, f"stopped の項目に tag が要ります: {x}"))
    both = std_tags & stop_tags
    if both:
        res.append((False, f"標準とやめたことの両方に入っている tag があります: {', '.join(sorted(both))}"))

    # 前回の標準・やめたことを黙って消していないか（外すなら stopped に移す）。
    # 「これまでの型」（practice）は試した記録が無く verdicts で stop にできないので、stopped へ移せば外せる
    prev = past[-1] if past else None
    verdicts = draft.get("verdicts") or []
    decided = {v.get("tag"): v.get("decision") for v in verdicts if isinstance(v, dict)}
    if prev:
        for x in prev.get("standards") or []:
            t = x.get("tag")
            if t and t not in std_tags and t not in stop_tags:
                res.append((False, f"前回の標準 [{t}] が消えています。続けるなら書き写し、やめるなら stopped に移してください"))
        for x in prev.get("stopped") or []:
            t = x.get("tag")
            if t and t not in stop_tags:
                res.append((False, f"前回のやめたこと [{t}] が消えています。書き写してください"))

    # 判定
    again_before: dict = {}
    for r in past:
        for v in r.get("verdicts") or []:
            if v.get("decision") == "again":
                again_before[v.get("tag")] = again_before.get(v.get("tag"), 0) + 1
    for v in verdicts:
        if not isinstance(v, dict):
            res.append((False, f"verdicts の項目が不正です: {v}"))
            continue
        t = v.get("tag")
        if v.get("decision") not in DECISIONS:
            res.append((False, f"verdicts[{t}].decision は {' / '.join(DECISIONS)} のどれか"))
        if not _has_digit(v.get("evidence")):
            res.append((False, f"verdicts[{t}].evidence に根拠の数字を入れてください"))
        if t not in trial_tags:
            res.append((False, f"verdicts[{t}] の施策を試した投稿が記録にありません（判定は試した投稿があるものだけ）"))
        if v.get("decision") == "again" and again_before.get(t, 0) >= MAX_AGAIN:
            res.append((False, f"[{t}] は「もう一度」がすでに{MAX_AGAIN}回です。標準にするか、やめるかを決めてください"))
        if v.get("decision") == "standard" and t not in std_tags:
            res.append((False, f"[{t}] を標準にするなら standards にも書いてください"))
        if v.get("decision") == "stop" and t not in stop_tags:
            res.append((False, f"[{t}] をやめるなら stopped にも書いてください"))

    # 次に試すこと
    nxt = draft.get("next") or []
    if not 1 <= len(nxt) <= MAX_NEXT:
        res.append((False, f"next（次に試すこと）は1〜{MAX_NEXT}個にしてください（今 {len(nxt)}個）"))
    past_stops = {v.get("tag") for r in past for v in (r.get("verdicts") or []) if v.get("decision") == "stop"}
    for x in nxt:
        if not isinstance(x, dict):
            res.append((False, f"next の項目が不正です: {x}"))
            continue
        t = x.get("tag")
        if not tag_ok(t):
            res.append((False, f"next の tag=\"{t}\" は英小文字・数字・ハイフンにしてください"))
        if x.get("lever") not in TRIAL_LEVERS:
            res.append((False, f"next[{t}].lever=\"{x.get('lever')}\" は変えてよい項目ではありません"
                               f"（{' / '.join(TRIAL_LEVERS)}）"))
        if x.get("metric") not in TRIAL_METRICS:
            res.append((False, f"next[{t}].metric は {' / '.join(TRIAL_METRICS)} のどれか"))
        what = str(x.get("what") or "")
        if not what.strip():
            res.append((False, f"next[{t}].what が空です"))
        fixed = fixed_items_in(what)
        if fixed:
            res.append((False, f"next[{t}] は変えられない項目に見えます（{'・'.join(fixed)}）。"
                               "投稿を作るときに変えられることだけを書いてください"))
        if not _has_digit(x.get("why")):
            res.append((False, f"next[{t}].why に根拠の数字を入れてください"))
        if t in std_tags:
            res.append((False, f"next[{t}] はもう標準です（毎回入れる型なので、試すことにはしない）"))
        if t in stop_tags or t in past_stops:
            res.append((False, f"next[{t}] は前にやめた施策です"))
        if decided.get(t) in ("standard", "stop"):
            res.append((False, f"next[{t}] は今回 {DECISIONS[decided[t]]} と判定した施策です"))
    tags = [x.get("tag") for x in nxt if isinstance(x, dict)]
    if len(tags) != len(set(tags)):
        res.append((False, "next に同じ tag が2回出ています"))

    if not res:
        res.append((True, f"振り返りの下書き: 判定{len(verdicts)}件・標準{len(standards)}件・"
                          f"やめたこと{len(stopped)}件・次に試すこと{len(nxt)}件 ✓"))
    return res


def _local_requests(data: dict) -> list:
    """手元の修正の記録にある修正依頼の文（スナップショットには入れていないので記録から直接読む）。"""
    from content_baseline import load_history
    out = []
    for slug in (data.get("records") or {}):
        for e in (load_history(slug) or {}).get("events") or []:
            if str(e.get("request") or "").strip():
                out.append(e["request"])
    return out


def _trial_tags(data: dict) -> set:
    """判定できる（投稿から MATURE_DAYS 日たった）投稿で試した tag。判定を書けるのはこれだけ。"""
    return {t.get("tag") for t in ((data.get("derived") or {}).get("trial_stats") or [])
            if t.get("judged")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="振り返りの材料（digest）と下書きのチェック（check）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("digest", help="振り返りを書く前に読む材料を表示する")
    c = sub.add_parser("check", help="振り返りの下書きを機械チェックする")
    c.add_argument("path", nargs="?", default=str(DRAFT_FILE))
    args = ap.parse_args(argv)

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    if args.cmd == "digest":
        print(digest(data))
        return 0

    try:
        draft = json.loads(Path(args.path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"❌ 下書きを読めません: {e}")
        return 1
    past = [r for r in load_reviews(include_draft=False)
            if str(r.get("written_on")) < str(draft.get("written_on"))]
    results = check_review(draft, past, _trial_tags(data), _local_requests(data))
    errors = [m for ok, m in results if not ok]
    for ok, m in results:
        print(("  ✓ " if ok else "  ✗ ") + m)
    print("✅ 問題なし" if not errors else f"❌ 問題あり: {len(errors)}件（直してからもう一度 check）")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
