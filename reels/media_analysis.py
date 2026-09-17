"""動画・写真を解析する（フェーズ1）。ネットワークには触れない純粋な処理だけを置く。

動画から取るもの:
  長さ・縦横・回転・fps・HDR・音声の有無・代表フレーム・動きの量・使える区間
  ＋ 1秒ごとのコマを並べた一覧画像（素材の中身を人が確認するため）

動きの量は ffmpeg の場面変化スコア（前のコマとの差、0〜1）を
10fps・幅160pxに縮小した映像で測り、1秒ごとに平均したもの。
しきい値は 2026-09-17 に iPhone 17 の実写（手持ち 0.01〜0.05）と
合成の静止映像・カット入り映像で合わせた。
"""

from __future__ import annotations

import json
import re
import shutil
import statistics
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat

# ---- 動きの解析 ----
MOTION_SAMPLE_FPS = 10
MOTION_SAMPLE_WIDTH = 160
# 1コマの変化がこれ以上なら「場面の切れ目（ハードカット）」とみなす
CUT_SCORE = 0.30
# 1秒平均の変化量による区分（静止 < 少 < 中 < 多）
MOTION_STATIC_MAX = 0.004
MOTION_LOW_MAX = 0.012
MOTION_MEDIUM_MAX = 0.030
MOTION_LABELS = {"static": "静止", "low": "少", "medium": "中", "high": "多"}
# 平均輝度（0〜255）がこれ未満の秒は「暗すぎる」
DARK_LUMA = 30.0

# ---- 使える区間 ----
# 撮影の開始・停止ボタンを押した瞬間は手ブレしやすいので端を除く
EDGE_TRIM_SECONDS = 0.3
# 切れ目の前後も同じ理由で少し除く
CUT_MARGIN_SECONDS = 0.1
MIN_SEGMENT_SECONDS = 1.0

# ---- 一覧画像 ----
SHEET_COLUMNS = 6
SHEET_TILE_WIDTH = 240
POSTER_WIDTH = 1080

HDR_TRANSFERS = {"smpte2084": "HDR10（PQ）", "arib-std-b67": "HLG"}
VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".avi", ".mkv", ".webm", ".3gp"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}

_FONT_CANDIDATES = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
]


class MediaAnalysisError(RuntimeError):
    pass


def _font(size: int) -> ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _run(cmd: list, *, text: bool = True) -> subprocess.CompletedProcess:
    res = subprocess.run(cmd, capture_output=True, text=text)
    if res.returncode != 0:
        tail = (res.stderr or "")[-600:] if text else ""
        raise MediaAnalysisError(f"コマンドが失敗しました: {' '.join(map(str, cmd[:6]))} …\n{tail}")
    return res


