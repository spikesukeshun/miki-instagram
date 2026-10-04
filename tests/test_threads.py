"""Threads 実験コードのテスト（ネットワーク・シートに触れない）。

  python3 -m unittest tests/test_threads.py
"""

import os
import sys
import unittest
from datetime import datetime, date
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import threads_api as api  # noqa: E402
import threads_plan as plan  # noqa: E402
import threads_scheduler as sched  # noqa: E402
import threads_store as store  # noqa: E402
import threads_notify as notifier  # noqa: E402
import line_notify  # noqa: E402
import tempfile  # noqa: E402
import gspread  # noqa: E402

CAPTION = (
    "肩こりと顔のむくみ、実はつながっているって知っていましたか？\n\n"
    "MIKIです。今日は首と肩のケアについてお話しします。デスクワークが続くと、"
    "首の後ろがガチガチになって、夕方には顔までむくんでしまう方がとても多いんです。"
    "私の施術では、デコルテから首、肩までしっかりほぐしてから、お顔に入ります。"
    "VIPオーダーメイド150分（15分ジャグジーつき）¥24,800"
)
POOL = {"111": {"ig_id": "111", "caption": CAPTION, "children": 6, "ig_date": "2026-05-01",
                "permalink": "https://instagram.com/p/x"},
        "222": {"ig_id": "222", "caption": "花嫁さまのための準備の話。" * 10, "children": 0}}
PRICES = {"24800", "15800"}


def entry(**kw):
    base = {"scheduled": "2026/10/06 08:00", "slot": "朝", "ig_id": "111", "type": "悩み起点",
            "flags": ["悩み"], "topic_tag": "六本木エステ", "media": "carousel:0,1,2",
            "text": "夕方になると顔がむくむ。\n\nそれ、首と肩のこりが原因のことがあります。\n"
                    "六本木で施術していると、デスクワークの方にとても多いんです。\n\n"
                    "肩とむくみ、どっちが気になりますか？"}
    base.update(kw)
    return base


class TextLengthTest(unittest.TestCase):
    def test_japanese_counts_one_per_char(self):
        self.assertEqual(api.text_length("あいう"), 3)

    def test_emoji_counts_utf8_bytes(self):
        self.assertEqual(api.text_length("😊"), 4)

    def test_topic_tag_rules(self):
        self.assertIsNone(api.validate_topic_tag("六本木エステ"))
        self.assertIsNotNone(api.validate_topic_tag("a.b"))
        self.assertIsNotNone(api.validate_topic_tag("美容&エステ"))
        self.assertIsNotNone(api.validate_topic_tag("#美容"))
        self.assertIsNotNone(api.validate_topic_tag("あ" * 51))


