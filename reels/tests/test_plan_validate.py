"""設計図の検査のテスト。

  /usr/bin/python3 -m unittest reels.tests.test_plan_validate
"""

from __future__ import annotations

import copy
import unittest

from reels.plan_validate import validate_plan


def base_plan() -> dict:
    """検査を通る最小の設計図（実写→写真→文字→CTA）。"""
    return {
        "schema_version": 1,
        "theme": "テスト",
        "slug": "test",
        "purpose": {"goal": "目的", "audience": "誰に", "viewer_takeaway": "残すこと", "desired_action": "行動"},
        "duration": {"class": "short", "target_seconds": 12, "reason": "理由"},
        "hook": {"text": "背中、見えてる？", "visual": "手元", "why_it_stops": "理由"},
        "script": [{"section": "hook", "text": "..."}, {"section": "cta", "text": "..."}],
        "voice_script": {"mode": "none", "lines": []},
        "cuts": [
            {
                "id": "c01", "start": 0.0, "end": 2.5, "role": "hook", "purpose": "つかむ",
                "visual": {"shows": "背中の施術の手元", "person_action": "手を肩甲骨に沿って流す",
                           "camera_move": "固定", "changes": [{"at": 0.2, "what": "テロップ"}]},
                "material": {
                    "preferred": "miki_video",
                    "requirements": {"subjects_any": ["背中"], "people_allowed": ["お客様・施術者"],
                                     "face_allowed": ["なし"], "min_seconds": 2.5, "motion_min": "low",
                                     "consent_min": "書面"},
                    "fallbacks": [{"type": "photo_motion", "requirements": {"subjects_any": ["背中"]},
                                   "photo_treatment": {"type": "push_in"}},
                                  {"type": "text_card"}],
                },
                "caption": [{"lines": ["背中、見えてる？"], "start": 0.2, "end": 2.3}],
                "narration": {"has": False},
            },
            {
                "id": "c02", "start": 2.5, "end": 5.0, "role": "problem", "purpose": "問題",
                "visual": {"shows": "背中の写真", "person_action": "なし", "camera_move": "寄る",
                           "changes": [{"at": 3.5, "what": "寄り終わり"}]},
                "material": {"preferred": "photo_motion",
                             "requirements": {"subjects_any": ["背中"]},
                             "photo_treatment": {"type": "push_in"},
                             "fallbacks": [{"type": "text_card"}]},
                "caption": [{"lines": ["自分では見えない"], "start": 2.6, "end": 4.9}],
                "narration": {"has": False},
            },
            {
                "id": "c03", "start": 5.0, "end": 9.0, "role": "main", "purpose": "本題",
                "visual": {"shows": "オイル施術", "person_action": "手で流す", "camera_move": "手持ちで追う",
                           "changes": [{"at": 7.0, "what": "テロップ切替"}]},
                "material": {"preferred": "miki_video",
                             "requirements": {"subjects_any": ["背中"], "min_seconds": 4, "consent_min": "書面"},
                             "fallbacks": [{"type": "text_card"}]},
                "caption": [{"lines": ["だからプロに"], "start": 5.1, "end": 6.9},
                            {"lines": ["任せてください"], "start": 7.0, "end": 8.9}],
                "narration": {"has": False},
            },
            {
                "id": "c04", "start": 9.0, "end": 12.0, "role": "cta", "purpose": "行動",
                "visual": {"shows": "店内", "person_action": "なし", "camera_move": "ゆっくりパン",
                           "changes": [{"at": 10.5, "what": "2行目"}]},
                "material": {"preferred": "text_card", "fallbacks": []},
                "caption": [{"lines": ["ご相談は", "プロフィールのリンクから"], "start": 9.1, "end": 11.9}],
                "narration": {"has": False},
            },
        ],
        "cta": {"message": "相談してほしい", "lp_guidance_text": "プロフィールのリンクから"},
        "cover": {"title_lines": ["背中の話"], "background_cut": "c01"},
        "open_questions": [],
    }


def codes(report, level=None):
    return [f.code for f in report.findings if level is None or f.level == level]


