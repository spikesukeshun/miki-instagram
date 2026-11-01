"""ダッシュボードの振り返りの数字（dashboard/review_inputs.py）のテスト。

  python3 -m unittest tests/test_review_inputs.py
"""
import copy
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboard"))

import review_inputs as ri  # noqa: E402

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 7, 8, 30, tzinfo=JST)  # 土曜朝の週次更新


def ts(y, mo, d, h, mi=0):
    """JST の日時を Instagram の timestamp（+0000）にする。"""
    return datetime(y, mo, d, h, mi, tzinfo=JST).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")


def post(when, caption, reach=150, saved=1, pv=3, media_type="CAROUSEL_ALBUM"):
    ins = {"reach": reach, "saved": saved, "follows": 0}
    if media_type != "VIDEO":
        ins["profile_visits"] = pv
    return {"media_id": caption[:8], "timestamp": when, "media_type": media_type,
            "permalink": "https://example.com/p", "caption_head": caption[:120], "theme": "menu",
            "caption_key": ri.caption_key(caption), "caption_sig": ri.caption_sig(caption),
            "insights": ins}


def row(slug, caption, hashtags="", status="投稿済み"):
    dt = datetime.strptime(slug, "%Y-%m-%d-%H%M")
    return {"slug": slug, "post_datetime": dt.strftime("%Y/%m/%d %H:%M"), "menu": "美容情報",
            "status": status, "preview_url": "", "caption_key": ri.caption_key(caption),
            "caption_sig": ri.caption_sig(caption, hashtags)}


def trial(tag="cover-number", metric="saved"):
    return {"tag": tag, "lever": "cover", "what": "表紙に数字", "metric": metric,
            "why": "10/12は保存2件", "where": "表紙「4つ」"}


def snapshot():
    posts = []
    # いつもの範囲の材料: 9月〜10月の投稿14本（保存率は 0.5%〜1.2% あたり）
    start = datetime(2026, 9, 7, 22, tzinfo=JST)
    for i in range(14):
        t = start + timedelta(days=3 * i)
        posts.append(post(t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000"),
                          f"古い投稿{i:02d}の書き出しの一文はここまでです本文が続きます",
                          reach=120 + i * 5, saved=1 if i % 3 else 2, pv=2 + i % 3))
    # 判定する週（10/26の週）の3本。金曜分は 3時間遅れて土曜 1:18 に出た
    cap_mon = "月曜の投稿の書き出しの一文はこれで十分な長さになります本文"
    cap_thu = "木曜の投稿の書き出しの一文はこれで十分な長さになります本文"
    cap_fri = "金曜の投稿の書き出しの一文はこれで十分な長さになります本文"
    posts.append(post(ts(2026, 10, 26, 22, 4), cap_mon, reach=180, saved=4, pv=4))
    posts.append(post(ts(2026, 10, 29, 21, 58), cap_thu + "アプリで直した", reach=100, saved=0, pv=1))
    posts.append(post(ts(2026, 10, 31, 1, 18), cap_fri, reach=90, saved=1, pv=0))
    # 集計中（11/2 の投稿は4日目）
    cap_new = "新しい投稿の書き出しの一文はこれで十分な長さになります本文"
    posts.append(post(ts(2026, 11, 2, 22, 2), cap_new, reach=60, saved=0, pv=1))

    weekly = []
    w = datetime(2026, 8, 10, tzinfo=JST)
    while w <= datetime(2026, 11, 2, tzinfo=JST):
        weekly.append({"week_start": w.strftime("%Y-%m-%d"), "partial": w.month == 11,
                       "reach": 400 + (w.day % 7) * 20, "profile_views": 40, "website_clicks": 3})
        w += timedelta(weeks=1)

    rows = [
        row("2026-10-26-2200", cap_mon),
        row("2026-10-29-2100", cap_thu),            # Instagram 側だけ書き換わっている → 時刻で結ぶ
        row("2026-10-30-2200", cap_fri),
        row("2026-11-02-2200", cap_new),
        row("2026-11-09-2200", "来週の投稿の書き出し", status="確認待ち"),
        row("2026-11-12-2100", "校閲前に止まった回", status="確認待ち"),       # 前回版が無い
        row("2026-11-13-2200", "手動投稿のリール", status="手動投稿待ち"),     # リールは校閲しない
    ]
    records = {
        "2026-10-26-2200": {"cover_title": "4つ", "trial": trial(), "caption_sig": ri.caption_sig(cap_mon),
                            "base_origin": "weekly", "revisions": [
                                {"at": "2026-10-25T10:00:00+09:00", "changes": ["表紙タイトル", "スライド3の文言"]}]},
        "2026-10-29-2100": {"cover_title": "", "trial": trial(), "caption_sig": ri.caption_sig(cap_thu),
                            "base_origin": "weekly", "revisions": []},
        "2026-10-30-2200": {"cover_title": "", "trial": {"lever": "none", "why": "差し替え"},
                            "caption_sig": "different", "base_origin": "weekly", "revisions": []},
        "2026-11-09-2200": {"cover_title": "来週の表紙", "trial": trial("cover-question"),
                            "caption_sig": ri.caption_sig("来週の投稿の書き出し"), "base_origin": "weekly",
                            "revisions": [{"at": "2026-11-07T08:00:00+09:00", "changes": ["スライド2の写真"]}]},
    }
    return {
        "fetched_at": NOW.isoformat(), "account": {"followers_count": 700},
        "account_daily": [{"date": "2026-11-01", "follower_count": 1}],
        "account_weekly": weekly, "posts": posts, "lp": None,
        "sheet": {"rows": rows, "error": None}, "records": records, "reviews": [],
    }