class ReviewTest(unittest.TestCase):
    def review(self, posts):
        return plan.review_entries(posts, POOL, PRICES)

    def test_good_entry_passes(self):
        errors, _ = self.review([entry()])
        self.assertEqual(errors, [])

    def test_flags_are_detected_from_text(self):
        posts = [entry()]
        self.review(posts)
        self.assertEqual(posts[0]["flags"], ["地域", "悩み", "問いかけ"])

    def test_cta_ignores_noun_soudan(self):
        self.assertNotIn("CTA", plan.detect_flags("花嫁さまのご相談が多いです", []))
        self.assertIn("CTA", plan.detect_flags("気になることはDMで聞いてください", []))
        self.assertIn("CTA", plan.detect_flags("お気軽にご相談くださいね", []))

    def test_copy_of_caption_fails(self):
        errors, _ = self.review([entry(text=CAPTION[:300])])
        self.assertTrue(any("単純コピー" in e for e in errors), errors)

    def test_over_500_fails(self):
        errors, _ = self.review([entry(text="あ" * 501)])
        self.assertTrue(any("500字" in e for e in errors))

    def test_salon_name_and_ig_discount_fail(self):
        errors, _ = self.review([entry(text="AMRTAで施術しています。Instagram限定20%OFFです")])
        self.assertTrue(any("AMRTA" in e for e in errors))
        self.assertTrue(any("Instagram限定" in e for e in errors))

    def test_old_first_visit_discount_fails(self):
        errors, _ = self.review([entry(text="MIKI指名 初回限定20%OFF（VIPコースのみ）首と肩のケア")])
        self.assertTrue(any("20%OFF" in e for e in errors), errors)

    def test_unknown_price_fails_known_price_passes(self):
        errors, _ = self.review([entry(text="今月は¥9,800でご案内しています。首と肩のケアです")])
        self.assertTrue(any("価格" in e for e in errors))
        errors, _ = self.review([entry(text="150分のコースは¥24,800です。首と肩からほぐします")])
        self.assertFalse(any("価格" in e for e in errors), errors)

    def test_availability_requires_manual_info(self):
        errors, _ = self.review([entry(text="今日の15時、空きが出ました。首肩ほぐしたい方へ")])
        self.assertTrue(any("availability" in e for e in errors))
        errors, _ = self.review([entry(text="今日の15時、空きが出ました。首肩ほぐしたい方へ",
                                       availability="10/6 15:00 1枠")])
        self.assertFalse(any("availability" in e for e in errors), errors)

    def test_unknown_ig_id_fails(self):
        errors, _ = self.review([entry(ig_id="999")])
        self.assertTrue(any("候補プール" in e for e in errors))

    def test_same_type_twice_and_same_day_and_same_post_fail(self):
        a = entry()
        b = entry(text="別の書き出しです。\n首のケアについて。")
        errors, _ = self.review([a, b])
        joined = "\n".join(errors)
        self.assertIn("2日連続", joined)
        self.assertIn("1日1投稿", joined)
        self.assertIn("2回使って", joined)

    def test_hashtag_and_bait_fail(self):
        errors, _ = self.review([entry(text="#エステ いいねしてね")])
        self.assertTrue(any("ハッシュタグ" in e for e in errors))
        self.assertTrue(any("ベイト" in e for e in errors))

    def test_carousel_index_out_of_range(self):
        errors, _ = self.review([entry(media="carousel:0,9")])
        self.assertTrue(any("枚数" in e for e in errors))

    def test_cta_over_half_warns(self):
        posts = [entry(ig_id="111", text="DMからご相談ください。首肩のケア"),
                 entry(ig_id="222", type="施術紹介", scheduled="2026/10/07 12:30", slot="昼",
                       text="花嫁さまの準備。ご予約はDMから")]
        _, warns = self.review(posts)
        self.assertTrue(any("CTA" in w for w in warns))

    def test_allowed_prices_come_from_skill_md(self):
        self.assertIn("24800", plan.allowed_prices())


class SlotTest(unittest.TestCase):
    def test_rotation_covers_all_slots_evenly(self):
        counts = {}
        for i in range(30):
            counts[plan.slot_for(i)[0]] = counts.get(plan.slot_for(i)[0], 0) + 1
        self.assertEqual(set(counts), {"朝", "昼", "夜"})
        self.assertTrue(all(9 <= c <= 11 for c in counts.values()), counts)

    def test_same_weekday_rotates_week_to_week(self):
        self.assertNotEqual(plan.slot_for(0), plan.slot_for(7))


class MediaSuggestTest(unittest.TestCase):
    def test_carousel_drops_last_two_cta_slides(self):
        item = {"media_type": "CAROUSEL_ALBUM", "children": {"data": [{}] * 8}}
        self.assertEqual(plan.suggest_media(item), "carousel:0,1,2,3")
        item = {"media_type": "CAROUSEL_ALBUM", "children": {"data": [{}] * 4}}
        self.assertEqual(plan.suggest_media(item), "carousel:0,1")

    def test_video_uses_thumbnail(self):
        self.assertEqual(plan.suggest_media({"media_type": "VIDEO"}), "thumbnail")


JST = sched.JST