class PlanValidateTest(unittest.TestCase):
    def test_base_plan_passes(self):
        r = validate_plan(base_plan())
        self.assertEqual(codes(r, "error"), [], [f.text() for f in r.errors])
        self.assertEqual(r.metrics["cut_count"], 4)
        self.assertGreater(r.metrics["video_share"], 0.4)

    def test_photo_only_plan_is_rejected(self):
        plan = base_plan()
        for cut in plan["cuts"][:3]:
            cut["material"] = {"preferred": "photo_motion", "requirements": {"subjects_any": ["背中"]},
                               "photo_treatment": {"type": "pan"}, "fallbacks": [{"type": "text_card"}]}
        r = validate_plan(plan)
        self.assertIn("no_video_cut", codes(r, "error"))
        self.assertIn("photo_run", codes(r, "error"))

    def test_ai_video_cannot_be_preferred(self):
        plan = base_plan()
        plan["cuts"][1]["material"] = {"preferred": "ai_video", "requirements": {"subjects_any": ["光"]},
                                       "fallbacks": [{"type": "text_card"}]}
        self.assertIn("ai_video_preferred", codes(validate_plan(plan), "error"))

    def test_three_second_rule_is_warning_not_error(self):
        plan = base_plan()
        # 写真カットを5秒にして変化の予定を消す → 確認警告
        plan["cuts"][1]["end"] = 7.5
        plan["cuts"][1]["visual"]["changes"] = []
        plan["cuts"][1]["caption"] = [{"lines": ["自分では見えない"], "start": 2.6, "end": 3.9}]
        for cut in plan["cuts"][2:]:
            cut["start"] += 2.5
            cut["end"] += 2.5
            for c in cut["caption"]:
                c["start"] += 2.5
                c["end"] += 2.5
            for ch in cut["visual"]["changes"]:
                ch["at"] += 2.5
        plan["duration"]["target_seconds"] = 14.5
        r = validate_plan(plan)
        self.assertIn("change_gap", codes(r, "warn"))
        self.assertNotIn("change_gap", codes(r, "error"))

    def test_moving_video_long_take_is_ok(self):
        plan = base_plan()
        plan["cuts"][2]["visual"]["changes"] = []
        # 5.8秒でテロップが消えた後、9.0秒まで3.2秒間は実写の動きだけ
        plan["cuts"][2]["caption"] = [{"lines": ["だからプロに"], "start": 5.1, "end": 5.8}]
        r = validate_plan(plan)
        self.assertIn("long_take_ok", codes(r, "info"))
        self.assertNotIn("change_gap", codes(r))

    def test_caption_length_rules(self):
        plan = base_plan()
        plan["cuts"][0]["caption"][0]["lines"] = ["自分では見えない背中こそ丁寧に"]            # 15文字: OK
        plan["cuts"][1]["caption"][0]["lines"] = ["自分では見えない背中こそ丁寧にケア"]        # 17文字: 警告
        plan["cuts"][2]["caption"][0]["lines"] = ["自分では見えない背中こそ丁寧にケアしてあげたい"]  # 23文字: 差し戻し
        r = validate_plan(plan)
        self.assertIn("caption_long", codes(r, "warn"))
        self.assertIn("caption_too_long", codes(r, "error"))

    def test_numeric_claim_needs_source(self):
        plan = base_plan()
        plan["cuts"][1]["caption"][0]["lines"] = ["式の5日前までに"]
        self.assertIn("numeric_claim_without_source", codes(validate_plan(plan), "error"))
        plan["cuts"][1]["facts"] = [{"claim": "最後のエステは式の5日前まで", "source_type": "posted_content",
                                     "source": "content_2026-09-14-2200.json"}]
        self.assertNotIn("numeric_claim_without_source", codes(validate_plan(plan)))

    def test_before_after_requires_verified_case(self):
        plan = base_plan()
        plan["cuts"][1]["tags"] = ["before_after"]
        self.assertIn("ba_without_case", codes(validate_plan(plan), "error"))

        plan["cuts"][1]["material"]["requirements"]["ba_case_id"] = "BA-001"
        self.assertIn("ba_unverifiable", codes(validate_plan(plan), "error"))

        unverified = {"case_id": "BA-001", "status": "未確認", "written_consent": "未確認"}
        r = validate_plan(plan, ba_cases=[unverified], catalog_ids=set())
        self.assertIn("ba_not_verified", codes(r, "error"))

        verified = {"case_id": "BA-001", "customer": "A", "body_part": "背中", "before_asset": "P-1",
                    "after_asset": "P-2", "treatment": "背中のトリートメント", "allowed_text": "自分では見えない",
                    "written_consent": "あり", "verified_by": "MIKI", "verified_at": "2026-09-17", "status": "確認済み"}
        r = validate_plan(plan, ba_cases=[verified], catalog_ids={"P-1", "P-2"})
        self.assertNotIn("ba_not_verified", codes(r))
        self.assertNotIn("ba_text_not_allowed", codes(r))

        # 使ってよい説明文にない文を出すと差し戻し（写真と説明の食い違いを防ぐ）
        plan["cuts"][1]["caption"][0]["lines"] = ["輪郭がすっきり"]
        r = validate_plan(plan, ba_cases=[verified], catalog_ids={"P-1", "P-2"})
        self.assertIn("ba_text_not_allowed", codes(r, "error"))

    def test_cta_needs_lp_guidance_and_timeline_is_contiguous(self):
        plan = base_plan()
        plan["cuts"][3]["caption"][0]["lines"] = ["DMでご相談ください"]
        plan["cta"]["lp_guidance_text"] = ""
        plan["cuts"][2]["end"] = 8.5  # c03 と c04 の間にすき間
        r = validate_plan(plan)
        self.assertIn("cta_lp_guidance", codes(r, "error"))
        self.assertIn("cut_gap", codes(r, "error"))

    def test_guarantee_words_are_flagged(self):
        plan = base_plan()
        plan["cuts"][2]["caption"][1]["lines"] = ["必ずきれいになります"]
        r = validate_plan(plan)
        self.assertIn("guarantee_word", codes(r, "warn"))

    def test_forbidden_salon_name(self):
        plan = base_plan()
        plan["cover"]["title_lines"] = ["AMRTAの背中ケア"]
        self.assertIn("forbidden_word", codes(validate_plan(plan), "error"))

    def test_narration_must_match_voice_script(self):
        plan = base_plan()
        plan["cuts"][2]["narration"] = {"has": True, "line": "自分では見えない場所こそ、任せてください。"}
        r = validate_plan(plan)
        self.assertIn("voice_mode_none", codes(r, "error"))
        self.assertIn("narration_not_in_voice_script", codes(r, "error"))
        plan["voice_script"] = {"mode": "miki_voice_memo", "lines": [
            {"cut_id": "c03", "text": "自分では見えない場所こそ、任せてください。"}]}
        r = validate_plan(plan)
        self.assertNotIn("voice_mode_none", codes(r))
        self.assertNotIn("narration_not_in_voice_script", codes(r))


    def test_bad_cut_time_still_writes_design_and_result(self):
        # 秒数の書き間違いで設計図の出力ごと落ちると、どこを直せばよいか分からない（Codexレビューの指摘）
        import json
        import tempfile
        from pathlib import Path

        from reels.plan import run_check

        plan = base_plan()
        plan["cuts"][-1]["end"] = "12秒"
        plan["cuts"][0]["caption"][0]["start"] = None
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.json"
            path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            _, report, _, _ = run_check(path, offline=True)
            self.assertIn("cut_time", codes(report, "error"))
            self.assertIn("?秒", (Path(tmp) / "design.md").read_text(encoding="utf-8"))
            result = json.loads((Path(tmp) / "check_result.json").read_text(encoding="utf-8"))
            self.assertIn("cut_time", [e["code"] for e in result["errors"]])

    def test_photo_run_reports_whole_run(self):
        # 6枚続いた写真を「3つ続いています」と途中の数で報告しない
        plan = base_plan()
        for c in plan["cuts"]:
            c["material"] = {"preferred": "photo_motion", "requirements": {"subjects_any": ["背中"]},
                             "photo_treatment": {"type": "push_in"}, "fallbacks": [{"type": "text_card"}]}
        r = validate_plan(plan)
        runs = [f for f in r.errors if f.code == "photo_run"]
        self.assertEqual(len(runs), 1)
        self.assertIn(f"{len(plan['cuts'])}つ続いています", runs[0].message)
        self.assertEqual(r.metrics["longest_photo_run"], len(plan["cuts"]))

    def test_broken_shapes_are_reported_not_raised(self):
        # 配列のはずを文字列で書いても、例外ではなく ❌ として出る
        plan = base_plan()
        plan["cuts"][0]["caption"] = "テロップなし"
        plan["cuts"][1]["visual"]["changes"] = "寄る"
        plan["cuts"][2]["facts"] = {"claim": "..."}
        plan["script"] = "台本"
        r = validate_plan(plan)
        for code in ("caption_shape", "changes_shape", "facts_shape", "script_shape"):
            self.assertIn(code, codes(r, "error"))

    def test_numbers_outside_captions_need_a_source(self):
        # 台本・Hook・ボイス台本の数字も出典を求める（テロップだけ見ていると素通りする）
        plan = base_plan()
        plan["script"].append({"section": "main", "text": "最後のエステは式の5日前までに"})
        self.assertIn("numeric_claim_without_source", codes(validate_plan(plan), "error"))
        plan["cuts"][2]["facts"] = [{"claim": "最後のエステは式の5日前まで", "source_type": "posted_content",
                                     "source": "content_2026-09-14-2200.json"}]
        self.assertNotIn("numeric_claim_without_source", codes(validate_plan(plan)))

    def test_forbidden_word_is_case_insensitive_and_covers_script(self):
        plan = base_plan()
        plan["script"].append({"section": "detail", "text": "Amrta六本木のサロンです"})
        self.assertIn("forbidden_word", codes(validate_plan(plan), "error"))

    def test_guarantee_word_in_voice_script_is_warned(self):
        plan = base_plan()
        plan["voice_script"] = {"mode": "miki_voice_memo",
                                "lines": [{"cut_id": "c01", "text": "必ずきれいになります"}]}
        self.assertIn("guarantee_word", codes(validate_plan(plan), "warn"))


if __name__ == "__main__":
    unittest.main()