class RangeTest(unittest.TestCase):
    def test_usual_range_needs_enough_values(self):
        self.assertIsNone(ri.usual_range([1, 2, 3]))
        u = ri.usual_range([1, 2, 3, 4, 5])
        self.assertEqual((u["low"], u["median"], u["high"]), (2, 3, 4))
        self.assertEqual(ri.compare(5, u), "high")
        self.assertEqual(ri.compare(1, u), "low")
        self.assertEqual(ri.compare(3, u), "usual")

    def test_caption_sig_matches_posted_caption(self):
        # post_scheduler.build_caption は「本文 + 空行 + ハッシュタグ」で投稿する
        self.assertEqual(ri.caption_sig("本文です\n", "#a #b"), ri.caption_sig("本文です\n\n#a #b"))


class DeriveTest(unittest.TestCase):
    def setUp(self):
        self.d = ri.derive(snapshot(), NOW)

    def test_summary_is_the_last_complete_week(self):
        self.assertEqual(self.d["summary"]["week_start"], "2026-10-26")
        self.assertEqual([t["key"] for t in self.d["summary"]["tiles"]],
                         ["reach", "saved", "profile_views", "lp"])

    def test_judged_posts_are_matched_to_slots(self):
        judged = {p["slug"]: p for p in self.d["judged"]}
        self.assertEqual(set(judged), {"2026-10-26-2200", "2026-10-29-2100", "2026-10-30-2200"})
        self.assertEqual(judged["2026-10-30-2200"]["delay_min"], 198)  # 22:00 → 翌 1:18
        self.assertEqual(judged["2026-10-26-2200"]["vs"]["saved_rate"], "high")
        self.assertEqual(judged["2026-10-26-2200"]["edits"]["changes"], ["表紙タイトル", "スライド3の文言"])

    def test_direct_edits_are_detected(self):
        judged = {p["slug"]: p for p in self.d["judged"]}
        self.assertEqual(judged["2026-10-29-2100"]["edits"]["direct"], "app")
        self.assertEqual(judged["2026-10-30-2200"]["edits"]["direct"], "sheet")

    def test_new_posts_are_not_judged(self):
        newest = self.d["posts"][0]
        self.assertFalse(newest["mature"])
        self.assertIsNone(newest["vs"]["saved_rate"])

    def test_trial_stats_and_upcoming(self):
        stats = {t["tag"]: t for t in self.d["trial_stats"]}
        self.assertEqual((stats["cover-number"]["count"], stats["cover-number"]["judged"]), (2, 2))
        self.assertNotIn("cover-question", stats)  # まだ投稿されていない
        self.assertEqual([u["slug"] for u in self.d["upcoming"]],
                         ["2026-11-09-2200", "2026-11-12-2100", "2026-11-13-2200"])
        self.assertEqual([u["slug"] for u in ri.unreviewed_upcoming(self.d["upcoming"])], ["2026-11-12-2100"])
        self.assertEqual(self.d["upcoming"][0]["edits"]["count"], 1)
        self.assertEqual(self.d["edits"]["edited"], 2)