def row(**kw):
    base = {"予定日時": "2026/10/06 08:00", "ステータス": store.ST_APPROVED, "本文": "首と肩の話",
            "本文_生成時": "首と肩の話", "元IG投稿ID": "111", "メディア指定": "text", "空き情報": ""}
    base.update(kw)
    return base


class PickRowTest(unittest.TestCase):
    now = datetime(2026, 10, 6, 8, 35, tzinfo=JST)

    def test_picks_due_approved_row(self):
        r, rec, _ = sched.pick_row([(2, row())], self.now)
        self.assertEqual(r, 2)

    def test_not_due_yet(self):
        r, _, _ = sched.pick_row([(2, row(予定日時="2026/10/06 12:30"))], self.now)
        self.assertIsNone(r)

    def test_one_post_per_day(self):
        posted = row(ステータス=store.ST_POSTED, 投稿日時_実際="2026/10/06 08:31")
        r, _, reason = sched.pick_row([(2, posted), (3, row())], self.now)
        self.assertIsNone(r)
        self.assertIn("1日1投稿", reason)

    def test_stale_row_from_yesterday_is_not_posted(self):
        r, _, _ = sched.pick_row([(2, row(予定日時="2026/10/05 21:00"))], self.now)
        self.assertIsNone(r)

    def test_review_and_hold_rows_are_not_posted(self):
        for st in (store.ST_REVIEW, store.ST_HOLD_PREFIX + "x", store.ST_SKIPPED):
            r, _, _ = sched.pick_row([(2, row(ステータス=st))], self.now)
            self.assertIsNone(r, st)

    def test_error_row_is_retried_same_day(self):
        r, _, _ = sched.pick_row([(2, row(ステータス=store.ST_ERROR_PREFIX + "x"))], self.now)
        self.assertEqual(r, 2)


class GuardTest(unittest.TestCase):
    def test_availability_without_manual_info_is_held(self):
        r = row(本文="今日の15時に空きが出ました")
        self.assertIn("空き情報", sched.guard(r, [(2, r)]))

    def test_reused_ig_post_is_held(self):
        r = row()
        done = row(ステータス=store.ST_POSTED)
        self.assertIn("投稿済み", sched.guard(r, [(2, done), (3, r)]))

    def test_ok(self):
        r = row()
        self.assertEqual(sched.guard(r, [(2, r)]), "")


