"""校閲を通った content.json の「前回版」を保存・読み出す。

修正依頼でスライドだけ直してキャプションを直し忘れると、スライドとキャプションで
言っていることが食い違ったまま投稿される（2026-10-04、スライド3を
「当日は控えましょう」に変えたのにキャプションが「いつもより控えめに」のままだった）。
review_post.py がこの前回版と比べて、スライドから消えた言い回しが
キャプションに残っていないかを検査する。

保存先は git の共通ディレクトリ（.git/content_baselines/）。worktree をまたいでも
同じ投稿枠の前回版が見えるようにするため（投稿は別の worktree で作られることが多い）。
git 管理外なのでコミットには乗らない。

前回版の読み書きに失敗しても校閲そのものは止めない（比較スキップ扱い）。
"""
import json
import os
import re
import subprocess
from datetime import datetime

BASELINE_DIRNAME = "content_baselines"

# content_2026-08-10-2200.json のような日付入りファイル名から投稿日時を読む。
# fullmatch で使う。backup_content_2026-04-12-2100.json のような別物を拾わないため。
# create_post.py の投稿日時解決もこれを使う（同じ規則を2か所に書かない）。
CONTENT_FILENAME_DT_RE = re.compile(
    r"content_(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})\.json"
)


def _baseline_dir() -> str:
    """保存先。git の共通ディレクトリが分からなければ空文字（保存も比較もしない）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        common = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"], cwd=here,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return ""
    if not common:
        return ""
    common = common if os.path.isabs(common) else os.path.join(here, common)
    return os.path.join(common, BASELINE_DIRNAME)


def slot_slug(content: dict, content_path: str = "") -> str:
    """投稿枠の slug（YYYY-MM-DD-HHMM）。

    create_post.py の投稿日時解決と同じ順で決める: post_datetime → ファイル名 →
    _generated_dir（_generated_dir は別日時で使い回した時に古い値が残るので最後）。
    """
    raw = str(content.get("post_datetime") or "").strip()
    if raw:
        try:
            return datetime.strptime(raw, "%Y/%m/%d %H:%M").strftime("%Y-%m-%d-%H%M")
        except ValueError:
            pass
    m = CONTENT_FILENAME_DT_RE.fullmatch(os.path.basename(content_path or ""))
    if m:
        y, mo, d, h, mi = m.groups()
        return f"{y}-{mo}-{d}-{h}{mi}"
    return str(content.get("_generated_dir") or "").strip()


def load_baseline(slug: str):
    d = _baseline_dir()
    if not slug or not d:
        return None
    try:
        with open(os.path.join(d, f"{slug}.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def save_baseline(content: dict, content_path: str = "") -> str:
    """校閲を通った版を前回版として保存する。保存先パスを返す（保存しなければ空文字）。

    保存するのは content_YYYY-MM-DD-HHMM.json という本番の名前で、中の post_datetime
    （あれば）とも日時が合う時だけ。試作（proto-*）や content.json、/tmp のコピーを
    校閲しただけで、全 worktree 共通の前回版が上書きされないようにする。
    """
    m = CONTENT_FILENAME_DT_RE.fullmatch(os.path.basename(content_path or ""))
    if not m:
        return ""
    slug = slot_slug(content, content_path)
    y, mo, d_, h, mi = m.groups()
    if slug != f"{y}-{mo}-{d_}-{h}{mi}":
        return ""
    d = _baseline_dir()
    if not d:
        return ""
    try:
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"{slug}.json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError as e:
        print(f"⚠ 前回版の保存に失敗（校閲結果には影響なし）: {e}")
        return ""
    return path
