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

修正の記録（.git/content_history/）も同じ場所に置く。前回版は最新の1版で上書きされるので、
自動作成のあとにご本人が何を直したかが残らなかった（ダッシュボードが修正を把握できなかった）。
校閲を通るたびに前回版との差分を「どこが変わったか」の一覧にして追記する。
"""
import difflib
import json
import os
import re
import subprocess
import unicodedata
from datetime import datetime, timedelta, timezone

BASELINE_DIRNAME = "content_baselines"
HISTORY_DIRNAME = "content_history"
# テストで本物の .git/content_* を汚さないための差し替え口（値は2つの保存先の親ディレクトリ）
STORE_DIR_ENV = "MIKI_CONTENT_STORE_DIR"
JST = timezone(timedelta(hours=9))
# 修正の記録で「誰の版か」。週次タスクは review_post.py --origin weekly で校閲する
ORIGIN_WEEKLY = "weekly"
ORIGIN_CHAT = "chat"
ORIGINS = (ORIGIN_CHAT, ORIGIN_WEEKLY)
# 修正依頼の文は長すぎる分を切って保存する（記録が肥大化しないように）
MAX_REQUEST_CHARS = 2000

# content_2026-08-10-2200.json のような日付入りファイル名から投稿日時を読む。
# fullmatch で使う。backup_content_2026-04-12-2100.json のような別物を拾わないため。
# create_post.py の投稿日時解決もこれを使う（同じ規則を2か所に書かない）。
CONTENT_FILENAME_DT_RE = re.compile(
    r"content_(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})\.json"
)


def _store_dir(name: str) -> str:
    """保存先。git の共通ディレクトリが分からなければ空文字（保存も比較もしない）。"""
    override = os.environ.get(STORE_DIR_ENV, "").strip()
    if override:
        return os.path.join(override, name)
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
    return os.path.join(common, name)


def _baseline_dir() -> str:
    return _store_dir(BASELINE_DIRNAME)


def _history_dir() -> str:
    return _store_dir(HISTORY_DIRNAME)


def _production_slug(content: dict, content_path: str) -> str:
    """本番の名前（content_YYYY-MM-DD-HHMM.json）で、中の post_datetime とも日時が合う時だけ slug を返す。

    試作（proto-*）や content.json、/tmp のコピーを校閲しただけで、全 worktree 共通の
    前回版や修正の記録が上書きされないようにする。
    """
    m = CONTENT_FILENAME_DT_RE.fullmatch(os.path.basename(content_path or ""))
    if not m:
        return ""
    slug = slot_slug(content, content_path)
    y, mo, d_, h, mi = m.groups()
    return slug if slug == f"{y}-{mo}-{d_}-{h}{mi}" else ""


def _write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


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
    （あれば）とも日時が合う時だけ（_production_slug）。
    """
    slug = _production_slug(content, content_path)
    d = _baseline_dir()
    if not slug or not d:
        return ""
    path = os.path.join(d, f"{slug}.json")
    try:
        _write_json(path, content)
    except OSError as e:
        print(f"⚠ 前回版の保存に失敗（校閲結果には影響なし）: {e}")
        return ""
    return path


# ───────── 修正の記録 ─────────

# 写真の指定。どれかが変われば「写真」を差し替えたとみなす
PHOTO_KEYS = ("bg_strategy", "reuse_source", "reuse_theme", "reuse_filename",
              "local_path", "bg_prompt", "seed")
# 写真の切り位置・大きさ
POSITION_KEYS = ("focus_y", "focus_x", "photo_h_ratio")
# 文言として数えないキー（写真・位置のほか、描画の指定と作業メモ）
NON_TEXT_KEYS = set(PHOTO_KEYS) | set(POSITION_KEYS) | {
    "type", "layout", "filename", "focus_y_reason", "bg_generate_reason", "bubble",
}
# トップレベルで比べる項目（キー → 表示名）。memo・bg_prompt・_generated_dir などの
# 作業用の値は読者に見えないので数えない
TOP_LEVEL_LABELS = {
    "post_style": "投稿の型",
    "hashtags": "ハッシュタグ",
    "alt_text": "代替テキスト",
    "menu": "メニュー種別",
    "post_datetime": "投稿日時",
    "trial": "試すこと",
}
# キャプションの「書き出し」とみなす行数（CLAUDE.md の「1〜2行目は導入文」に合わせる）
CAPTION_HOOK_LINES = 2


def _norm_text(value) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", str(value or "")))


def _texts(value, skip=NON_TEXT_KEYS) -> list:
    """スライドの値から、読者に見える文字列を再帰的に集める。"""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for k, v in value.items() if k not in skip for s in _texts(v, skip)]
    if isinstance(value, list):
        return [s for v in value for s in _texts(v, skip)]
    return []


def _slide_text(slide: dict, keys=None) -> str:
    if keys is not None:
        return _norm_text("\x00".join(s for k in keys for s in _texts(slide.get(k))))
    return _norm_text("\x00".join(_texts(slide)))


def _slide_photo(slide: dict) -> tuple:
    return tuple(str(slide.get(k) or "") for k in PHOTO_KEYS)


def _slide_position(slide: dict) -> tuple:
    return tuple(str(slide.get(k) if slide.get(k) is not None else "") for k in POSITION_KEYS)


def _slide_name(index: int, slide: dict) -> str:
    return "表紙" if index == 0 and slide.get("type") == "cover" else f"スライド{index + 1}"