class PostFlowTest(unittest.TestCase):
    """cmd_post: 公開成功時は最初に「投稿済み」を書き、失敗時は「エラー：」を書く。"""

    def setUp(self):
        os.environ["THREADS_ACCESS_TOKEN"] = "x"
        os.environ["THREADS_USER_ID"] = "1"
        self.tab = mock.MagicMock()
        self.tab.rows.return_value = [(2, row(予定日時=datetime.now(JST).strftime("%Y/%m/%d %H:%M")))]
        p = mock.patch.object(store, "open_posts", return_value=self.tab)
        p.start()
        self.addCleanup(p.stop)
        lt = mock.patch.object(api, "list_my_threads", return_value=[])
        self.list_threads = lt.start()
        self.addCleanup(lt.stop)
        n = mock.patch.object(sched, "_notify")
        n.start()
        self.addCleanup(n.stop)

    def test_success_marks_posted_first(self):
        with mock.patch.object(api, "post_thread", return_value="999") as pt, \
                mock.patch.object(api, "get_post", side_effect=Exception("boom")):
            self.assertEqual(sched.cmd_post(dry_run=False), 0)
        pt.assert_called_once()
        first = self.tab.update.call_args_list[0][0][1]
        self.assertEqual(first["ステータス"], store.ST_POSTED)
        self.assertEqual(first["Threads投稿ID"], "999")
        self.assertEqual(first["修正あり"], "N")
        # permalink 取得の失敗で「エラー：」を書いていない
        for c in self.tab.update.call_args_list:
            self.assertFalse(str(c[0][1].get("ステータス", "")).startswith(store.ST_ERROR_PREFIX))

    def test_failure_marks_error(self):
        with mock.patch.object(api, "post_thread", side_effect=api.ThreadsAPIError("bad")):
            self.assertEqual(sched.cmd_post(dry_run=False), 1)
        sched._notify.assert_called_once()
        fields = self.tab.update.call_args_list[0][0][1]
        self.assertTrue(fields["ステータス"].startswith(store.ST_ERROR_PREFIX))

    def test_dry_run_does_not_post_or_write(self):
        with mock.patch.object(api, "post_thread") as pt:
            sched.cmd_post(dry_run=True)
        pt.assert_not_called()
        self.tab.update.assert_not_called()

    def test_edited_text_is_recorded(self):
        self.tab.rows.return_value = [(2, row(予定日時=datetime.now(JST).strftime("%Y/%m/%d %H:%M"),
                                              本文="直した本文"))]
        with mock.patch.object(api, "post_thread", return_value="999"), \
                mock.patch.object(api, "get_post", return_value={"permalink": "u"}):
            sched.cmd_post(dry_run=False)
        self.assertEqual(self.tab.update.call_args_list[0][0][1]["修正あり"], "Y")

    def test_already_on_threads_is_not_reposted(self):
        self.list_threads.return_value = [{"id": "555", "text": "首と肩の話"}]
        with mock.patch.object(api, "post_thread") as pt:
            self.assertEqual(sched.cmd_post(dry_run=False), 0)
        pt.assert_not_called()
        fields = self.tab.update.call_args_list[0][0][1]
        self.assertEqual((fields["ステータス"], fields["Threads投稿ID"]), (store.ST_POSTED, "555"))

    def test_disabled_without_token(self):
        os.environ.pop("THREADS_ACCESS_TOKEN")
        with mock.patch.object(api, "post_thread") as pt:
            self.assertEqual(sched.cmd_post(dry_run=False), 0)
        pt.assert_not_called()


class ApiFlowTest(unittest.TestCase):
    def setUp(self):
        os.environ["THREADS_ACCESS_TOKEN"] = "x"
        os.environ["THREADS_USER_ID"] = "1"

    def test_carousel_creates_children_then_parent(self):
        calls = []

        def fake_create(media_type, **kw):
            calls.append((media_type, kw.get("is_carousel_item", False), kw.get("topic_tag", "")))
            return f"c{len(calls)}"
        with mock.patch.object(api, "create_container", side_effect=fake_create), \
                mock.patch.object(api, "wait_until_ready"), \
                mock.patch.object(api, "publish", return_value="T1") as pub:
            out = api.post_thread("本文", [{"type": "IMAGE", "url": "a"}, {"type": "IMAGE", "url": "b"}],
                                  "美容")
        self.assertEqual(out, "T1")
        self.assertEqual([c[0] for c in calls], ["IMAGE", "IMAGE", "CAROUSEL"])
        self.assertTrue(calls[0][1] and calls[1][1])
        self.assertEqual(calls[2][2], "美容")
        pub.assert_called_once_with("c3")

    def test_publish_is_not_retried(self):
        with mock.patch.object(api, "_post", return_value={"id": "9"}) as p:
            api.publish("c1")
        self.assertEqual(p.call_args.kwargs.get("attempts"), 1)

    def test_metric_value_shapes(self):
        self.assertEqual(api._metric_value({"name": "likes", "values": [{"value": 3}]}), 3)
        self.assertEqual(api._metric_value({"name": "likes", "total_value": {"value": 5}}), 5)
        self.assertEqual(api._metric_value({"name": "clicks", "link_total_values":
                                            [{"value": 2, "link_url": "u"}]}), {"u": 2})


