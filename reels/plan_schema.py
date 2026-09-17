"""リール設計図（plan.json）の型と、設計ルールの数値（フェーズ2）。

ルールの数値はここが唯一の正。rules/reel-planning.md は意味だけを書き、数値を転記しない。

plan.json の形（キーは英語・中身は日本語）:
{
  "schema_version": 1,
  "theme": "背中が自分では見えないからこそケアが大切",
  "slug": "back-care-invisible",
  "purpose": {"goal": "...", "audience": "...", "viewer_takeaway": "...", "desired_action": "..."},
  "duration": {"class": "short|standard|long", "target_seconds": 15, "reason": "..."},
  "hook": {"text": "...", "visual": "...", "why_it_stops": "..."},
  "script": [{"section": "hook|problem|main|detail|cta", "text": "..."}],
  "voice_script": {"mode": "miki_voice_memo|tts|none", "lines": [{"cut_id": "c01", "text": "...", "reading": "..."}]},
  "cuts": [ カット（下記） ],
  "cta": {"message": "...", "lp_guidance_text": "..."},
  "cover": {"title_lines": ["..."], "background_cut": "c01", "note": "..."},
  "open_questions": ["作る前に人に確認すること"]
}

カット:
{
  "id": "c01", "start": 0.0, "end": 2.0, "role": "hook",
  "purpose": "何を伝えるカットか",
  "visual": {
    "shows": "何を映すか",
    "person_action": "人物の動き（人物がいなければ「なし」）",
    "camera_move": "カメラの動き（固定・寄る・引く・パン・手持ちで追う など）",
    "changes": [{"at": 1.0, "what": "テロップが出る"}]      # 絶対時刻（秒）
  },
  "material": {
    "preferred": "miki_video",                               # MATERIAL_TYPES のどれか
    "requirements": {
      "subjects_all": ["背中"],            # 必ず写っていること（1つでも無ければ候補にしない）
      "subjects_any": ["手元"],            # どれか1つ写っていればよい
      "actions_any": ["施術"],             # 書いたら必須（動作が違う映像は候補にしない）
      "framing_any": ["寄り"],             # 合えば優先（必須ではない）
      "people_allowed": ["お客様・施術者"], "face_allowed": ["なし"],
      "min_seconds": 2.0, "motion_min": "low", "consent_min": "書面",
      "ba_case_id": "（BAを使う場合だけ）"
    },
    "photo_treatment": {"type": "push_in", "note": "肩甲骨に向かってゆっくり寄る"},   # photo_motion の時
    "fallbacks": [{"type": "photo_motion", "requirements": {...}, "photo_treatment": {...}, "note": "..."},
                  {"type": "text_card", "note": "..."}]
  },
  "caption": [{"lines": ["背中、見えてる？"], "start": 0.2, "end": 1.9}],
  "narration": {"has": true, "line": "ボイス台本の該当行と同じ文"},
  "facts": [{"claim": "最後のエステは式の5日前まで", "source_type": "posted_content", "source": "content_2026-09-14-2200.json"}],
  "tags": ["before_after"]                                    # BAを見せるカットだけ
}
"""

from __future__ import annotations

import copy
import re

SCHEMA_VERSION = 1

# ---- 構成 ----
ROLES = ["hook", "problem", "main", "detail", "cta"]
ROLE_LABELS = {"hook": "Hook", "problem": "問題提起", "main": "本題", "detail": "補足・具体例", "cta": "CTA"}

# 尺の型。企画に合わせて選ぶ（固定しない）
DURATION_CLASSES = {
    "short": {"label": "短い", "min": 12, "max": 18},
    "standard": {"label": "標準", "min": 20, "max": 30},
    "long": {"label": "長い", "min": 30, "max": 45},
}
TOTAL_TOLERANCE_SECONDS = 1.0

# Hook は最初のカットで、この秒までに終える（このアカウントの平均視聴は約3秒）
HOOK_MAX_END_SECONDS = 3.0
MIN_CUT_SECONDS = 0.5
TIME_EPSILON = 0.05

# ---- 素材 ----
# 数字が小さいほど優先。ai_video はフェーズ6の実験扱いで、今は割り当てない
MATERIAL_TYPES = {
    "miki_video": {"priority": 1, "label": "MIKIさん提供の実写動画", "catalog_kind": "動画"},
    "photo_motion": {"priority": 2, "label": "既存写真＋モーション演出", "catalog_kind": "写真"},
    "stock_video": {"priority": 3, "label": "無料ストック動画（未導入）", "catalog_kind": None},
    "ai_video": {"priority": 4, "label": "無料AI動画（フェーズ6の実験扱い）", "catalog_kind": None},
}
# 素材を使わない（または自前で作る）カット。代替の最後の手段としても使う
NON_MATERIAL_TYPES = {
    "text_card": "文字主体の場面",
    "screen_capture": "自前の画面収録（LP・プロフィールなど）",
    "change_cut": "カットの内容を変更する",
}
AI_VIDEO_ENABLED = False

