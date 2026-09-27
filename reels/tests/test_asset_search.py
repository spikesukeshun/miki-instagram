"""素材探索・不足素材・撮影依頼のテスト（台帳は作り物の行で代用する）。

  /usr/bin/python3 -m unittest reels.tests.test_asset_search
"""

from __future__ import annotations

import unittest

from reels.asset_search import search_cut, shooting_request_text, shooting_requests
from reels.tests.test_plan_validate import base_plan


def row(asset_id, kind, subjects, *, people="お客様・施術者", face="なし", consent="書面",
        usable="使用可", segments="0.3-8.0秒(中)", actions="", framing="", usage=""):
    return {"asset_id": asset_id, "kind": kind, "file_name": f"{asset_id}.mov", "subjects": subjects,
            "actions": actions, "framing": framing, "people": people, "face": face, "consent": consent,
            "usable": usable, "segments": segments if kind == "動画" else "", "usage_history": usage}


class AssetSearchTest(unittest.TestCase):
    def test_ready_video_is_assigned_with_segment(self):
        cut = base_plan()["cuts"][0]
        res = search_cut(cut, [row("V-back", "動画", "背中,手元")])
        self.assertEqual(res.status, "割当OK")
        self.assertEqual(res.chosen.asset_id, "V-back")
        self.assertGreaterEqual(res.chosen.segment["duration"], 2.5)
        self.assertIsNone(res.missing)

    def test_unconfirmed_consent_is_not_auto_assigned(self):
        cut = base_plan()["cuts"][0]
        rows = [row("V-back", "動画", "背中", consent="未確認", usable="未確認"),
                row("P-back", "写真", "背中")]
        res = search_cut(cut, rows)
        # 実写は確認待ちの候補に回り、代替の写真で作る
        self.assertEqual(res.status, "代替で対応")
        self.assertEqual(res.used_type, "photo_motion")
        self.assertEqual([c.asset_id for c in res.pending_candidates], ["V-back"])
        self.assertIsNotNone(res.missing)
        self.assertTrue(res.missing["has_pending"])

    def test_wrong_subject_face_or_short_clip_is_rejected(self):
        cut = base_plan()["cuts"][0]
        rows = [row("V-leg", "動画", "脚,手元"),
                row("V-face", "動画", "背中", face="正面"),
                row("V-short", "動画", "背中", segments="0.3-1.5秒(中)"),
                row("V-still", "動画", "背中", segments="0.3-8.0秒(静止)")]
        res = search_cut(cut, rows)
        self.assertIn("被写体が合わない", res.rejected["V-leg"])
        self.assertIn("顔の写り", res.rejected["V-face"])
        self.assertIn("区間がない", res.rejected["V-short"])
        self.assertIn("区間がない", res.rejected["V-still"])
        # 写真も無いので文字主体で作る。実写は不足素材に載る
        self.assertEqual(res.used_type, "text_card")
        self.assertIsNotNone(res.missing)

    def test_blank_face_is_rejected_when_face_is_restricted(self):
        # 顔の写りが未記入の素材を、顔を出さない条件のカットに入れない（Codexレビューの指摘）
        cut = base_plan()["cuts"][0]
        res = search_cut(cut, [row("V-noface", "動画", "背中", face="")])
        self.assertEqual(res.rejected["V-noface"], "顔の写りの欄が未記入")
        self.assertIsNone(res.chosen)

    def test_unusable_and_untagged_assets_are_skipped(self):
        cut = base_plan()["cuts"][0]
        rows = [row("V-ng", "動画", "背中", usable="使用不可"), row("V-untagged", "動画", "")]
        res = search_cut(cut, rows)
        self.assertEqual(res.rejected["V-ng"], "使用不可")
        self.assertEqual(res.rejected["V-untagged"], "被写体のタグが未記入")

    def test_same_hands_but_different_action_is_not_assigned(self):
        # 2026-09-17 に実際に起きた誤割当：カウンセリングの手元のカットに、ソルトを混ぜる準備の手元が入った
        cut = base_plan()["cuts"][0]
        cut["material"]["requirements"] = {"subjects_all": ["カウンセリング"], "subjects_any": ["手元"],
                                           "actions_any": ["説明", "書く"], "min_seconds": 2.0}
        rows = [row("V-salt", "動画", "手元,ソルト,道具", actions="準備,混ぜる", people="施術者の手元")]
        res = search_cut(cut, rows)
        self.assertIn("必須の被写体", res.rejected["V-salt"])
        self.assertIsNone(res.chosen)

    def test_action_is_required_when_specified(self):
        # シェービングのカットに、同じ「背中」のオイル施術を入れない
        cut = base_plan()["cuts"][0]
        cut["material"]["requirements"] = {"subjects_any": ["うなじ", "背中"], "actions_any": ["シェービング"],
                                           "people_allowed": ["お客様・施術者"], "min_seconds": 2.0}
        rows = [row("V-oil", "動画", "背中,手元", actions="オイルトリートメント,施術")]
        res = search_cut(cut, rows)
        self.assertIn("動作が合わない", res.rejected["V-oil"])
        rows.append(row("V-shave", "動画", "うなじ,背中", actions="シェービング"))
        self.assertEqual(search_cut(cut, rows).chosen.asset_id, "V-shave")

    def test_composite_photo_is_used_only_when_requested(self):
        # 2枚組（比較用）の写真が普通の写真として割り当てられると、BAの誤用になる
        cut = base_plan()["cuts"][1]
        rows = [row("P-pair", "写真", "背中", framing="2枚組,背面")]
        res = search_cut(cut, rows)
        self.assertEqual(res.rejected["P-pair"], "2枚組（比較用）の写真")
        cut["material"]["requirements"]["framing_any"] = ["2枚組"]
        self.assertEqual(search_cut(cut, rows).chosen.asset_id, "P-pair")

    def test_assume_confirmed_never_revives_unusable_assets(self):
        from reels.asset_search import assume_confirmed
        rows = assume_confirmed([row("V-a", "動画", "背中", consent="未確認", usable="未確認"),
                                 row("V-b", "動画", "背中", consent="未確認", usable="使用不可")])
        self.assertEqual((rows[0]["consent"], rows[0]["usable"]), ("書面", "使用可"))
        self.assertEqual((rows[1]["consent"], rows[1]["usable"]), ("未確認", "使用不可"))

    def test_shooting_request_groups_and_mentions_rules(self):
        plan = base_plan()
        results = [search_cut(c, []) for c in plan["cuts"]]
        requests = shooting_requests(plan, results)
        # c01 と c03 は同じ「背中」の撮影なので1件にまとめる。写真カット（c02）は撮影依頼に入らない
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["cuts"], ["c01", "c03"])
        # 長い方のカット（c03 の4秒）に前後の余白を足した長さで頼む
        self.assertEqual(requests[0]["record_seconds"], 7)
        text = shooting_request_text(plan, requests)
        self.assertIn("縦向き", text)
        self.assertIn("HDRビデオ", text)
        # 撮影分の投入先は、今ある動画と同じ Drive の「動画」フォルダ（受け取り方法を増やさない）
        self.assertIn("「instagram投稿素材 ＞ 動画」フォルダ", text)
        self.assertIn("書面での同意", text)

    def test_different_required_subjects_are_separate_requests(self):
        # 動作が同じでも、必ず写すもの（背中／お腹）が違えば別の撮影として頼む
        plan = base_plan()
        plan["cuts"][0]["material"]["requirements"] = {"subjects_all": ["背中"], "actions_any": ["施術"],
                                                       "min_seconds": 2.0}
        plan["cuts"][2]["material"]["requirements"] = {"subjects_all": ["お腹"], "actions_any": ["施術"],
                                                       "min_seconds": 2.0}
        requests = shooting_requests(plan, [search_cut(c, []) for c in plan["cuts"]])
        self.assertEqual([r["cuts"] for r in requests], [["c01"], ["c03"]])
        self.assertEqual([r["subjects_all"] for r in requests], [["背中"], ["お腹"]])

    def test_customer_asset_needs_consent_even_without_consent_min(self):
        # 2026-09-18 レビュー: カットに consent_min を書き忘れても、お客様が写った素材は自動割当しない
        cut = base_plan()["cuts"][1]
        cut["material"]["requirements"] = {"subjects_any": ["背中"]}
        rows = [row("P-cust", "写真", "背中", people="お客様", face="正面", consent="未確認", usable="使用可")]
        res = search_cut(cut, rows)
        self.assertNotEqual(res.status, "割当OK")
        self.assertIsNone(res.chosen)
        self.assertEqual([c.asset_id for c in res.pending_candidates], ["P-cust"])
        self.assertIn("同意", res.pending_candidates[0].pending[0])
        # 顔が写る素材は書面まで求める
        self.assertIn("書面", res.pending_candidates[0].pending[0])

    def test_salon_photo_without_customer_is_still_assigned(self):
        # お客様が写っていない素材（施術室など）まで確認待ちにしない
        cut = base_plan()["cuts"][1]
        cut["material"]["requirements"] = {"subjects_any": ["施術室"]}
        rows = [row("P-room", "写真", "施術室,店内", people="なし", face="なし", consent="不要", usable="使用可")]
        self.assertEqual(search_cut(cut, rows).chosen.asset_id, "P-room")

    def test_required_subject_is_matched_exactly(self):
        # 「顔」が「洗顔の手元」に部分一致してしまわないこと
        cut = base_plan()["cuts"][0]
        cut["material"]["requirements"] = {"subjects_all": ["顔"], "min_seconds": 2.0}
        res = search_cut(cut, [row("V-wash", "動画", "洗顔の手元,手元")])
        self.assertIn("必須の被写体", res.rejected["V-wash"])


if __name__ == "__main__":
    unittest.main()