class InsightsTest(unittest.TestCase):
    def setUp(self):
        os.environ["THREADS_ACCESS_TOKEN"] = "x"
        os.environ["THREADS_USER_ID"] = "1"

    def _rows(self, hours_ago, **kw):
        from datetime import timedelta
        posted = (datetime.now(JST) - timedelta(hours=hours_ago)).strftime("%Y/%m/%d %H:%M")
        return row(ステータス=store.ST_POSTED, Threads投稿ID="T1", 投稿日時_実際=posted, **kw)

    def run_insights(self, rows, user=None):
        tab, daily = mock.MagicMock(), mock.MagicMock()
        tab.rows.return_value = rows
        daily.rows.return_value = []
        with mock.patch.object(store, "open_posts", return_value=tab), \
                mock.patch.object(store, "open_daily", return_value=daily), \
                mock.patch.object(api, "get_media_insights", return_value={"likes": 3, "replies": 1}), \
                mock.patch.object(api, "get_user_insights", return_value=user or {
                    "views": [{"date": "2026-10-05", "value": 12}], "followers_count": 40,
                    "likes": 5, "clicks": {"https://x": 2}}), \
                mock.patch.object(sched, "_notify"):
            code = sched.cmd_insights(dry_run=False)
        return code, tab, daily

    def test_24h_snapshot_is_saved_once(self):
        _, tab, _ = self.run_insights([(2, self._rows(30))])
        fields = tab.update.call_args[0][1]
        self.assertIn("指標_24h", fields)
        self.assertNotIn("指標_7d", fields)
        _, tab, _ = self.run_insights([(2, self._rows(30, 指標_24h='{"likes":1}'))])
        self.assertNotIn("指標_24h", tab.update.call_args[0][1])

    def test_7d_snapshot(self):
        _, tab, _ = self.run_insights([(2, self._rows(24 * 7 + 2, 指標_24h='{"likes":1}'))])
        self.assertIn("指標_7d", tab.update.call_args[0][1])

    def test_old_posts_are_not_tracked(self):
        _, tab, _ = self.run_insights([(2, self._rows(24 * 20))])
        tab.update.assert_not_called()

    def test_daily_row_records_profile_views_and_followers(self):
        _, _, daily = self.run_insights([])
        rec = daily.append.call_args[0][0][0]
        self.assertEqual((rec["profile_views"], rec["followers_count"]), (12, 40))
        self.assertIn("https://x", rec["clicks"])

    def test_profile_views_take_latest_day_only(self):
        _, _, daily = self.run_insights([], user={
            "views": [{"date": "2026-10-02", "value": 13}, {"date": "2026-10-03", "value": 5}],
            "followers_count": 169})
        self.assertEqual(daily.append.call_args[0][0][0]["profile_views"], 5)

    def test_user_insights_failure_notifies(self):
        tab, daily = mock.MagicMock(), mock.MagicMock()
        tab.rows.return_value = []
        with mock.patch.object(store, "open_posts", return_value=tab), \
                mock.patch.object(api, "get_user_insights", side_effect=api.ThreadsAPIError("expired")), \
                mock.patch.object(sched, "_notify") as notify:
            self.assertEqual(sched.cmd_insights(dry_run=False), 1)
        notify.assert_called_once()

    def test_unavailable_metric_falls_back_one_by_one(self):
        def fake_get(path, params):
            if "," in params["metric"] or params["metric"] == "views":
                raise api.ThreadsAPIError("metric not supported")
            return {"data": [{"name": params["metric"], "values": [{"value": 2}]}]}
        with mock.patch.object(api, "_get", side_effect=fake_get):
            m = api.get_media_insights("T1")
        self.assertEqual(m["likes"], 2)
        self.assertIn("views", m["_missing"])


class ContainerTestCommandTest(unittest.TestCase):
    def test_never_publishes(self):
        os.environ["THREADS_ACCESS_TOKEN"] = "x"
        os.environ["THREADS_USER_ID"] = "1"
        original = api.publish
        try:
            with mock.patch.object(api, "_post", return_value={"id": "c1"}) as post, \
                    mock.patch.object(api, "_get", return_value={"status": "FINISHED"}), \
                    mock.patch.object(api, "wait_until_ready"), \
                    mock.patch.object(sched, "resolve_media", return_value=[
                        {"type": "IMAGE", "url": "a"}, {"type": "IMAGE", "url": "b"}]):
                code = sched.cmd_container_test("tests/fixtures/threads_week_sample.json", 0)
            self.assertEqual(code, 0)
            paths = [c.args[0] for c in post.call_args_list]
            self.assertTrue(paths and all(p.endswith("/threads") for p in paths), paths)
            self.assertFalse(any("threads_publish" in p for p in paths))
        finally:
            api.publish = original