def media_kind(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in IMAGE_EXTS:
        return "photo"
    return None


# =====================================================================
# 動画のメタデータ
# =====================================================================

def _parse_rate(rate: str | None) -> float | None:
    if not rate or rate in ("0/0", "0"):
        return None
    if "/" in rate:
        num, den = rate.split("/", 1)
        try:
            return float(num) / float(den) if float(den) else None
        except ValueError:
            return None
    try:
        return float(rate)
    except ValueError:
        return None


def orientation_label(width: int, height: int) -> str:
    if abs(width - height) <= max(width, height) * 0.02:
        return "正方形"
    return "縦" if height > width else "横"


def probe_video(path: Path) -> dict:
    """ffprobe で動画の基本情報を取る。回転を反映した「見た目の縦横」も返す。"""
    res = _run(["ffprobe", "-v", "error", "-print_format", "json",
                "-show_format", "-show_streams", str(path)])
    data = json.loads(res.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and not s.get("disposition", {}).get("attached_pic")), None)
    if video is None:
        raise MediaAnalysisError(f"映像のストリームがありません: {path.name}")

    rotation = 0
    for side in video.get("side_data_list", []) or []:
        if "rotation" in side:
            rotation = int(round(float(side["rotation"])))
    if not rotation and video.get("tags", {}).get("rotate"):
        rotation = int(video["tags"]["rotate"])
    rotation = ((rotation + 180) % 360) - 180  # -180〜179 に正規化

    width, height = int(video["width"]), int(video["height"])
    if abs(rotation) == 90:
        display_w, display_h = height, width
    else:
        display_w, display_h = width, height

    transfer = video.get("color_transfer")
    dolby = any("DOVI" in (side.get("side_data_type") or "")
                for side in video.get("side_data_list", []) or [])
    if dolby:
        hdr_type = "Dolby Vision"
    else:
        hdr_type = HDR_TRANSFERS.get(transfer or "")

    # 再生できる音声（コーデック名が付いているもの）だけを数える。
    # iPhone は空間オーディオ用に中身を読めない音声トラックを別に持つことがある
    audio_streams = [s for s in streams
                     if s.get("codec_type") == "audio" and s.get("codec_name")]
    fmt = data.get("format", {})
    duration = float(fmt.get("duration") or video.get("duration") or 0.0)
    tags = fmt.get("tags", {}) or {}

    return {
        "duration": round(duration, 3),
        "coded_width": width,
        "coded_height": height,
        "rotation": rotation,
        "width": display_w,
        "height": display_h,
        "orientation": orientation_label(display_w, display_h),
        "fps": round(_parse_rate(video.get("avg_frame_rate")) or 0.0, 3),
        "fps_nominal": _parse_rate(video.get("r_frame_rate")),
        "variable_fps": (_parse_rate(video.get("avg_frame_rate")) or 0)
                        != (_parse_rate(video.get("r_frame_rate")) or 0),
        "codec": video.get("codec_name"),
        "pix_fmt": video.get("pix_fmt"),
        "color_transfer": transfer,
        "hdr": hdr_type is not None,
        "hdr_type": hdr_type,
        "has_audio": bool(audio_streams),
        "audio_channels": audio_streams[0].get("channels") if audio_streams else 0,
        "creation_time": tags.get("creation_time"),
        "device": tags.get("com.apple.quicktime.model"),
    }


def audio_levels(path: Path) -> dict | None:
    """最初の音声トラックの平均・最大音量（dB）。音声が無ければ None。"""
    res = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0",
         "-af", "volumedetect", "-vn", "-f", "null", "-"],
        capture_output=True, text=True)
    if res.returncode != 0:
        return None
    mean = re.search(r"mean_volume:\s*(-?[\d.]+|-inf) dB", res.stderr)
    peak = re.search(r"max_volume:\s*(-?[\d.]+|-inf) dB", res.stderr)
    if not mean or not peak:
        return None

    def num(m):
        return float("-inf") if m.group(1) == "-inf" else float(m.group(1))

    mean_db, max_db = num(mean), num(peak)
    return {
        "mean_db": mean_db,
        "max_db": max_db,
        # 最大音量が -50dB 未満なら実質無音（無音トラックが付いているだけ）
        "silent": max_db < -50.0,
    }


# =====================================================================
# 動きの量と使える区間
# =====================================================================

@dataclass
class FrameStat:
    t: float
    scene: float
    luma: float


def frame_stats(path: Path) -> list:
    """縮小した映像の各コマについて、前のコマとの差（scene）と平均輝度を取る。"""
    vf = (f"fps={MOTION_SAMPLE_FPS},scale={MOTION_SAMPLE_WIDTH}:-2,signalstats,"
          "select='gte(scene\\,0)',metadata=print:file=-")
    res = _run(["ffmpeg", "-hide_banner", "-v", "error", "-i", str(path),
                "-map", "0:v:0", "-vf", vf, "-an", "-f", "null", "-"])
    stats = []
    current = None
    for line in res.stdout.splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            if current:
                stats.append(current)
            current = FrameStat(t=float(m.group(1)), scene=0.0, luma=0.0)
            continue
        if current is None:
            continue
        m = re.match(r"lavfi\.(scene_score|signalstats\.YAVG)=([\d.]+)", line.strip())
        if m:
            if m.group(1) == "scene_score":
                current.scene = float(m.group(2))
            else:
                current.luma = float(m.group(2))
    if current:
        stats.append(current)
    if stats:
        # 最初のコマは比較対象が無いので差を0にする
        stats[0].scene = 0.0
    return stats


def motion_class(value: float) -> str:
    if value < MOTION_STATIC_MAX:
        return "static"
    if value < MOTION_LOW_MAX:
        return "low"
    if value < MOTION_MEDIUM_MAX:
        return "medium"
    return "high"


def detect_cuts(stats: list) -> list:
    return [round(s.t, 2) for s in stats[1:] if s.scene >= CUT_SCORE]