class CheckReviewTest(unittest.TestCase):
    DRAFT = {
        "written_on": "2026-11-14",
        "summary": "先週は保存4件でいつもより多かった。",
        "verdicts": [{"tag": "cover-number", "decision": "again", "evidence": "保存率2.2%・いつも0.8〜1.0%"}],
        "standards": [{"tag": "save-list", "what": "保存用のリストを1枚", "since": "2026-11-07", "source": "practice"}],
        "stopped": [],
        "next": [{"tag": "cover-question", "lever": "cover", "what": "表紙を疑問形に", "metric": "saved",
                  "why": "10/05は保存2件"}],
    }

    def errors(self, draft, past=(), tags=("cover-number",)):
        return [m for ok, m in ri.check_review(draft, list(past), set(tags)) if not ok]

    def test_valid_draft_passes(self):
        self.assertEqual(self.errors(self.DRAFT), [])

    def test_fixed_items_cannot_be_proposed(self):
        d = copy.deepcopy(self.DRAFT)
        d["next"][0]["lever"] = "posting_time"
        self.assertTrue(self.errors(d))
        d = copy.deepcopy(self.DRAFT)
        d["next"][0]["what"] = "投稿時間を18時にする"
        self.assertTrue(self.errors(d))

    def test_summary_needs_numbers(self):
        d = copy.deepcopy(self.DRAFT)
        d["summary"] = "先週はよかった。"
        self.assertTrue(any("summary に数字" in m for m in self.errors(d)))

    def test_request_text_must_not_be_copied_to_public_fields(self):
        req = ["表紙の写真をもっと明るいものに変えてください。暗いと開かれない気がします"]
        d = copy.deepcopy(self.DRAFT)
        d["summary"] = "保存は4件。表紙の写真をもっと明るいものに変えてほしいと依頼があった。"
        msgs = [m for ok, m in ri.check_review(d, [], {"cover-number"}, req) if not ok]
        self.assertTrue(any("修正依頼の文" in m for m in msgs), msgs)
        # 言い換えた標準は通る
        d = copy.deepcopy(self.DRAFT)
        d["standards"].append({"tag": "edit-bright-cover", "what": "表紙の写真は明るいものを選ぶ",
                               "since": "2026-11-14", "source": "edits", "explicit": True,
                               "based_on": ["2026-11-09-2200"]})
        self.assertEqual([m for ok, m in ri.check_review(d, [], {"cover-number"}, req) if not ok], [])

    def test_fixed_items_are_caught_even_when_reworded(self):
        d = copy.deepcopy(self.DRAFT)
        d["next"][0]["what"] = "18時に投稿する"   # lever は表紙のまま
        self.assertTrue(any("変えられない" in m for m in self.errors(d)))

    def test_why_and_evidence_need_numbers(self):
        d = copy.deepcopy(self.DRAFT)
        d["next"][0]["why"] = "なんとなく"
        d["verdicts"][0]["evidence"] = "よかった"
        self.assertEqual(len(self.errors(d)), 2)

    def test_standard_and_stopped_tags_cannot_be_tried_again(self):
        d = copy.deepcopy(self.DRAFT)
        d["next"][0]["tag"] = "save-list"
        self.assertTrue(self.errors(d))
        past = [{"written_on": "2026-11-07", "verdicts": [{"tag": "cover-question", "decision": "stop"}],
                 "standards": [{"tag": "save-list"}], "stopped": [{"tag": "cover-question"}]}]
        self.assertTrue(self.errors(self.DRAFT, past))

    def test_again_is_limited(self):
        past = [{"written_on": f"2026-10-{d}", "verdicts": [{"tag": "cover-number", "decision": "again"}],
                 "standards": [{"tag": "save-list"}]} for d in (24, 31)]
        self.assertTrue(any("2回" in m for m in self.errors(self.DRAFT, past)))

    def test_verdict_needs_a_judged_post(self):
        self.assertTrue(self.errors(self.DRAFT, tags=()))

    def test_dropping_a_standard_needs_a_stop(self):
        past = [{"written_on": "2026-11-07", "standards": [{"tag": "bright-cover"}, {"tag": "save-list"}]}]
        self.assertTrue(any("消えています" in m for m in self.errors(self.DRAFT, past)))
        # stopped に移せば外せる（これまでの型は試した記録が無く、判定で stop にできないため）
        d = copy.deepcopy(self.DRAFT)
        d["stopped"] = [{"tag": "bright-cover", "what": "表紙は明るい写真", "since": "2026-11-14"}]
        self.assertEqual(self.errors(d, past), [])

    def test_standard_from_edits_needs_two_posts(self):
        d = copy.deepcopy(self.DRAFT)
        d["standards"].append({"tag": "edit-bright-cover", "what": "表紙は明るい写真", "since": "2026-11-14",
                               "source": "edits", "based_on": ["2026-11-09-2200"]})
        self.assertTrue(self.errors(d))
        d["standards"][-1]["explicit"] = True
        self.assertEqual(self.errors(d), [])
        d["standards"][-1]["explicit"] = False
        d["standards"][-1]["based_on"].append("2026-11-12-2100")
        self.assertEqual(self.errors(d), [])


if __name__ == "__main__":
    unittest.main()
