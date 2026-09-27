"""Drive「動画」フォルダの動画を、コマを抜いて目視確認する。

パラパラ漫画型（post_style: "flipbook"）のコマ送りに使える動画かどうかは、
ファイル名では分からない。preview_drive_images.py と同じ考え方で、
「素材が無い／使えない」と判断する前に必ず実物のコマを見るためのツール。

使い方:
    python3 preview_drive_videos.py
        → 全動画から1コマずつ抜いた一覧シート（drive_video_preview.png）

    python3 preview_drive_videos.py --file IMG_8133.mov --frames 12
        → その動画のコマ送りシート（drive_video_frames_<名前>.png）

シートのラベルには秒数が入る。目視で選んだコマの秒数を、そのまま
content.json のコマ抽出（--at）に写せるようにするため。
"""
import argparse
import os
import sys
import tempfile

from drive_manager import _get_service, download_drive_file
from preview_drive_images import tile_to_sheet
from video_frames import extract_frames, probe_duration, sample_times, window_times

# 「動画」フォルダのID。
# drive_folders.json には入れない。fetch_posts_data.py の
# build_drive_current_state() が drive_folders.json の全キーを舐め、その出力を
# reclassify_drive.py が読んで trash_file()（Driveのゴミ箱へ）まで走る経路があり、
# 画像の整理を意図した仕組みに動画を巻き込む理由が無いため。
VIDEO_FOLDER_ID = "1ONxJjMoTV5CIoHATJ6A4Zf6Fvdyiej3P"


def list_drive_videos() -> list:
    """「動画」フォルダ内の動画ファイル一覧（ページネーション対応・全件）"""
    service = _get_service()
    query = (f"'{VIDEO_FOLDER_ID}' in parents "
             f"and mimeType contains 'video/' and trashed=false")
    files, page_token = [], None
    while True:
        kwargs = dict(q=query, fields="nextPageToken, files(id, name, size)",
                      pageSize=100, orderBy="name")
        if page_token:
            kwargs["pageToken"] = page_token
        res = service.files().list(**kwargs).execute()
        files += res.get("files", [])
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    print(f"  Drive「動画」: {len(files)}本")
    return files


def overview_sheet() -> str:
    """全動画から1コマずつ抜いて一覧にする。"""
    videos = list_drive_videos()
    if not videos:
        print("動画がありません")
        return ""

    paths, labels = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for v in videos:
            local = os.path.join(tmp, v["id"])
            print(f"  取得中: {v['name']}")
            if not download_drive_file(v["id"], local):
                continue
            try:
                duration = probe_duration(local)
            except RuntimeError as e:
                print(f"  スキップ: {e}")
                continue
            times = sample_times(duration, 1)
            frames = extract_frames(local, times, tmp, prefix=f"o{v['id'][:6]}")
            if not frames:
                continue
            paths.append(frames[0][1])
            labels.append(f"{v['name']}  ({duration:.1f}s)")

        out = tile_to_sheet(paths, labels, "drive_video_preview.png")

    if out:
        print("動きの幅が大きく、速すぎない動画を選ぶこと"
              "（9コマに落とすのでコマ送りは粗くなる）。")
        print("決めたら: python3 preview_drive_videos.py --file <名前> --frames 12")
    return out


def frames_sheet(name: str, count: int, at: float = -1.0,
                 window: float = 1.6, save_frames: str = "") -> str:
    """1本の動画からコマ送りシートを作る。

    at を指定すると、その秒から window 秒の「区間内」を等分する（パラパラ漫画用）。
    at を省略すると動画全体を等分する（どんな場面が入っているかの下見用）。
    """
    videos = list_drive_videos()
    matched = [v for v in videos if v["name"] == name]
    if not matched:
        near = [v["name"] for v in videos if name.lower() in v["name"].lower()]
        print(f"「{name}」が見つかりません。"
              + (f" 候補: {' / '.join(near[:5])}" if near else ""))
        return ""
    if len(matched) > 1:
        # 同名の重複アップロードがある（IMG_8133.mov が実際に2件ある）。
        # どちらを見ているか分からないまま進むと、本番で別の実体を掴みうる。
        print(f"  ※「{name}」は同名が{len(matched)}件あります"
              f"（id: {' / '.join(v['id'][:8] for v in matched)}）。先頭を使います。")
    video = matched[0]

    with tempfile.TemporaryDirectory() as tmp:
        local = os.path.join(tmp, video["id"])
        print(f"  取得中: {video['name']}")
        if not download_drive_file(video["id"], local):
            return ""
        duration = probe_duration(local)
        if at >= 0:
            times = window_times(at, window, count, duration)
        else:
            times = sample_times(duration, count)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in video["name"])
        # コマを残すなら一時ディレクトリではなく実ディレクトリへ書く。
        # これが無いと「preview で秒数を選ぶ → content.json の local_path に書く」
        # の間の一歩が手作業になり、手順書にあってコードに無い状態になる。
        frame_dir = save_frames or tmp
        frames = extract_frames(local, times, frame_dir,
                                prefix=safe[:24] if save_frames else "f",
                                name_by_time=bool(save_frames))
        # 秒数はパスと一緒に返る（失敗したコマを飛ばしてもラベルがズレない）
        labels = [f"{t}s" for t, _ in frames]
        out = tile_to_sheet([p for _, p in frames], labels,
                            f"drive_video_frames_{safe}.png")

    if out:
        if at >= 0:
            # 動画の長さで切り詰められることがあるので、要求値ではなく実際の秒数を出す
            first, last = times[0], times[-1]
            step = (last - first) / max(1, len(times) - 1)
            print(f"  動画の長さ: {duration:.1f}秒 / {first}〜{last}秒を{len(times)}コマ"
                  f"（コマ間 {step:.2f}秒）")
            if abs(first - at) > 0.01:
                print(f"  ※ --at {at} は動画の長さを超えるため {first}秒に詰めました")
        else:
            print(f"  動画の長さ: {duration:.1f}秒 / 全体を{count}コマ"
                  f"（コマ間 {duration / max(1, count - 1):.2f}秒）")
            print("  ※ 全体を等分したコマは、パラパラ漫画としては繋がらない。"
                  "場面の下見用。動かすなら --at で区間を指定する")
        print("  コマ送りとして成立しているかを見る。"
              "使うならラベルの秒数を content.json 側に写すこと。")
        if save_frames:
            print("  保存したコマ（ファイル名に秒数が入っています）:")
            for _, path in frames:
                print(f"    {path}")
            print(f"  content.json には")
            print(f"    \"bg_strategy\": \"local\", \"local_path\": \"<上のパス>\"")
            print(f"  と書く（案B・flipbook）。")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Drive「動画」フォルダの動画をコマで目視確認する")
    parser.add_argument("--file", default="", help="1本だけコマ送りにする（Driveのファイル名）")
    parser.add_argument("--frames", type=int, default=12, help="コマ数（default 12）")
    parser.add_argument("--at", type=float, default=-1.0,
                        help="この秒から --window 秒の区間を等分する（パラパラ漫画用）。"
                             "省略すると動画全体を等分（場面の下見用）")
    parser.add_argument("--window", type=float, default=1.6,
                        help="--at からの区間の長さ・秒（default 1.6）")
    parser.add_argument("--save-frames", dest="save_frames", default="",
                        help="コマをこのディレクトリに残す（例: backgrounds）。"
                             "content.json の local_path から参照する")
    args = parser.parse_args()

    out = (frames_sheet(args.file, args.frames, args.at, args.window,
                        args.save_frames)
           if args.file else overview_sheet())
    sys.exit(0 if out else 1)
