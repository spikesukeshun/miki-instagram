"""この投稿で試すこと（trial）の校閲チェックのテスト。

  python3 -m unittest tests/test_trial.py
"""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from review_post import TRIAL_LEVERS, TRIAL_METRICS, check_trial  # noqa: E402

CONTENT = {
    "post_style": "standard",
    "slides": [
        {"type": "cover", "title": "冬の冷え\n何を飲めばいい？", "bg_strategy": "edit",
         "reuse_source": "drive", "reuse_theme": "menu", "reuse_filename": "Hamam bath.JPG"},
        {"type": "list", "title": "冷えさんの4つの習慣", "items": ["白湯", "腹巻き"]},
    ],
    "caption": "冬の冷えが気になる方へ\n\nMIKIです。",
    "hashtags": "#冷え対策 #エステ",
    "trial": {"tag": "cover-question", "lever": "cover", "what": "表紙を疑問形にする",
              "metric": "saved", "why": "10/05は保存2件",
              "where": "スライド1の表紙タイトル「冬の冷え何を飲めばいい？」"},
}


def with_trial(**changes):
    c = copy.deepcopy(CONTENT)
    c["trial"].update(changes)
    return c


def errors(content):
    return [m for ok, m in check_trial(content) if not ok]


class TrialTest(unittest.TestCase):
    def test_valid_trial_passes(self):
        self.assertEqual(errors(CONTENT), [])

    def test_missing_trial_fails(self):
        c = copy.deepcopy(CONTENT)
        del c["trial"]
        self.assertTrue(errors(c))

    def test_none_needs_reason(self):
        c = copy.deepcopy(CONTENT)
        c["trial"] = {"lever": "none", "why": "承認済みの投稿の差し替えのため"}
        self.assertEqual(errors(c), [])
        c["trial"] = {"lever": "none"}
        self.assertTrue(errors(c))

    def test_fixed_items_are_not_levers(self):
        # 投稿時刻・CTA・リールなど、投稿を作るときに変えられないものは項目に無い
        for lever in ("posting_time", "cta", "reel", "profile", "lp"):
            self.assertNotIn(lever, TRIAL_LEVERS)
            self.assertTrue(errors(with_trial(lever=lever)), lever)

    def test_fixed_items_in_what_fail(self):
        # lever が表紙でも、中身が投稿時刻・CTA なら止める
        for what in ("18時に投稿する", "金曜に出す", "CTAの前に一言足す", "LPへの誘導を足す"):
            self.assertTrue(errors(with_trial(what=what)), what)
        self.assertEqual(errors(with_trial(what="夜のスキンケアの話題にする")), [])

    def test_bad_tag_and_metric_fail(self):
        self.assertTrue(errors(with_trial(tag="Cover Question")))
        self.assertTrue(errors(with_trial(metric="lp")))
        self.assertNotIn("lp", TRIAL_METRICS)

    def test_where_needs_a_quote(self):
        self.assertTrue(errors(with_trial(where="スライド1の表紙タイトル")))

    def test_where_quote_must_exist_now(self):
        # 修正で表紙を変えたのに trial が古いまま → 止める
        c = copy.deepcopy(CONTENT)
        c["slides"][0]["title"] = "冬の冷え対策4選"
        msgs = errors(c)
        self.assertTrue(any("見つかりません" in m for m in msgs), msgs)

    def test_where_can_point_to_caption_hashtags_style_and_photo(self):
        for where in ("キャプション1行目「冬の冷えが気になる方へ」",
                      "ハッシュタグ「#冷え対策」",
                      "投稿の型「standard」",
                      "表紙の写真「Hamam bath.JPG」"):
            self.assertEqual(errors(with_trial(where=where)), [], where)


if __name__ == "__main__":
    unittest.main()
