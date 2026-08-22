"""
theme_classifier.py
────────────────────────────────────────────────────
投稿テーマ（bridal / menu / reward / lifestyle）の判定を
get_recent_insights.py・insight_report.py・
dashboard/fetch_dashboard_data.py で共有するモジュール。

⚠ 依存は標準ライブラリのみに保つこと。
   fetch_dashboard_data.py は requests を持たない環境（/usr/bin/python3 3.9）で
   動かす前提で urllib を使っている。ここに requests 等を足すと壊れる。
   3.10+ の構文（dict[str, str] 等のアノテーション）も使わない。

キャプション推定の精度: 人手ラベル322件（post_classifications.json）に対し
234件=72.7%。多数派ベースラインは65.5%。
旧実装は固定順の先頭一致で、旧スタイルの定型自己紹介にある
「ブライダルエステも得意♪」が全件 bridal に一致し 32件=9.9% しか当たらなかった。
定型文を除去してSEO導入文を重み付けする現方式でこの水準になっている。
キーワードや重みを変えた時はこの数値で回帰を確認すること。

判定の優先順位:
  1. theme_overrides.json      … 手動上書き（最優先・以後固定）
  2. post_classifications.json … 棚卸し済みの確定分類
  3. キャプションからの推定     … 上2つに無い投稿

post_classifications.json は 2026-04-06 の棚卸しで止まっており、
それ以降の投稿は必ず 3 に落ちてくる（＝全件「未分類」になるのを防ぐ）。
"""

import json
import os
import re
from collections import Counter

CLASSIFICATIONS_FILE = "post_classifications.json"
OVERRIDES_FILE       = "theme_overrides.json"

THEME_LABELS = {
    "bridal":    "ブライダル",
    "menu":      "メニュー・サービス",
    "reward":    "ご褒美エステ",
    "lifestyle": "ライフスタイル・自己語り",
    "other":     "未分類",
}

# ──────────────────────────────────────────────────────────
# キャプションからのテーマ推定
#
# 現行のキャプションは CLAUDE.md のルールにより
#   1〜2行目: 主題を要約したSEO導入文
#   3行目以降: 「MIKIです。」から本文
# という構造になっている。導入文が主題そのものなので、そこを強く重み付けする。
# ──────────────────────────────────────────────────────────

# 全投稿に出る自己紹介・料金表・ハッシュタグはテーマ信号にならないので落とす
BOILERPLATE_MARKERS = [
    "20代～30代の口コミ", "20代〜30代の口コミ", "シデスコ国際ライセンス",
    "〜MIKI〜", ":*:*:*:*", "＼ご予約", "▶︎", "ご予約・お問い合わせ",
]
LEAD_MARKERS        = ["MIKIです", "mikiです"]
LEAD_BOOST          = 4      # 導入文に出た語の重み倍率
LEAD_FALLBACK_CHARS = 120    # 「MIKIです」が無い旧スタイル用

# (重み, 語) — 重み5は主題を確定させる明示マーカー
THEME_KEYWORDS = {
    "bridal": [
        (3, ["ブライダル", "花嫁", "プレ花嫁", "卒花", "挙式", "結婚式", "ウェディング",
             "前撮り", "フォトウェディング", "婚礼", "式まで", "式当日", "秋婚", "春婚",
             "冬婚", "夏婚", "マリッジ"]),
        (1, ["ドレス", "披露宴", "入籍"]),
    ],
    "reward": [
        (3, ["ご褒美", "労わ", "労る", "ねぎら", "頑張った自分", "頑張ってきた自分",
             "頑張りすぎた自分", "自分を大切", "自分のための時間", "自分時間",
             "自分へのプレゼント"]),
        (1, ["リセット", "疲れ", "癒し", "リフレッシュ", "リラックス", "解放"]),
    ],
    "lifestyle": [
        (5, ["自分語り", "プライベート投稿", "お休みの日", "原点", "ぼやか", "私自身の話"]),
        (3, ["プライベート", "休日の過ごし方", "大切にしている", "大切なこと",
             "ライフプラン", "教わる", "教えてくれた", "私の話", "きっかけ", "初心",
             "お客様のお声", "子供の頃", "ご機嫌", "習慣"]),
        (1, ["想い", "日常", "本音", "正直", "感謝", "趣味"]),
    ],
    "menu": [
        (3, ["コース", "メニュー", "料金", "キャビテーション", "ラジオ波", "EMS",
             "痩身", "フェイシャル", "マシン", "ハーブピーリング", "ご質問",
             "よくある質問", "予約方法", "アクセス", "契約", "キャンペーン",
             "オプション", "毛穴", "小顔", "対策"]),
        (1, ["施術", "ケア", "肌", "むくみ", "予約", "円"]),
    ],
}
# 同点時の優先順（主題としての具体性が高い順）
THEME_PRIORITY = ["bridal", "reward", "lifestyle", "menu"]


def _strip_boilerplate(caption: str) -> str:
    cut = len(caption)
    for m in BOILERPLATE_MARKERS:
        i = caption.find(m)
        if i != -1:
            cut = min(cut, i)
    body = caption[:cut] if cut > 40 else caption
    return re.sub(r"#\S+", "", body)


def _split_lead(body: str) -> tuple:
    """SEO導入文（主題）と本文に分ける。"""
    for m in LEAD_MARKERS:
        i = body.find(m)
        if 0 < i <= 400:
            return body[:i], body[i:]
    return body[:LEAD_FALLBACK_CHARS], body[LEAD_FALLBACK_CHARS:]


def classify_by_caption(caption: str) -> str:
    body = _strip_boilerplate(caption or "")
    lead, rest = _split_lead(body)
    score = Counter()
    for theme, groups in THEME_KEYWORDS.items():
        for weight, words in groups:
            for w in words:
                score[theme] += weight * (lead.count(w) * LEAD_BOOST + rest.count(w))
    best = max(score.values()) if score else 0
    if best == 0:
        return "other"
    return next(t for t in THEME_PRIORITY if score[t] == best)


def load_classifications() -> dict:
    if not os.path.exists(CLASSIFICATIONS_FILE):
        return {}
    with open(CLASSIFICATIONS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return {c["media_id"]: c["theme"] for c in data.get("classifications", [])}


def load_overrides() -> dict:
    """手動上書き（media_id → theme）。推定が外れた投稿をここで直すと以後固定される。"""
    if not os.path.exists(OVERRIDES_FILE):
        return {}
    with open(OVERRIDES_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def resolve_theme(media_id: str, caption: str,
                  classifications: dict, overrides: dict) -> tuple:
    """テーマを (theme, source) で返す。手動上書き > 棚卸し済み > キャプション推定。"""
    if media_id in overrides:
        return overrides[media_id], "override"
    if media_id in classifications:
        return classifications[media_id], "classified"
    return classify_by_caption(caption), "estimated"
