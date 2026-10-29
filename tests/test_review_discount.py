"""20%OFF の対象外（ギフトチケット・ペアコース）の校閲チェックのテスト。

  python3 -m unittest tests/test_review_discount.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from review_post import (  # noqa: E402
    CAPTION_CTA_LINE,
    CTA_DISCOUNT_EXCLUSION,
    check_caption_has_cta,
    check_discount_exclusion_on_slides,
)


class CaptionExclusionTest(unittest.TestCase):
    def test_note_right_after_cta_line_passes(self):
        ok, _ = check_caption_has_cta(f"本文\n\n{CAPTION_CTA_LINE}\n{CTA_DISCOUNT_EXCLUSION}\n\nDMから")
        self.assertTrue(ok)

    def test_missing_note_fails(self):
        ok, msg = check_caption_has_cta(f"本文\n\n{CAPTION_CTA_LINE}\n\nDMから")
        self.assertFalse(ok)
        self.assertIn(CTA_DISCOUNT_EXCLUSION, msg)

    def test_note_in_another_paragraph_fails(self):
        ok, _ = check_caption_has_cta(f"{CTA_DISCOUNT_EXCLUSION}\n\n{CAPTION_CTA_LINE}\n\nDMから")
        self.assertFalse(ok)

    def test_note_line_with_extra_text_fails(self):
        ok, _ = check_caption_has_cta(f"{CAPTION_CTA_LINE}\n{CTA_DISCOUNT_EXCLUSION}。詳しくはDMで\n")
        self.assertFalse(ok)


class SlideExclusionTest(unittest.TestCase):
    def _result(self, slide):
        return check_discount_exclusion_on_slides([slide])

    def test_price_highlight_without_note_fails(self):
        res = self._result({"type": "price", "highlight": {"label": "インスタ限定 MIKI指名20%OFF"},
                            "notes": ["指名料 ＋1,000円"]})
        self.assertEqual([ok for ok, _ in res], [False])

    def test_note_in_notes_passes(self):
        res = self._result({"type": "price", "highlight": {"label": "20%OFF"},
                            "notes": [CTA_DISCOUNT_EXCLUSION]})
        self.assertEqual([ok for ok, _ in res], [True])

    def test_fullwidth_mention_is_detected(self):
        res = self._result({"type": "text", "text": "ＶＩＰは２０％ＯＦＦです"})
        self.assertEqual([ok for ok, _ in res], [False])

    def test_spaced_and_katakana_mentions_are_detected(self):
        for text in ("VIPは20% OFFです", "VIPは20％オフです", "20%off"):
            res = self._result({"type": "text", "text": text})
            self.assertEqual([ok for ok, _ in res], [False], text)

    def test_cta_and_file_names_are_ignored(self):
        res = check_discount_exclusion_on_slides([
            {"type": "cta", "title": "MIKI指名 Instagram限定20%OFF\n（VIPコースのみ）"},
            {"type": "text", "text": "割引の話なし", "reuse_filename": "20%OFF.jpg"},
        ])
        self.assertEqual(res, [])


if __name__ == "__main__":
    unittest.main()
