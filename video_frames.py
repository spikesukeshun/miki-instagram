"""動画から等間隔のコマを切り出す。

deliver_reel.py の extract_thumbnail() がリールのサムネ用に1枚だけ抜くのに対し、
こちらはカルーセル（パラパラ漫画型）のために連番で複数枚抜く。
引数も目的も違うので同じ関数にはまとめていないが、ffmpeg の呼び方と
「先頭を避ける」理由は共通している。

deliver_reel.py:65-69 の理由コメント:
  冒頭がフェードインで始まる動画だと1フレーム目が白飛びするため、
  0秒ちょうどではなく少し後ろを使う。
ここでは先頭と末尾を等分に避けて、内側だけをサンプリングする。
"""
import os
import subprocess

# 先頭・末尾をこの割合ぶん捨ててからサンプリングする。
# 0秒ちょうどはフェードイン、末尾は手ブレや撮影終了の動きが入りやすい。
EDGE_MARGIN_RATIO = 0.08
# サンプリング範囲が極端に短い動画でも、最低これだけは先頭から離す（秒）
MIN_EDGE_SECONDS = 0.3


def probe_duration(video_path: str) -> float:
    """動画の長さ（秒）。取れなければ例外で止める。

    0.0 を返して先に進ませてはいけない。sample_times() が同じ秒数を count 個
    返し、「全部同じ絵で全部同じ秒数ラベル」のシートが正常終了で出てしまう。
    素材を目視するための道具が、最も誤解を招く形で成功を装うことになる。
    """
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", video_path]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        raise RuntimeError(
            "ffprobe が見つかりません（ffmpeg を入れてください）。"
        ) from None
    try:
        duration = float(res.stdout.strip())
    except ValueError:
        raise RuntimeError(
            f"動画の長さを取得できませんでした: {os.path.basename(video_path)}\n"
            f"  ffprobe: {res.stderr.strip()[:200]}"
        ) from None
    if duration <= 0:
        raise RuntimeError(
            f"動画の長さが 0 です: {os.path.basename(video_path)}（壊れている可能性）")
    return duration


def sample_times(duration: float, count: int) -> list:
    """動画の内側から count 個の秒数を等間隔で選ぶ。"""
    if count <= 0:
        return []
    if duration <= 0:
        raise ValueError("duration が 0 以下です（probe_duration() の戻りを確認）")
    edge = max(MIN_EDGE_SECONDS, duration * EDGE_MARGIN_RATIO)
    start = min(edge, duration / 2)
    end = max(duration - edge, start)
    if count == 1:
        return [round((start + end) / 2, 2)]
    step = (end - start) / (count - 1)
    return [round(start + step * i, 2) for i in range(count)]


def window_times(start: float, window: float, count: int,
                 duration: float = 0.0) -> list:
    """start から window 秒の「区間内」を count 個に等分した秒数を返す。

    パラパラ漫画は、動画全体を等分してはいけない。
    21秒の動画から9コマを等間隔で抜くとコマ間が2.2秒空き、手の位置も
    被写体の向きも毎回変わって、連続した動きに見えない（実際にそうなった）。
    滑らかに見せたいなら1〜2秒程度の短い区間から抜く。
    """
    if count <= 0:
        return []
    start = max(0.0, start)
    if duration > 0:
        start = min(start, max(0.0, duration - 0.1))
        window = min(window, max(0.1, duration - start))
    if count == 1:
        return [round(start, 2)]
    step = window / (count - 1)
    return [round(start + step * i, 2) for i in range(count)]


def extract_frames(video_path: str, times: list, out_dir: str,
                   prefix: str = "frame", quality: int = 2,
                   name_by_time: bool = False) -> list:
    """times（秒）の各地点を1枚ずつ静止画に書き出し、**(秒, パス) の組**を返す。

    パスだけを返してはいけない。失敗したコマを飛ばすと、呼び出し側が
    times[k] と frames[k] を突き合わせた瞬間にラベルがズレる。
    このツールは「ラベルの秒数をそのまま content.json に写す」のが存在理由なので、
    ズレはそのまま投稿のミスになる。秒数とパスは必ず一緒に運ぶ。

    ffmpeg は -ss を -i の前に置くとキーフレーム単位の高速シークになる。
    コマ送りでは指定秒との誤差が見た目に出るので、-i の後ろに置いて
    正確にシークさせる（1枚あたりは遅いが、抜くのは10枚程度）。
    """
    os.makedirs(out_dir, exist_ok=True)
    extracted = []
    for i, t in enumerate(times, 1):
        # name_by_time=True なら秒数をファイル名に入れる（例: IMG_9981_MOV_0044.00s.jpg）。
        # 連番だと、別の区間で抜き直した時に content.json が参照しているコマが
        # 黙って差し替わる。秒数入りなら区間ごとに別名になり、名前から抜き直しもできる。
        name = f"{prefix}_{t:07.2f}s.jpg" if name_by_time else f"{prefix}_{i:02d}.jpg"
        out_path = os.path.join(out_dir, name)
        cmd = ["ffmpeg", "-y", "-i", video_path, "-ss", str(t),
               "-frames:v", "1", "-q:v", str(quality), out_path]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError:
            raise RuntimeError(
                "ffmpeg が見つかりません（ffmpeg を入れてください）。") from None
        if res.returncode != 0 or not os.path.exists(out_path):
            print(f"  コマ抽出に失敗 ({os.path.basename(video_path)} @ {t}s)")
            continue
        extracted.append((t, out_path))
    return extracted
