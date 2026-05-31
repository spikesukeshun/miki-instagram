"""
投稿内容の校閲スクリプト。
content.json を読み込み、CLAUDE.md の11項目チェックリストを自動検証する。

Usage:
    python review_post.py [content.json のパス] [--revision "修正依頼文"]
"""

import os
import sys
import json
import re
import argparse

EMOJI_PATTERN = re.compile(
    "[\U0001F300-\U0001F9FF"
    "\U00002600-\U000027BF"
    "\U0001FA00-\U0001FA9F"
    "\U0001FA70-\U0001FAFF"
    "\U00002702-\U000027B0]+",
    flags=re.UNICODE,
)

CTA_REQUIRED_TITLE = "MIKI指名 初回限定20%OFF（VIPコースのみ）"
CTA_REQUIRED_TITLE_ALT = "MIKI指名 初回限定20%OFF\n（VIPコースのみ）"


def count_emojis(text: str) -> int:
    return sum(len(m) for m in EMOJI_PATTERN.findall(text))


def check_caption_seo_intro(caption: str) -> tuple[bool, str]:
    """キャプション1〜2行目にSEO導入文があり、MIKIです。が3行目以降か確認"""
    lines = caption.split("\n")
    first_nonempty = next((l for l in lines if l.strip()), "")
    if first_nonempty.strip() == "MIKIです。":
        return False, "キャプション1行目が「MIKIです。」— 主要キーワードを含む導入文を先に書いてください"
    miki_start_idx = next(
        (i for i, l in enumerate(lines) if l.strip() == "MIKIです。"), None
    )
    if miki_start_idx is None:
        return False, "キャプションに「MIKIです。」が見つかりません"
    if miki_start_idx < 2:
        return False, f"「MIKIです。」が{miki_start_idx + 1}行目— 3行目以降に移動してください"
    return True, f"「MIKIです。」は{miki_start_idx + 1}行目から ✓"


def check_caption_emoji_count(caption: str) -> tuple[bool, str]:
    count = count_emojis(caption)
    if count < 3:
        return False, f"絵文字が少なすぎます（{count}個）— 3〜5個が目安"
    if count > 5:
        return False, f"絵文字が多すぎます（{count}個）— 3〜5個が目安"
    return True, f"絵文字数: {count}個 ✓"


def check_caption_forbidden_chars(caption: str) -> tuple[bool, str]:
    if "——" in caption:
        return False, "キャプションに「——」（em dash）が含まれています— 使用禁止"
    return True, "禁止文字なし ✓"


def check_caption_has_cta(caption: str) -> tuple[bool, str]:
    if "MIKI指名 初回限定20%OFF（VIPコースのみ）" not in caption:
        return False, "キャプション末尾にCTA「MIKI指名 初回限定20%OFF（VIPコースのみ）」がありません"
    return True, "キャプションCTA ✓"


# 年代括りの定型導入（例: 「30代・40代の女性へ」）
GENERIC_OPENER_RE = re.compile(r"^[2-5]0代\s*[・,、,]?\s*[2-5]0代")


def _normalize_prefix(text: str, n: int = 12) -> str:
    return re.sub(r"\s", "", text)[:n]


def check_caption_seo_opener(caption: str, recent_path: str = "recent_insights.json") -> tuple[bool, str]:
    """導入文（1行目）が定型化・直近投稿と重複していないか確認。
    recent_insights.json があれば直近投稿の導入文と照合する（posts[].intro 必須）。"""
    intro = next((l.strip() for l in caption.split("\n") if l.strip()), "")
    if not intro:
        return True, "導入文チェック（導入なし・スキップ）"

    # 1) 直近投稿と同一の定型導入か
    if os.path.exists(recent_path):
        try:
            with open(recent_path, encoding="utf-8") as f:
                data = json.load(f)
            recent_intros = [p.get("intro", "") for p in data.get("posts", []) if p.get("intro")]
        except (json.JSONDecodeError, OSError):
            recent_intros = []
        new_pref = _normalize_prefix(intro)
        if any(_normalize_prefix(s) == new_pref for s in recent_intros):
            return False, f"導入文が直近投稿と同じ定型です（「{new_pref}…」）— 投稿ごとに固有の一文で開始してください"

    # 2) 年代括りの汎用テンプレ（recent が無い場合の保険）
    if GENERIC_OPENER_RE.match(intro):
        return False, f"導入文が定型の年代括りです（「{intro[:14]}…」）— 没個性化回避のため固有の切り口に変更してください"

    return True, "導入文の独自性 ✓"


