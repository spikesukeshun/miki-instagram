"""投稿を生成するこの作業ディレクトリが、確定済みルールを満たしているか確認する。

2026-08-08 に判明した問題：このディレクトリの main は 2026-04-26 以降 origin/main と
分岐したまま同期されておらず、5〜8月に origin/main へ入った修正
（シートI列以降の廃止・listの番号の左揃え）が、実際に画像を作るマシンに届いていなかった。
その結果、文章としては確定していたルールが投稿の上で巻き戻った。

このスクリプトは2種類のチェックを行う：

1. 恒久ルールの実装チェック（ネットワーク不要・これが本体）
   コードが確定済みルールどおりになっているかをソースから直接検証する。
   git の状態がどうであれ、ここが通れば投稿は正しく作られる。

2. origin/main との差分レポート（git fetch できるときのみ・参考情報）
   生成系スクリプトについて、origin/main にあってこちらに無いコミットを一覧する。

Usage:
    python3 check_repo_sync.py            # 両方
    python3 check_repo_sync.py --no-fetch # 1 のみ（オフライン）

終了コード: 0=問題なし / 1=恒久ルール違反あり（投稿を作ってはいけない）
"""
import argparse
import os
import re
import subprocess
import sys

REPO_DIR = os.path.dirname(os.path.abspath(__file__))

# origin/main との差分を見る対象（投稿の中身に直接影響するもの）
GENERATION_SCRIPTS = [
    "create_post.py",
    "generate_carousel.py",
    "register_post.py",
    "review_post.py",
    "check_week_slots.py",
]


def _read(name: str) -> str:
    with open(os.path.join(REPO_DIR, name), encoding="utf-8") as f:
        return f.read()


def check_list_left_align() -> tuple[bool, str]:
    """listスライドの番号付き箇条書きが左揃えになっているか。

    行ごとに中央寄せ（ループ内で x を計算し直す）に戻っていないことを見る。
    """
    src = _read("generate_carousel.py")
    m = re.search(r"def generate_list_slide\(.*?\n(.*?)\ndef ", src, re.S)
    if not m:
        return False, "generate_list_slide() が見つかりません"
    body = m.group(1)
    loop = body.split("for ", 1)[-1] if "for " in body else ""
    # 描画ループの中で x を計算し直していたら行ごと中央寄せ＝ルール違反
    if re.search(r"x\s*=\s*\(W\s*-\s*total\)\s*//\s*2", body):
        return False, ("listの番号が行ごとの中央寄せに戻っています— 左揃え（全項目で同じx）に"
                       "してください。CLAUDE.md「維持されるルール」参照")
    if "item_x" not in body:
        return False, "listの番号・本文が共通のx座標で描画されていません（左揃えの実装が無い）"
    return True, "listの番号付き箇条書きは左揃え ✓"


def check_sheet_columns() -> tuple[bool, str]:
    """シート書き込みが A〜H の8列に収まっているか。"""
    src = _read("register_post.py")
    wide = sorted(set(re.findall(r'f"A\{[^}]+\}:([I-Z])\{', src)))
    if wide:
        return False, (f"register_post.py が A〜{wide[-1]} 列に書き込んでいます— "
                       f"シートは A〜H の8列のみ（I列以降は2026-07-11に廃止）")
    if "SHEET_LAST_COL" not in src:
        return False, "register_post.py に SHEET_LAST_COL がありません（列範囲が固定されていない）"
    create_src = _read("create_post.py")
    m = re.search(r"register\(\s*(.*?)\)\s*\n", create_src, re.S)
    if m and ("alt_text=" in m.group(1) or "seed=" in m.group(1)):
        return False, "create_post.py が register() に seed / alt_text を渡しています— シートI列以降が復活します"
    return True, "シート書き込みは A〜H の8列 ✓"


def check_no_silent_bg_fallback() -> tuple[bool, str]:
    """Drive指定の失敗時に、黙ってAI生成へフォールバックしないこと。"""
    src = _read("create_post.py")
    if "Drive画像の取得失敗、HFで代替生成" in src:
        return False, ("create_post.py がDrive取得失敗時に黙ってAI生成へフォールバックします— "
                       "意図しない生成画像の使用につながるため例外で止めること")
    if "reuse_source が指定されていません" not in src:
        return False, "create_post.py に reuse_source 未指定の検出がありません"
    return True, "Drive取得失敗時にAI生成へ落ちない ✓"


def check_generate_guard() -> tuple[bool, str]:
    """review_post.py が AI生成の暗黙採用を止められること。"""
    src = _read("review_post.py")
    if "check_backgrounds" not in src or "bg_generate_reason" not in src:
        return False, "review_post.py に背景チェック（check_backgrounds）がありません"
    return True, "review_post.py の背景チェックあり ✓"


RULE_CHECKS = [
    check_list_left_align,
    check_sheet_columns,
    check_no_silent_bg_fallback,
    check_generate_guard,
]


def report_origin_diff() -> None:
    """origin/main にあってこちらに無いコミットを生成系スクリプト単位で出す（参考情報）。"""
    try:
        subprocess.run(["git", "fetch", "--quiet", "origin", "main"],
                       cwd=REPO_DIR, check=True, timeout=60)
    except Exception as e:
        print(f"\n[参考] origin/main を取得できませんでした（{e}）— 差分レポートはスキップします")
        return

    print("\n--- origin/main との差分（生成系スクリプト） ---")
    any_behind = False
    for path in GENERATION_SCRIPTS:
        try:
            # --full-history を付けないと、マージを含む履歴でコミットが隠れる
            out = subprocess.check_output(
                ["git", "log", "--full-history", "--oneline", "HEAD..origin/main", "--", path],
                cwd=REPO_DIR, text=True, timeout=60,
            ).strip()
        except Exception as e:
            print(f"  {path}: 確認できませんでした（{e}）")
            continue
        if out:
            any_behind = True
            lines = out.splitlines()
            print(f"  ⚠ {path}: origin/main に未取り込みのコミット {len(lines)}件")
            for line in lines[:5]:
                print(f"      {line}")
            if len(lines) > 5:
                print(f"      … 他{len(lines) - 5}件")
        else:
            print(f"  ✓ {path}: origin/main と同期済み")

    if any_behind:
        print("\n  ※ 上のルールチェックが全て ✓ なら投稿を作って問題ない。")
        print("    ただし origin/main 側の修正が届いていないので、時間のあるときに")
        print("    取り込みを検討すること（GitHub Actions の投稿処理は origin/main を使う）。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="投稿生成環境の恒久ルール実装チェック")
    parser.add_argument("--no-fetch", action="store_true", help="origin/main との差分レポートを行わない")
    args = parser.parse_args()

    print("=" * 50)
    print("🔧 投稿生成環境チェック")
    print("=" * 50)

    failures = []
    for check in RULE_CHECKS:
        ok, msg = check()
        print(f"  {'✓' if ok else '✗'} {msg}")
        if not ok:
            failures.append(msg)

    if not args.no_fetch:
        report_origin_diff()

    print("=" * 50)
    if failures:
        print(f"\n❌ 恒久ルール違反 {len(failures)}件— 投稿を作る前に直してください\n")
        sys.exit(1)
    print("\n✅ 恒久ルールはすべて実装されています\n")
    sys.exit(0)