PHOTO_TREATMENTS = {
    "push_in": "被写体に向かって寄る",
    "pull_out": "引いて全体を見せる",
    "pan": "被写体をなぞるように動かす",
    "crop_detail": "一部を切り抜いて見せる",
    "split_compare": "2枚を左右（上下）に並べて比べる",
    "grid_build": "複数枚を組み立てて見せる",
    "match_cut": "動画へ動きをつないで切り替える",
}

MOTION_ORDER = ["static", "low", "medium", "high"]

# 写真だけを並べた設計を基本形にしないためのルール
MAX_CONSECUTIVE_PHOTO_CUTS = 2
MAX_PHOTO_SHARE_WHEN_VIDEO = 0.40

# ---- テンポ ----
# 画面に変化の予定がない時間がこれを超えたら「確認警告」（NGではない）
CHANGE_GAP_WARN_SECONDS = 3.0

# ---- テロップ ----
CAPTION_LINE_TARGET = 15      # 目安。超えたら警告
CAPTION_LINE_MAX = 20         # これを超えたら差し戻し
CAPTION_MAX_LINES = 2
READING_CHARS_PER_SECOND = 8.0

# ---- ナレーション ----
NARRATION_CHARS_PER_SECOND = 7.5
VOICE_MODES = {"miki_voice_memo": "MIKIさんのボイスメモ", "tts": "合成音声", "none": "ナレーションなし"}

# ---- カバー ----
COVER_MAX_LINES = 2
COVER_LINE_TARGET = 12

# ---- 事実と表現 ----
FACT_SOURCE_TYPES = {
    "ba_case": "BA登録の確認済みケース",
    "user_confirmed": "ユーザー（MIKIさん）が確認した事実",
    "posted_content": "過去に投稿して承認済みの内容",
    "salon_info": "サロンの確定情報（料金・機器など）",
}
# 数字を含む主張（回数・期間・体重など）は出典が必要
NUMERIC_CLAIM_RE = re.compile(
    r"([0-9０-９]+|[一二三四五六七八九十]+)\s*(回|ヶ月|か月|カ月|ヵ月|週間|週|日前|日|kg|キロ|％|%|cm|センチ|歳|年)")
FORBIDDEN_WORDS = ["AMRTA"]
# 効果を約束する言い切り（景品表示法・薬機法の観点で避けたい）。見つけたら確認警告
GUARANTEE_WORDS = ["必ず", "絶対", "確実に", "100%", "１００％", "誰でも", "一回で", "1回で"]


def sanitize_plan(plan: dict) -> tuple:
    """「配列のはずが文字列」のような書き間違いで処理が落ちないよう、形だけ整えた写しを返す。

    中身は直さない。見つかった問題は (code, message, cut_id) の一覧で返し、検査が ❌ として報告する。
    これが無いと、検査の途中で例外になって design.md も検査結果も出ず、直す手がかりが残らない。
    """
    problems = []

    def fix_list(container: dict, key: str, where: str, cut_id=None) -> None:
        value = container.get(key)
        if value is None:
            return
        if not isinstance(value, list):
            problems.append((f"{key}_shape", f"{where} は配列で書いてください", cut_id))
            container[key] = []
            return
        kept = [v for v in value if isinstance(v, dict)]
        if len(kept) != len(value):
            problems.append((f"{key}_shape", f"{where} に項目でないものが混ざっています", cut_id))
            container[key] = kept

    def fix_dict(container: dict, key: str, where: str, cut_id=None) -> dict:
        value = container.get(key)
        if value is not None and not isinstance(value, dict):
            problems.append((f"{key}_shape", f"{where} の書き方が違います", cut_id))
            container[key] = {}
        return container.get(key) or {}

    plan = copy.deepcopy(plan) if isinstance(plan, dict) else {}
    fix_list(plan, "script", "script（台本）")
    fix_list(plan, "cuts", "cuts（カット構成）")
    fix_list(fix_dict(plan, "voice_script", "voice_script（ボイス台本）"), "lines", "voice_script.lines")
    for cut in plan.get("cuts") or []:
        cid = cut.get("id")
        fix_list(cut, "caption", "caption（テロップ）", cid)
        fix_list(cut, "facts", "facts（事実と出典）", cid)
        fix_list(fix_dict(cut, "visual", "visual（映すもの）", cid), "changes", "visual.changes", cid)
        fix_list(fix_dict(cut, "material", "material（素材）", cid), "fallbacks", "material.fallbacks", cid)
    return plan, problems


def to_number(value) -> float | None:
    """設計図の数値（秒など）を読む。書き間違いは None にして、検査と設計図の出力を止めない。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def caption_length(line: str) -> int:
    """テロップ1行の文字数（空白は数えない）。"""
    return len(re.sub(r"\s", "", line))


def material_label(kind: str) -> str:
    if kind in MATERIAL_TYPES:
        return MATERIAL_TYPES[kind]["label"]
    return NON_MATERIAL_TYPES.get(kind, kind)


def is_photo_based(kind: str) -> bool:
    return kind == "photo_motion"


def is_video_based(kind: str) -> bool:
    return kind in ("miki_video", "stock_video", "ai_video", "screen_capture")