def check_slides(slides: list) -> list[tuple[bool, str]]:
    results = []

    for i, slide in enumerate(slides, 1):
        stype = slide.get("type", "")
        title = slide.get("title", "")
        body_keys = ["text", "body"]
        body = " ".join(str(slide.get(k, "")) for k in body_keys)
        items = slide.get("items", [])
        bg_prompt = slide.get("bg_prompt", "")

        # 1. bg_prompt に no people
        if bg_prompt and "no people" not in bg_prompt:
            results.append((False, f"スライド{i}: bg_prompt に 'no people' がありません"))
        elif bg_prompt:
            results.append((True, f"スライド{i}: bg_prompt ✓"))

        # 2. スライド本文にMIKIが使われていないか
        # CTAスライドは「MIKIにお任せください♪」のようなブランドCTAフレーズを許可
        if stype != "cta" and "MIKI" in body:
            results.append((False, f"スライド{i}: 本文（text/body）に「MIKI」が含まれています— 「私」に変更してください"))
        if items and any("MIKI" in item for item in items):
            results.append((False, f"スライド{i}: list items に「MIKI」が含まれています"))

        # 3. listスライドのitemsが全角20文字以内か
        if stype == "list" and items:
            for j, item in enumerate(items, 1):
                if len(item) > 20:
                    results.append((False, f"スライド{i} 項目{j}: {len(item)}文字（全角20文字超え）— 折り返しなし固定幅のため要短縮"))

        # 4. CTAスライドのタイトル恒久ルール + body禁止フレーズ
        if stype == "cta":
            if title not in (CTA_REQUIRED_TITLE, CTA_REQUIRED_TITLE_ALT):
                results.append(
                    (False, f"スライド{i}（CTA）: タイトルが違います\n"
                            f"  現在: 「{title}」\n"
                            f"  必須: 「{CTA_REQUIRED_TITLE}」")
                )
            else:
                results.append((True, f"スライド{i}（CTA）タイトル ✓"))

            # CTAスライドbodyの禁止フレーズチェック
            CTA_BANNED_PHRASES = [
                "MIKIに会いに来てください",
                "MIKIに会いにきてください",
                "まずはお気軽にDMでご連絡ください",
                "お気軽にDMでご連絡ください",
            ]
            cta_body = slide.get("body", "")
            for phrase in CTA_BANNED_PHRASES:
                if phrase in cta_body:
                    results.append(
                        (False, f"スライド{i}（CTA）body: 禁止フレーズ「{phrase}」が含まれています\n"
                                f"  → 「MIKIにお任せください。」に変更してください")
                    )
                    break
            else:
                if cta_body:
                    results.append((True, f"スライド{i}（CTA）body 禁止フレーズなし ✓"))

        # 5. タイトルにMIKIを使う場合、幼稚な表現チェック（警告のみ）
        naive_patterns = ["MIKIが大好きな", "MIKIのおすすめ！", "MIKIが癒して", "MIKIのお気に入り"]
        if any(p in title for p in naive_patterns):
            results.append((False, f"スライド{i}: タイトルのMIKI使用が幼稚な印象を与える可能性— 確認してください: 「{title}」"))

    # スライド枚数チェック（6枚以内）
    if len(slides) > 6:
        results.append((False, f"スライドが{len(slides)}枚あります— 6枚以内（末尾固定2枚を除く）"))
    else:
        results.append((True, f"スライド枚数: {len(slides)}枚 ✓"))

    return results