def _motion_frames(frames: list) -> list:
    """切れ目のコマは動きの量から除く（場面が変わっただけで動いたことにしない）。"""
    return [f.scene for f in frames if f.scene < CUT_SCORE]


def per_second(stats: list, duration: float) -> list:
    seconds = []
    total = int(duration) + (1 if duration - int(duration) > 1e-6 else 0)
    for sec in range(total):
        frames = [f for f in stats if sec <= f.t < sec + 1]
        if not frames:
            continue
        motion_values = _motion_frames(frames)
        motion = statistics.mean(motion_values) if motion_values else 0.0
        luma = statistics.mean(f.luma for f in frames)
        seconds.append({
            "second": sec,
            "motion": round(motion, 4),
            "motion_class": motion_class(motion),
            "luma": round(luma, 1),
            "dark": luma < DARK_LUMA,
            "has_cut": any(f.scene >= CUT_SCORE for f in frames),
        })
    return seconds


def _segment(frames: list, start: float, end: float) -> dict:
    values = _motion_frames([f for f in frames if start <= f.t < end])
    motion = statistics.mean(values) if values else 0.0
    return {
        "start": round(start, 2),
        "end": round(end, 2),
        "duration": round(end - start, 2),
        "motion": round(motion, 4),
        "motion_class": motion_class(motion),
    }


def usable_segments(stats: list, duration: float) -> list:
    """切れ目と暗い区間で区切り、1秒以上続く「使える区間」を返す。

    静止している区間も「使える区間」に含める（動きの量は区間ごとに記録するので、
    動きが必要なカットかどうかは設計図側の条件で判断する）。
    """
    if not stats:
        return []
    bounds = [0.0] + detect_cuts(stats) + [duration]
    segments = []
    for i in range(len(bounds) - 1):
        start = bounds[i] + (EDGE_TRIM_SECONDS if i == 0 else CUT_MARGIN_SECONDS)
        end = bounds[i + 1] - (EDGE_TRIM_SECONDS if i == len(bounds) - 2 else CUT_MARGIN_SECONDS)
        if end - start < MIN_SEGMENT_SECONDS:
            continue

        # 区間内を「明るいコマが続く所」に分ける。暗いコマで区切る
        frames = [f for f in stats if start <= f.t < end]
        run_start = None
        for idx, f in enumerate(frames):
            bright = f.luma >= DARK_LUMA
            if bright and run_start is None:
                run_start = max(start, f.t)
            if not bright and run_start is not None:
                if f.t - run_start >= MIN_SEGMENT_SECONDS:
                    segments.append(_segment(frames, run_start, f.t))
                run_start = None
        if run_start is not None and end - run_start >= MIN_SEGMENT_SECONDS:
            segments.append(_segment(frames, run_start, end))
    return segments


def summarize_motion(segments: list, seconds: list) -> dict:
    """台帳に載せる要約。使える区間の長さで重み付けした平均を代表値にする。"""
    if segments:
        total = sum(s["duration"] for s in segments)
        mean = sum(s["motion"] * s["duration"] for s in segments) / total
    elif seconds:
        mean = statistics.mean(s["motion"] for s in seconds)
    else:
        mean = 0.0
    return {"mean": round(mean, 4), "class": motion_class(mean)}


def format_segments(segments: list) -> str:
    """台帳の1セルに収まる書き方: 0.3-8.4秒(中) / 9.0-14.5秒(多)"""
    return " / ".join(
        f"{s['start']:.1f}-{s['end']:.1f}秒({MOTION_LABELS[s['motion_class']]})"
        for s in segments) or "なし"


# =====================================================================
# コマの書き出し・一覧画像・代表フレーム
# =====================================================================

def extract_frames_per_second(path: Path, out_dir: Path, width: int = SHEET_TILE_WIDTH * 2) -> list:
    """1秒ごとのコマを書き出す（ffmpeg は回転情報を反映して正しい向きで出す）。"""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    _run(["ffmpeg", "-hide_banner", "-v", "error", "-i", str(path), "-map", "0:v:0",
          "-vf", f"fps=1:round=down,scale={width}:-2", "-q:v", "4",
          str(out_dir / "%04d.jpg")])
    frames = sorted(out_dir.glob("*.jpg"))
    # fps=1:round=down は n 番目の出力が n-1 秒台のコマになる
    return [(i, p) for i, p in enumerate(frames)]