def _compare_slide(index: int, old: dict, new: dict) -> list:
    name = _slide_name(index, new)
    labels = []
    if (old.get("type") or "") != (new.get("type") or ""):
        labels.append(f"{name}の型")
    if name == "表紙":
        if _slide_text(old, ["title"]) != _slide_text(new, ["title"]):
            labels.append("表紙タイトル")
        rest = [k for k in set(old) | set(new) if k not in NON_TEXT_KEYS and k != "title"]
        if _slide_text(old, rest) != _slide_text(new, rest):
            labels.append("表紙の文言")
    elif _slide_text(old) != _slide_text(new):
        labels.append(f"{name}の文言")
    if _slide_photo(old) != _slide_photo(new):
        labels.append(f"{name}の写真")
    if _slide_position(old) != _slide_position(new):
        labels.append(f"{name}の写真の位置")
    return labels


def describe_changes(prev: dict, new: dict) -> list:
    """前回版から新しい版で「どこが変わったか」を、読み手向けの短い名前の一覧で返す。

    スライドは文言の並びで対応づけてから比べる（1枚足しただけで後ろの全スライドが
    「変わった」と出ないように）。
    """
    prev = prev if isinstance(prev, dict) else {}
    new = new if isinstance(new, dict) else {}
    old_slides = [s for s in (prev.get("slides") or []) if isinstance(s, dict)]
    new_slides = [s for s in (new.get("slides") or []) if isinstance(s, dict)]
    labels = []

    matcher = difflib.SequenceMatcher(
        None, [_slide_text(s) for s in old_slides], [_slide_text(s) for s in new_slides],
        autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal" or (tag == "replace" and i2 - i1 == j2 - j1):
            for k in range(i2 - i1):
                labels.extend(_compare_slide(j1 + k, old_slides[i1 + k], new_slides[j1 + k]))
            continue
        # 枚数が変わった区間。対応づけられる分は比べ、余りは追加・削除として数える
        n = min(i2 - i1, j2 - j1)
        for k in range(n):
            labels.extend(_compare_slide(j1 + k, old_slides[i1 + k], new_slides[j1 + k]))
        for j in range(j1 + n, j2):
            labels.append(f"{_slide_name(j, new_slides[j])}を追加")
        for i in range(i1 + n, i2):
            labels.append(f"スライド{i + 1}を削除")

    old_cap = str(prev.get("caption") or "").split("\n")
    new_cap = str(new.get("caption") or "").split("\n")
    if _norm_text("".join(old_cap[:CAPTION_HOOK_LINES])) != _norm_text("".join(new_cap[:CAPTION_HOOK_LINES])):
        labels.append("キャプションの書き出し")
    if _norm_text("".join(old_cap[CAPTION_HOOK_LINES:])) != _norm_text("".join(new_cap[CAPTION_HOOK_LINES:])):
        labels.append("キャプション本文")

    for key, label in TOP_LEVEL_LABELS.items():
        a, b = prev.get(key), new.get(key)
        if isinstance(a, (dict, list)) or isinstance(b, (dict, list)):
            same = json.dumps(a, ensure_ascii=False, sort_keys=True) == json.dumps(b, ensure_ascii=False, sort_keys=True)
        else:
            same = _norm_text(a) == _norm_text(b)
        if not same:
            labels.append(label)

    # 同じ名前が2回出ないように（並び順は保つ）
    return list(dict.fromkeys(labels))


def list_slugs() -> list:
    """前回版が保存されている枠の slug を古い順に返す（ダッシュボードが読む範囲を決める）。"""
    d = _baseline_dir()
    if not d or not os.path.isdir(d):
        return []
    return sorted(
        name[:-5] for name in os.listdir(d)
        if name.endswith(".json") and re.fullmatch(r"\d{4}-\d{2}-\d{2}-\d{4}", name[:-5])
    )


def load_history(slug: str):
    d = _history_dir()
    if not slug or not d:
        return None
    try:
        with open(os.path.join(d, f"{slug}.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def record_history(prev, content: dict, content_path: str = "", request: str = "",
                   origin: str = ORIGIN_CHAT, now=None) -> str:
    """校閲を通った版を修正の記録に足す。保存した記録のパスを返す（保存しなければ空文字）。

    記録の形:
      base   … 起点の版。週次タスクが校閲を通すたびに最新の版で置き換える
               （＝週次タスクの最後の版が「自動作成版」。作成中の作り直しは修正に数えない）。
               この仕組みの前に作られた枠は前回版を起点にし、origin は "unknown"
      events … base 以降のご本人の修正。日時・どこが変わったか・修正依頼の文
    prev は今回の校閲の前に保存されていた前回版（無ければ None）。
    """
    slug = _production_slug(content, content_path)
    d = _history_dir()
    if not slug or not d:
        return ""
    origin = origin if origin in ORIGINS else ORIGIN_CHAT
    at = (now or datetime.now(JST)).isoformat(timespec="seconds")
    hist = load_history(slug) or {"slug": slug, "base": None, "events": []}
    hist.setdefault("events", [])

    if origin == ORIGIN_WEEKLY or (hist.get("base") is None and prev is None):
        hist["base"] = {"at": at, "origin": origin, "content": content}
        if origin == ORIGIN_WEEKLY:
            # 起点が新しくなったので、それより前の修正は数えない
            hist["events"] = []
    else:
        if hist.get("base") is None:
            hist["base"] = {"at": None, "origin": "unknown", "content": prev}
        before = prev if prev is not None else hist["base"].get("content")
        changes = describe_changes(before, content)
        if not changes:
            return ""
        hist["events"].append({
            "at": at,
            "origin": origin,
            "changes": changes,
            "request": str(request or "").strip()[:MAX_REQUEST_CHARS],
        })
    path = os.path.join(d, f"{slug}.json")
    try:
        _write_json(path, hist)
    except OSError as e:
        print(f"⚠ 修正の記録の保存に失敗（校閲結果には影響なし）: {e}")
        return ""
    return path