def check_alt_text(alt_text: str) -> tuple[bool, str]:
    if not alt_text or not alt_text.strip():
        return False, "alt_text が設定されていません"
    # キーワード羅列判定（スペース区切りで短い単語が4つ以上→警告）
    words = alt_text.strip().split()
    avg_len = sum(len(w) for w in words) / max(len(words), 1)
    if len(words) >= 4 and avg_len < 4:
        return False, f"alt_text がキーワード羅列に見えます— 短い文章で記述してください: 「{alt_text}」"
    return True, f"alt_text ✓"


def check_revision_applied(caption: str, body_texts: list[str], revision_instruction: str) -> list[tuple[bool, str]]:
    """修正依頼の指示が実際に反映されているか簡易チェック"""
    results = []
    instruction_lower = revision_instruction

    # よくある修正フレーズのチェック
    checks = [
        ("MIKIにお任せください♪", ["MIKIにお任せください♪"]),
        ("MIKIにお任せください", ["MIKIにお任せください"]),
    ]
    for phrase, keywords in checks:
        if phrase in instruction_lower:
            found_in_caption = any(k in caption for k in keywords)
            found_in_body = any(any(k in b for k in keywords) for b in body_texts)
            if not found_in_caption and not found_in_body:
                results.append((False, f"修正依頼に「{phrase}」が含まれていますが、キャプション・スライド本文に見つかりません"))
            else:
                results.append((True, f"修正依頼「{phrase}」の反映確認 ✓"))

    # 「MIKIに会いに来てください」が残っていないか
    if "MIKIに会いに来てください" in caption:
        results.append((False, "キャプションに「MIKIに会いに来てください」が残っています— 修正依頼の対象フレーズを確認してください"))

    return results


def run_review(content_path: str, revision_instruction: str = ""):
    with open(content_path, encoding="utf-8") as f:
        content = json.load(f)

    slides = content.get("slides", [])
    caption = content.get("caption", "")
    alt_text = content.get("alt_text", "")

    all_results = []

    # キャプションチェック
    all_results.append(check_caption_seo_intro(caption))
    all_results.append(check_caption_seo_opener(caption))
    all_results.append(check_caption_emoji_count(caption))
    all_results.append(check_caption_forbidden_chars(caption))
    all_results.append(check_caption_has_cta(caption))

    # スライドチェック
    all_results.extend(check_slides(slides))

    # alt_textチェック
    all_results.append(check_alt_text(alt_text))

    # 修正依頼反映チェック（指示がある場合のみ）
    if revision_instruction:
        body_texts = [s.get("text", "") + s.get("body", "") for s in slides]
        all_results.extend(check_revision_applied(caption, body_texts, revision_instruction))

    # 結果出力
    print("\n" + "=" * 50)
    print("📋 投稿校閲レポート")
    print("=" * 50)

    errors = [(ok, msg) for ok, msg in all_results if not ok]
    ok_items = [(ok, msg) for ok, msg in all_results if ok]

    if errors:
        print(f"\n❌ 問題あり: {len(errors)}件\n")
        for _, msg in errors:
            print(f"  ✗ {msg}")
    else:
        print("\n✅ 問題なし")

    if ok_items:
        print(f"\n✓ チェック通過: {len(ok_items)}件")
        for _, msg in ok_items:
            print(f"  ✓ {msg}")

    print("=" * 50 + "\n")
    return len(errors) == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="投稿内容の校閲チェック")
    parser.add_argument("content_file", nargs="?", default="content.json", help="content.jsonのパス")
    parser.add_argument("--revision", default="", help="修正依頼文（修正依頼処理後に指定）")
    args = parser.parse_args()

    ok = run_review(args.content_file, args.revision)
    sys.exit(0 if ok else 1)
