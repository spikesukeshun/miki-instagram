"""動画解析のテスト。合成した動画で、回転・fps・HDR・音声・切れ目・暗い区間・動きの量を確かめる。

  /usr/bin/python3 -m unittest reels.tests.test_media_analysis
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from reels import media_analysis as M

HAS_FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", *args], check=True)


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg が無い環境では動画解析のテストをしない")
class MediaAnalysisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="reels-media-"))
        d = cls.tmp
        # 横長60fps・音あり → 表示回転90°のコピー
        _ffmpeg("-f", "lavfi", "-i", "testsrc2=s=640x360:r=60:d=3",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(d / "landscape.mp4"))
        _ffmpeg("-display_rotation", "90", "-i", str(d / "landscape.mp4"), "-c", "copy", str(d / "rotated.mp4"))
        # HLG（HDR）タグ付き・無音トラック
        _ffmpeg("-f", "lavfi", "-i", "testsrc2=s=360x640:r=30:d=2",
                "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                "-c:v", "libx264", "-pix_fmt", "yuv420p10le",
                "-x264-params", "colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc",
                "-c:a", "aac", "-t", "2", str(d / "hdr.mp4"))
        # 3秒の静止画（ノイズあり）→ 真っ黒2秒 → 動く柄2秒（切れ目が2回）
        _ffmpeg("-f", "lavfi", "-i", "color=c=0xC89664:s=360x640:r=30:d=3",
                "-f", "lavfi", "-i", "color=c=black:s=360x640:r=30:d=2",
                "-f", "lavfi", "-i", "testsrc2=s=720x1280:r=30:d=2",
                "-filter_complex",
                "[0:v]noise=alls=3:allf=t,format=yuv420p[a];[1:v]format=yuv420p[b];"
                "[2:v]crop=360:640:x='mod(t*300,360)':y='mod(t*500,640)',format=yuv420p[c];"
                "[a][b][c]concat=n=3:v=1",
                "-c:v", "libx264", str(d / "mixed.mp4"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_orientation_rotation_fps_audio(self):
        plain = M.probe_video(self.tmp / "landscape.mp4")
        self.assertEqual((plain["width"], plain["height"], plain["orientation"]), (640, 360, "横"))
        self.assertAlmostEqual(plain["fps"], 60.0, places=1)
        self.assertTrue(plain["has_audio"])

        rotated = M.probe_video(self.tmp / "rotated.mp4")
        self.assertEqual(abs(rotated["rotation"]), 90)
        self.assertEqual((rotated["width"], rotated["height"], rotated["orientation"]), (360, 640, "縦"))

    def test_hdr_and_silent_audio(self):
        meta = M.probe_video(self.tmp / "hdr.mp4")
        self.assertTrue(meta["hdr"])
        self.assertEqual(meta["hdr_type"], "HLG")
        levels = M.audio_levels(self.tmp / "hdr.mp4")
        self.assertTrue(levels["silent"])

    def test_cuts_dark_segments_and_motion(self):
        path = self.tmp / "mixed.mp4"
        meta = M.probe_video(path)
        stats = M.frame_stats(path)
        cuts = M.detect_cuts(stats)
        # 静止→黒（3秒）と 黒→動く柄（5秒）の2か所
        self.assertEqual(len(cuts), 2, cuts)
        self.assertAlmostEqual(cuts[0], 3.0, delta=0.15)
        self.assertAlmostEqual(cuts[1], 5.0, delta=0.15)

        segments = M.usable_segments(stats, meta["duration"])
        # 黒い2秒は使える区間に入らない
        self.assertEqual(len(segments), 2, segments)
        self.assertLess(segments[0]["end"], 3.0)
        self.assertGreater(segments[1]["start"], 5.0)
        self.assertEqual(segments[0]["motion_class"], "static")
        self.assertIn(segments[1]["motion_class"], ("medium", "high"))

    def test_analyze_video_writes_sheet_and_poster(self):
        out = self.tmp / "out"
        result = M.analyze_video(self.tmp / "mixed.mp4", out, title="テスト")
        self.assertTrue((out / "contact_sheet.jpg").exists())
        self.assertTrue((out / "poster.jpg").exists())
        self.assertTrue((out / "analysis.json").exists())
        # 暗い秒は代表フレームに選ばれない
        dark = {s["second"] for s in result["seconds"] if s["dark"]}
        self.assertNotIn(result["representative_second"], dark)
        self.assertEqual(len(list((out / "frames").glob("*.jpg"))), 7)


class MotionClassTest(unittest.TestCase):
    def test_thresholds_are_ordered(self):
        self.assertEqual(M.motion_class(0.0), "static")
        self.assertEqual(M.motion_class(M.MOTION_STATIC_MAX), "low")
        self.assertEqual(M.motion_class(M.MOTION_LOW_MAX), "medium")
        self.assertEqual(M.motion_class(M.MOTION_MEDIUM_MAX), "high")
        self.assertEqual(M.format_segments([]), "なし")


if __name__ == "__main__":
    unittest.main()