class LineNotifyLimitTest(unittest.TestCase):
    """Threads の LINE 通知は、人の対応が必要なときだけ・1人に・同じ通知は1日1回・月上限つき。"""

    def setUp(self):
        os.environ["THREADS_ACCESS_TOKEN"] = "x"
        os.environ["THREADS_USER_ID"] = "1"
        os.environ["LINE_USER_ID_SHUNSUKE"] = "U_SHUNSUKE"
        os.environ["LINE_USER_ID_MIKI"] = "U_MIKI"
        self.tmp = tempfile.mkdtemp()
        p = mock.patch.object(notifier, "LEDGER_FILE", os.path.join(self.tmp, "log.json"))
        p.start()
        self.addCleanup(p.stop)
        # LINE への送信だけを差し替える（Instagram と共用の line_notify の中身はそのまま）
        s = mock.patch.object(line_notify, "send_line_message", return_value=True)
        self.send = s.start()
        self.addCleanup(s.stop)
        self.tab = mock.MagicMock()
        self.tab.rows.return_value = [(2, row(予定日時=datetime.now(JST).strftime("%Y/%m/%d %H:%M")))]
        o = mock.patch.object(store, "open_posts", return_value=self.tab)
        o.start()
        self.addCleanup(o.stop)
        lt = mock.patch.object(api, "list_my_threads", return_value=[])
        lt.start()
        self.addCleanup(lt.stop)

    # 1. 正常投稿では通知しない
    def test_success_sends_no_line(self):
        with mock.patch.object(api, "post_thread", return_value="999"), \
                mock.patch.object(api, "get_post", return_value={"permalink": "u"}):
            self.assertEqual(sched.cmd_post(dry_run=False), 0)
        self.send.assert_not_called()

    # 2. 投稿失敗では通知する（1人だけ）
    def test_failure_sends_one_line_to_one_person(self):
        with mock.patch.object(api, "post_thread", side_effect=api.ThreadsAPIError("bad")):
            sched.cmd_post(dry_run=False)
        self.send.assert_called_once()
        self.assertEqual(self.send.call_args.kwargs["user_ids"], ["U_SHUNSUKE"])
        self.assertIn("投稿に失敗", self.send.call_args.args[0])

    # 3. 要確認では通知する
    def test_hold_sends_line(self):
        self.tab.rows.return_value = [(2, row(予定日時=datetime.now(JST).strftime("%Y/%m/%d %H:%M"),
                                              本文="今日の15時に空きが出ました"))]
        with mock.patch.object(api, "post_thread") as pt:
            self.assertEqual(sched.cmd_post(dry_run=False), 1)
        pt.assert_not_called()
        self.send.assert_called_once()
        self.assertIn("要確認", self.send.call_args.args[0])

    # 4. 同じ通知は同じ日に1回だけ（失敗が同じ日に3回起きても1通）
    def test_same_failure_three_times_same_day_sends_once(self):
        with mock.patch.object(api, "post_thread", side_effect=api.ThreadsAPIError("bad")):
            for _ in range(3):
                sched.cmd_post(dry_run=False)
        self.assertEqual(self.send.call_count, 1)

    def test_dedupe_is_per_day_and_per_target(self):
        from datetime import timedelta
        d1 = datetime(2026, 10, 6, 8, 30, tzinfo=JST)
        f = lambda t, now: notifier.notify(notifier.POST_FAILED, t, "x", now=now)  # noqa: E731
        self.assertTrue(f("2026/10/06 08:00", d1))
        self.assertFalse(f("2026/10/06 08:00", d1 + timedelta(hours=4)))   # 同じ日・同じ対象
        self.assertTrue(f("2026/10/06 12:30", d1))                         # 対象が違う
        self.assertTrue(f("2026/10/06 08:00", d1 + timedelta(days=1)))     # 翌日
        self.assertEqual(self.send.call_count, 3)

    def test_monthly_cap(self):
        base = datetime(2026, 11, 1, 9, 0, tzinfo=JST)
        sent = sum(notifier.notify(notifier.HELD, f"t{i}", "x", now=base) for i in range(notifier.MONTHLY_CAP + 5))
        self.assertEqual(sent, notifier.MONTHLY_CAP)
        self.assertIn("上限", self.send.call_args_list[-1].args[0])
        # 翌月はまた送れる
        self.assertTrue(notifier.notify(notifier.HELD, "t0", "x", now=datetime(2026, 12, 1, 9, 0, tzinfo=JST)))

    def test_unreadable_ledger_still_notifies(self):
        with open(notifier.LEDGER_FILE, "w") as f:
            f.write("{broken")
        self.assertTrue(notifier.notify(notifier.POST_FAILED, "a", "x"))

    def test_failed_send_is_not_recorded(self):
        self.send.return_value = False
        self.assertFalse(notifier.notify(notifier.POST_FAILED, "a", "x"))
        self.send.return_value = True
        self.assertTrue(notifier.notify(notifier.POST_FAILED, "a", "x"))

    # Instagram 側の LINE 通知処理を変えていない
    def test_instagram_line_functions_untouched(self):
        import importlib
        fresh = importlib.reload(line_notify)  # Threads の処理を通った後でも、中身は元のまま
        self.assertEqual(sorted(fresh._get_user_ids()), ["U_MIKI", "U_SHUNSUKE"])
        import inspect
        src = inspect.getsource(notifier)
        self.assertNotIn("line_notify._", src)            # 内部関数に触れない
        self.assertNotRegex(src, r"line_notify\.\w+\s*=")   # 差し替えない

    def test_message_is_prefixed_and_redacted(self):
        notifier.notify(notifier.POST_FAILED, "a", "url?access_token=x123456789&")
        msg = self.send.call_args.args[0]
        self.assertTrue(msg.startswith("【Threads】"))
        self.assertNotIn("x123456789", msg)