def sharpness(img: Image.Image) -> float:
    edges = img.convert("L").filter(ImageFilter.FIND_EDGES)
    return ImageStat.Stat(edges).var[0]


def pick_representative_second(frames: list, seconds: list, segments: list) -> int:
    """使える区間の中で、暗くなく最もくっきりしたコマの秒を選ぶ。"""
    usable = set()
    for seg in segments:
        usable.update(range(int(seg["start"]), int(seg["end"]) + 1))
    dark = {s["second"] for s in seconds if s["dark"]}
    best, best_score = None, -1.0
    for sec, path in frames:
        if usable and sec not in usable:
            continue
        if sec in dark:
            continue
        with Image.open(path) as im:
            score = sharpness(im)
        if score > best_score:
            best, best_score = sec, score
    if best is None:
        best = frames[len(frames) // 2][0] if frames else 0
    return best


def extract_poster(path: Path, second: float, out_path: Path, width: int = POSTER_WIDTH) -> Path:
    _run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-ss", f"{second:.2f}",
          "-i", str(path), "-map", "0:v:0", "-frames:v", "1",
          "-vf", f"scale={width}:-2", "-q:v", "3", str(out_path)])
    return out_path


_CLASS_COLORS = {
    "static": (160, 160, 160),
    "low": (120, 170, 220),
    "medium": (90, 170, 110),
    "high": (230, 140, 50),
}


