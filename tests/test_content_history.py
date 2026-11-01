"""修正の記録（.git/content_history）のテスト。保存先は一時ディレクトリに差し替える。

  python3 -m unittest tests/test_content_history.py
"""
import copy
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import content_baseline as cb  # noqa: E402

JST = timezone(timedelta(hours=9))
PATH = "/somewhere/content_2026-11-09-2200.json"
V1 = {
    "post_datetime": "2026/11/09 22:00",
    "post_style": "standard",
    "slides": [
        {"type": "cover", "title": "指輪の写真で\n写る場所3つ", "reuse_filename": "a.JPG", "focus_y": 0.5},
        {"type": "text", "title": "1つ目", "text": "手の甲の乾燥", "reuse_filename": "b.JPG"},
        {"type": "list", "title": "まとめ", "items": ["保湿", "爪"], "reuse_filename": "c.JPG"},
    ],
    "caption": "指輪の写真が気になる花嫁様へ\n手元のケアの話\n\nMIKIです。本文",
    "hashtags": "#花嫁 #ブライダルエステ",
    "trial": {"tag": "cover-number", "lever": "cover"},
}


def at(day):
    return datetime(2026, 11, day, 9, 0, tzinfo=JST)


class DescribeChangesTest(unittest.TestCase):
    def test_no_change(self):
        self.assertEqual(cb.describe_changes(V1, copy.deepcopy(V1)), [])

    def test_labels(self):
        v = copy.deepcopy(V1)
        v["slides"][0]["title"] = "指輪の写真で写る場所4つ"
        v["slides"][1]["reuse_filename"] = "x.JPG"
        v["slides"][2]["focus_y"] = 0.3
        v["caption"] = "指輪の写真が心配な花嫁様へ\n手元のケアの話\n\nMIKIです。本文"
        v["hashtags"] = "#花嫁"
        self.assertEqual(cb.describe_changes(V1, v),
                         ["表紙タイトル", "スライド2の写真", "スライド3の写真の位置",
                          "キャプションの書き出し", "ハッシュタグ"])

    def test_inserting_a_slide_does_not_mark_the_rest_changed(self):
        v = copy.deepcopy(V1)
        v["slides"].insert(2, {"type": "text", "title": "2つ目", "text": "指の関節", "reuse_filename": "d.JPG"})
        self.assertEqual(cb.describe_changes(V1, v), ["スライド3を追加"])

    def test_caption_body_and_trial(self):
        v = copy.deepcopy(V1)
        v["caption"] += "追記"
        v["trial"] = {"lever": "none", "why": "差し替え"}
        self.assertEqual(cb.describe_changes(V1, v), ["キャプション本文", "試すこと"])


class RecordHistoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ[cb.STORE_DIR_ENV] = self.tmp.name

    def tearDown(self):
        os.environ.pop(cb.STORE_DIR_ENV, None)
        self.tmp.cleanup()

    def test_weekly_then_revisions(self):
        slug = "2026-11-09-2200"
        # 週次タスクの自動作成版（作成中の作り直しは修正に数えない）
        self.assertTrue(cb.record_history(None, V1, PATH, origin=cb.ORIGIN_WEEKLY, now=at(7)))
        v1b = copy.deepcopy(V1)
        v1b["hashtags"] += " #手元ケア"
        cb.record_history(V1, v1b, PATH, origin=cb.ORIGIN_WEEKLY, now=at(7))
        hist = cb.load_history(slug)
        self.assertEqual(hist["base"]["origin"], "weekly")
        self.assertEqual(hist["base"]["content"]["hashtags"], v1b["hashtags"])
        self.assertEqual(hist["events"], [])

        # ご本人の修正（依頼の文つき）
        v2 = copy.deepcopy(v1b)
        v2["slides"][0]["title"] = "指輪の写真で写る場所4つ"
        self.assertTrue(cb.record_history(v1b, v2, PATH, request="表紙を4つに", now=at(8)))
        # 依頼の文を付け忘れた修正も、差分から拾う
        v3 = copy.deepcopy(v2)
        v3["slides"][1]["reuse_filename"] = "y.JPG"
        cb.record_history(v2, v3, PATH, now=at(8))
        # 変更なしで校閲し直しただけなら足さない
        self.assertEqual(cb.record_history(v3, copy.deepcopy(v3), PATH, now=at(8)), "")

        events = cb.load_history(slug)["events"]
        self.assertEqual([e["changes"] for e in events], [["表紙タイトル"], ["スライド2の写真"]])
        self.assertEqual(events[0]["request"], "表紙を4つに")
        self.assertEqual(events[1]["request"], "")

    def test_slot_made_before_the_history_existed(self):
        v2 = copy.deepcopy(V1)
        v2["caption"] += "追記"
        cb.record_history(V1, v2, PATH, now=at(8))
        hist = cb.load_history("2026-11-09-2200")
        self.assertEqual(hist["base"]["origin"], "unknown")
        self.assertEqual([e["changes"] for e in hist["events"]], [["キャプション本文"]])

    def test_non_production_file_is_not_recorded(self):
        self.assertEqual(cb.record_history(None, V1, "/tmp/content.json", now=at(7)), "")
        self.assertEqual(cb.record_history(None, V1, "/tmp/content_2026-11-10-2200.json", now=at(7)), "")
        self.assertIsNone(cb.load_history("2026-11-09-2200"))

    def test_store_override_is_used_for_baselines_too(self):
        self.assertTrue(cb.save_baseline(V1, PATH).startswith(self.tmp.name))
        self.assertEqual(cb.list_slugs(), ["2026-11-09-2200"])


if __name__ == "__main__":
    unittest.main()