def _fake_book(index, exists=True):
    ws = mock.MagicMock()
    ws.index = index
    ws.title = store.POSTS_TAB
    ws.row_values.return_value = store.POSTS_HEADERS
    book = mock.MagicMock()
    if exists:
        book.worksheet.return_value = ws
    else:
        book.worksheet.side_effect = gspread.exceptions.WorksheetNotFound("x")
        book.add_worksheet.return_value = ws
    return book, ws


class FirstTabGuardTest(unittest.TestCase):
    # 5. Threads用タブが1枚目なら止まる
    def test_first_tab_stops(self):
        for opener in (store.open_posts, store.open_daily):
            book, ws = _fake_book(0)
            ws.row_values.return_value = store.DAILY_HEADERS if opener is store.open_daily else store.POSTS_HEADERS
            with mock.patch.object(store, "_open_spreadsheet", return_value=book):
                with self.assertRaises(store.UnsafeTabError) as cm:
                    opener()
            self.assertIn("1枚目", str(cm.exception))
            ws.update.assert_not_called()          # 見出しも書かない
            ws.update_cells.assert_not_called()

    # 6. 通常の位置なら動く
    def test_normal_position_works(self):
        book, ws = _fake_book(3)
        with mock.patch.object(store, "_open_spreadsheet", return_value=book):
            tab = store.open_posts()
        self.assertIs(tab.ws, ws)
        book.worksheet.assert_called_once_with(store.POSTS_TAB)   # タブ名で開く

    def test_create_appends_at_end_without_index(self):
        book, ws = _fake_book(3, exists=False)
        ws.row_values.return_value = []
        with mock.patch.object(store, "_open_spreadsheet", return_value=book):
            store.open_posts(create=True)
        kwargs = book.add_worksheet.call_args.kwargs
        self.assertNotIn("index", kwargs)    # 位置を指定しない＝末尾に追加
        self.assertEqual(kwargs["title"], store.POSTS_TAB)

    def test_created_tab_at_first_position_stops_before_writing(self):
        book, ws = _fake_book(0, exists=False)
        ws.row_values.return_value = []
        with mock.patch.object(store, "_open_spreadsheet", return_value=book):
            with self.assertRaises(store.UnsafeTabError):
                store.open_posts(create=True)
        ws.update.assert_not_called()

    def test_store_never_opens_by_position(self):
        import ast
        src = open("threads_store.py", encoding="utf-8").read()
        names = {n.attr for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Attribute)}
        self.assertFalse(names & {"sheet1", "get_worksheet", "worksheets"}, names & {"sheet1", "get_worksheet", "worksheets"})

    def test_unsafe_tab_is_not_swallowed_as_missing_tab(self):
        self.assertFalse(issubclass(store.UnsafeTabError, RuntimeError))
        self.assertTrue(issubclass(store.TabNotFoundError, RuntimeError))

    def test_scheduler_stops_and_notifies_on_first_tab(self):
        os.environ["THREADS_ACCESS_TOKEN"] = "x"
        os.environ["THREADS_USER_ID"] = "1"
        for cmd in (sched.cmd_post, sched.cmd_insights):
            with mock.patch.object(store, "open_posts", side_effect=store.UnsafeTabError(store.POSTS_TAB)), \
                    mock.patch.object(sched, "_notify") as notify, \
                    mock.patch.object(api, "post_thread") as pt, \
                    mock.patch.object(api, "get_user_insights") as gu:
                self.assertEqual(cmd(dry_run=False), 1)
            pt.assert_not_called()
            gu.assert_not_called()
            self.assertEqual(notify.call_args.args[0], notifier.TAB_UNSAFE)

    def test_missing_tab_exits_quietly(self):
        os.environ["THREADS_ACCESS_TOKEN"] = "x"
        os.environ["THREADS_USER_ID"] = "1"
        with mock.patch.object(store, "open_posts", side_effect=store.TabNotFoundError("none")), \
                mock.patch.object(sched, "_notify") as notify:
            self.assertEqual(sched.cmd_post(dry_run=False), 0)
        notify.assert_not_called()