def build_contact_sheet(title: str, info_lines: list, frames: list, seconds: list,
                        segments: list, out_path: Path) -> Path:
    """1秒ごとのコマを並べ、秒数・動きの量・使える区間を書き込んだ一覧画像。"""
    by_second = {s["second"]: s for s in seconds}
    in_segment = set()
    for seg in segments:
        for sec, _ in frames:
            if seg["start"] <= sec + 0.5 <= seg["end"]:
                in_segment.add(sec)

    tiles = []
    for sec, p in frames:
        im = ImageOps.contain(Image.open(p).convert("RGB"),
                              (SHEET_TILE_WIDTH, int(SHEET_TILE_WIDTH * 16 / 9)))
        tiles.append((sec, im))
    tile_h = max((im.height for _, im in tiles), default=SHEET_TILE_WIDTH)
    label_h = 44
    header_h = 40 + 30 * len(info_lines)
    graph_h = 120
    rows = max(1, -(-len(tiles) // SHEET_COLUMNS))
    width = SHEET_COLUMNS * (SHEET_TILE_WIDTH + 8) + 8
    height = header_h + graph_h + rows * (tile_h + label_h + 8) + 16

    sheet = Image.new("RGB", (width, height), (250, 248, 245))
    draw = ImageDraw.Draw(sheet)
    f_title, f_info, f_label = _font(26), _font(20), _font(18)
    draw.text((12, 10), title, fill=(30, 30, 30), font=f_title)
    for i, line in enumerate(info_lines):
        draw.text((12, 44 + i * 30), line, fill=(60, 60, 60), font=f_info)

    # 動きの量のグラフ（1秒ごと）と使える区間
    gx0, gy0 = 12, header_h + 10
    gw, gh = width - 24, graph_h - 50
    draw.rectangle([gx0, gy0, gx0 + gw, gy0 + gh], outline=(200, 200, 200))
    n = max(len(seconds), 1)
    bar_w = gw / n
    scale = max(MOTION_MEDIUM_MAX * 1.5, max((s["motion"] for s in seconds), default=0.0))
    for i, s in enumerate(seconds):
        h = gh * min(s["motion"] / scale, 1.0)
        color = (40, 40, 40) if s["dark"] else _CLASS_COLORS[s["motion_class"]]
        draw.rectangle([gx0 + i * bar_w + 1, gy0 + gh - h, gx0 + (i + 1) * bar_w - 1, gy0 + gh],
                       fill=color)
    total = seconds[-1]["second"] + 1 if seconds else 1
    for seg in segments:
        x1 = gx0 + gw * seg["start"] / total
        x2 = gx0 + gw * seg["end"] / total
        draw.rectangle([x1, gy0 + gh + 8, x2, gy0 + gh + 18], fill=(60, 140, 90))
    draw.text((gx0, gy0 + gh + 22),
              "棒＝1秒ごとの動きの量（灰:静止 青:少 緑:中 橙:多 黒:暗い）  緑の帯＝使える区間",
              fill=(90, 90, 90), font=f_label)

    top = header_h + graph_h
    for idx, (sec, im) in enumerate(tiles):
        col, row = idx % SHEET_COLUMNS, idx // SHEET_COLUMNS
        x = 8 + col * (SHEET_TILE_WIDTH + 8)
        y = top + row * (tile_h + label_h + 8)
        sheet.paste(im, (x + (SHEET_TILE_WIDTH - im.width) // 2, y))
        stat = by_second.get(sec)
        cls = MOTION_LABELS[stat["motion_class"]] if stat else "-"
        mark = "" if sec in in_segment else "  区間外"
        draw.rectangle([x, y + tile_h, x + SHEET_TILE_WIDTH, y + tile_h + label_h],
                       fill=(235, 245, 238) if sec in in_segment else (238, 232, 232))
        draw.text((x + 6, y + tile_h + 10), f"{sec}秒  動き:{cls}{mark}",
                  fill=(40, 40, 40), font=f_label)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, quality=85)
    return out_path


# =====================================================================
# まとめて解析する
# =====================================================================

def analyze_video(path: Path, out_dir: Path, title: str | None = None) -> dict:
    """動画1本を解析し、analysis.json・一覧画像・代表フレームを out_dir に書く。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = probe_video(path)
    levels = audio_levels(path) if meta["has_audio"] else None
    stats = frame_stats(path)
    seconds = per_second(stats, meta["duration"])
    segments = usable_segments(stats, meta["duration"])
    motion = summarize_motion(segments, seconds)

    frames = extract_frames_per_second(path, out_dir / "frames")
    rep_second = pick_representative_second(frames, seconds, segments)
    poster = extract_poster(path, rep_second + 0.5 if rep_second + 0.5 < meta["duration"] else rep_second,
                            out_dir / "poster.jpg")

    audio_text = "なし"
    if meta["has_audio"]:
        audio_text = "あり（ほぼ無音）" if levels and levels["silent"] else "あり"
    info_lines = [
        f"長さ {meta['duration']:.1f}秒 / {meta['width']}×{meta['height']}（{meta['orientation']}）"
        f" / 回転 {meta['rotation']}° / {meta['fps']:.2f}fps"
        + ("（可変）" if meta["variable_fps"] else ""),
        f"HDR {meta['hdr_type'] or 'なし'}"
        + ("（一覧画像の色は薄く見える場合あり）" if meta["hdr"] else "")
        + f" / 音声 {audio_text} / 動きの量 {MOTION_LABELS[motion['class']]}"
        + f" / 代表フレーム {rep_second}秒",
        f"使える区間 {format_segments(segments)}",
    ]
    sheet = build_contact_sheet(title or path.name, info_lines, frames, seconds, segments,
                                out_dir / "contact_sheet.jpg")

    result = {
        "kind": "video",
        "source_file": path.name,
        **meta,
        "audio_levels": levels,
        "audio_label": audio_text,
        "cuts": detect_cuts(stats),
        "seconds": seconds,
        "segments": segments,
        "segments_text": format_segments(segments),
        "motion": motion,
        "representative_second": rep_second,
        "poster": str(poster),
        "contact_sheet": str(sheet),
    }
    with open(out_dir / "analysis.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result


def open_image(path: Path) -> Image.Image:
    if path.suffix.lower() in (".heic", ".heif"):
        import pillow_heif  # 遅延 import（動画しか扱わない環境で必須にしない）
        pillow_heif.register_heif_opener()
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def analyze_photo(path: Path, out_dir: Path) -> dict:
    """写真1枚の縦横と代表画像（＝その写真の縮小版）を作る。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    img = open_image(path)
    poster = out_dir / "poster.jpg"
    preview = img.copy()
    preview.thumbnail((POSTER_WIDTH, POSTER_WIDTH * 2))
    preview.save(poster, quality=88)
    result = {
        "kind": "photo",
        "source_file": path.name,
        "width": img.width,
        "height": img.height,
        "orientation": orientation_label(img.width, img.height),
        "poster": str(poster),
        "contact_sheet": str(poster),
    }
    with open(out_dir / "analysis.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result