class RedactTest(unittest.TestCase):
    """通信エラーのメッセージにトークン入りURLが含まれても、外に出る文字列には残さない。"""

    def setUp(self):
        os.environ["THREADS_ACCESS_TOKEN"] = "SECRET_TOKEN_123"
        os.environ["THREADS_USER_ID"] = "1"

    def test_connection_error_is_redacted(self):
        import requests

        def boom(url, params=None, **kw):
            req = requests.Request("GET", url, params=params).prepare()
            raise requests.exceptions.ConnectionError(f"Max retries exceeded with url: {req.path_url}")
        with mock.patch("requests.get", side_effect=boom):
            with self.assertRaises(api.ThreadsAPIError) as cm:
                api.get_post("123")
        self.assertNotIn("SECRET_TOKEN_123", str(cm.exception))
        self.assertIn("access_token=***", str(cm.exception))

    def test_post_failure_message_written_to_sheet_is_redacted(self):
        tab = mock.MagicMock()
        tab.rows.return_value = [(2, row(予定日時=datetime.now(JST).strftime("%Y/%m/%d %H:%M")))]
        with mock.patch.object(store, "open_posts", return_value=tab), \
                mock.patch.object(api, "list_my_threads", return_value=[]), \
                mock.patch.object(sched, "_notify") as notify, \
                mock.patch.object(api, "post_thread",
                                  side_effect=RuntimeError("url?access_token=SECRET_TOKEN_123&x=1")):
            sched.cmd_post(dry_run=False)
        written = str(tab.update.call_args_list) + str(notify.call_args_list)
        self.assertNotIn("SECRET_TOKEN_123", written)


if __name__ == "__main__":
    unittest.main()
