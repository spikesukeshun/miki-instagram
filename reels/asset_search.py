"""設計図の各カットに合う素材を台帳から探し、不足素材と撮影依頼を作る（フェーズ2）。

探し方:
  1. 第一希望の素材の種類から、代替（fallbacks）の順番に探す
  2. 条件（被写体・人物・顔・同意・長さ・動き）を満たさない素材は候補にしない
  3. 同意や使用可否が「未確認」の素材は「確認待ちの候補」として分けて出す
     （勝手に割り当てない。人が確認すれば使える、という意味）
  4. 第一希望が実写動画なのに使える素材が無いカットは、代替があっても「不足素材」に載せる
     （理想は実写なので、撮影依頼に回す）
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from reels import config
from reels import plan_schema as S
from reels.catalog import CONSENT_RANK, split_tags

_SEGMENT_TEXT_RE = re.compile(r"([\d.]+)-([\d.]+)秒\((静止|少|中|多)\)")
COMPOSITE_TAG = "2枚組"
_MOTION_FROM_LABEL = {v: k for k, v in {"static": "静止", "low": "少", "medium": "中", "high": "多"}.items()}


@dataclass
class Candidate:
    asset_id: str
    file_name: str
    score: float
    segment: dict | None
    pending: list = field(default_factory=list)   # 確認が必要な点（同意・使用可否）
    matched: list = field(default_factory=list)   # 合った条件


@dataclass
class CutResult:
    cut_id: str
    status: str                 # 割当OK / 確認待ち / 代替で対応 / 不足
    used_type: str | None
    chosen: Candidate | None
    pending_candidates: list
    rejected: dict              # 素材ID → 候補にしなかった理由
    notes: list
    missing: dict | None        # 不足素材一覧に載せる内容


def asset_segments(row: dict) -> list:
    """解析結果（このMacに残っていれば）か、台帳の「使える区間」の文字から区間を得る。"""
    path = config.ASSETS_WORK_DIR / row.get("asset_id", "") / "analysis.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("segments", [])
    segments = []
    for m in _SEGMENT_TEXT_RE.finditer(row.get("segments", "") or ""):
        start, end = float(m.group(1)), float(m.group(2))
        segments.append({"start": start, "end": end, "duration": round(end - start, 2),
                         "motion_class": _MOTION_FROM_LABEL[m.group(3)]})
    return segments


def implied_consent_min(row: dict) -> str:
    """素材そのものから決まる、最低限必要な同意。

    カットの requirements に consent_min を書き忘れても、お客様が写った素材が
    同意の確認なしに割り当てられないようにするための下限（2026-09-18 のレビュー指摘）。
    """
    people = row.get("people") or ""
    if "お客様" not in people:
        return "不要"
    return "書面" if (row.get("face") or "") in ("横顔", "正面") else "口頭"


def _overlap(wanted: list, have: list) -> list:
    return [w for w in wanted if any(w in h or h in w for h in have)]


def evaluate_asset(row: dict, kind: str, req: dict) -> tuple:
    """(Candidate または None, 候補にしない理由)"""
    catalog_kind = S.MATERIAL_TYPES[kind]["catalog_kind"]
    if row.get("kind") != catalog_kind:
        return None, None  # 種類が違うものは理由を残さない（多すぎるため）
    if row.get("usable") == "使用不可":
        return None, "使用不可"
    # 2枚組（比較用）の写真は、カットが明示的に求めた時だけ使う。
    # 普通の写真として混ざると、ビフォーアフターのような見せ方に誤用されるため
    if (COMPOSITE_TAG in split_tags(row.get("framing", ""))
            and COMPOSITE_TAG not in (req.get("framing_any") or [])):
        return None, "2枚組（比較用）の写真"

    subjects = split_tags(row.get("subjects", ""))
    if not subjects:
        return None, "被写体のタグが未記入"
    # subjects_all は「必ず写っていること」。1つでも無ければ候補にしない
    # 必須の被写体は完全一致で見る（部分一致だと「顔」が「洗顔の手元」に当たってしまう）
    missing_all = [w for w in (req.get("subjects_all") or []) if w not in subjects]
    if missing_all:
        return None, f"必須の被写体（{','.join(missing_all)}）が写っていない（素材: {','.join(subjects)}）"
    wanted_subjects = req.get("subjects_any") or []
    subject_hits = _overlap(wanted_subjects, subjects) + [w for w in (req.get("subjects_all") or []) if w in subjects]
    if wanted_subjects and not _overlap(wanted_subjects, subjects):
        return None, f"被写体が合わない（素材: {','.join(subjects)}）"
    # 動作を指定したカットは、動作も合っていること（「手元」が同じでも施術と準備は別の映像）
    wanted_actions = req.get("actions_any") or []
    asset_actions = split_tags(row.get("actions", ""))
    if wanted_actions and not _overlap(wanted_actions, asset_actions):
        return None, f"動作が合わない（素材: {','.join(asset_actions) or '未記入'}）"

    people_allowed = req.get("people_allowed") or []
    if people_allowed:
        if not row.get("people"):
            return None, "人物の欄が未記入"
        if row["people"] not in people_allowed:
            return None, f"人物が条件外（素材: {row['people']}）"
    face_allowed = req.get("face_allowed") or []
    if face_allowed:
        # 顔の写りが未確認の素材は、顔の条件があるカットに入れない（プライバシーの条件を素通りさせない）
        if not row.get("face"):
            return None, "顔の写りの欄が未記入"
        if row["face"] not in face_allowed:
            return None, f"顔の写りが条件外（素材: {row['face']}）"

    segment = None
    if kind == "miki_video":
        need = S.to_number(req.get("min_seconds"))
        need = 0.0 if need is None else need
        motion_min = req.get("motion_min") or "static"
        min_rank = S.MOTION_ORDER.index(motion_min) if motion_min in S.MOTION_ORDER else 0
        fits = [s for s in asset_segments(row)
                if s["duration"] + 1e-6 >= need
                and S.MOTION_ORDER.index(s.get("motion_class", "static")) >= min_rank]
        if not fits:
            return None, f"条件（{need}秒以上・動き{motion_min}以上）を満たす区間がない"
        segment = max(fits, key=lambda s: s["duration"])

    pending = []
    # 指定された同意と、素材そのものから決まる下限の、厳しい方を使う
    consent_min = max([req.get("consent_min") or "未確認", implied_consent_min(row)],
                      key=lambda c: CONSENT_RANK.get(c, 0))
    if CONSENT_RANK.get(row.get("consent", "未確認"), 0) < CONSENT_RANK.get(consent_min, 0):
        pending.append(f"同意が「{row.get('consent') or '未確認'}」（必要: {consent_min}）")
    if row.get("usable") != "使用可":
        pending.append(f"使用可否が「{row.get('usable') or '未確認'}」")

    action_hits = _overlap(wanted_actions, asset_actions)
    framing_hits = _overlap(req.get("framing_any") or [], split_tags(row.get("framing", "")))
    score = 3 * len(subject_hits) + 2 * len(action_hits) + len(framing_hits)
    if not pending:
        score += 3
    if row.get("usage_history"):
        score -= 1  # 最近使った素材は少し下げる
    matched = subject_hits + action_hits + framing_hits
    return Candidate(row["asset_id"], row.get("file_name", ""), score, segment, pending, matched), None


def search_cut(cut: dict, catalog_rows: list) -> CutResult:
    material = cut.get("material") or {}
    options = [{"type": material.get("preferred"), "requirements": material.get("requirements") or {},
                "photo_treatment": material.get("photo_treatment"), "note": ""}]
    options += material.get("fallbacks") or []

    notes, rejected = [], {}
    first_pending = []
    chosen, used_type, status = None, None, "不足"
    for idx, option in enumerate(options):
        kind = option.get("type")
        is_preferred = idx == 0
        if kind in S.NON_MATERIAL_TYPES:
            chosen, used_type = None, kind
            status = "割当OK" if is_preferred else "代替で対応"
            notes.append(f"{S.material_label(kind)}で作る" + (f"（{option.get('note')}）" if option.get("note") else ""))
            break
        if kind == "stock_video":
            notes.append("無料ストック動画は未導入（フェーズ3以降に検討）。今は割り当てない")
            continue
        if kind == "ai_video":
            notes.append("AI動画はフェーズ6の実験扱い。今は割り当てない")
            continue
        if kind not in S.MATERIAL_TYPES:
            continue

        ready, pending = [], []
        for row in catalog_rows:
            cand, reason = evaluate_asset(row, kind, option.get("requirements") or {})
            if cand is None:
                if reason and is_preferred:
                    rejected[row["asset_id"]] = reason
                continue
            (pending if cand.pending else ready).append(cand)
        ready.sort(key=lambda c: -c.score)
        pending.sort(key=lambda c: -c.score)
        if is_preferred:
            first_pending = pending
        if ready:
            chosen, used_type = ready[0], kind
            status = "割当OK" if is_preferred else "代替で対応"
            break
        if pending and is_preferred:
            # 確認待ちの候補しかない場合も、代替を探し続ける（勝手に割り当てない）
            notes.append(f"{S.material_label(kind)}は確認待ちの候補が {len(pending)}件あります")

    if chosen is None and used_type is None and first_pending:
        status = "確認待ち"
        used_type = material.get("preferred")
    elif status == "代替で対応" and first_pending:
        notes.append("第一希望の素材は確認が済めば使えます")

    missing = None
    preferred = material.get("preferred")
    preferred_ready = status == "割当OK" and used_type == preferred
    if preferred in ("miki_video", "photo_motion") and not preferred_ready:
        missing = {
            "cut_id": cut.get("id"),
            "type": preferred,
            "shows": (cut.get("visual") or {}).get("shows", ""),
            "person_action": (cut.get("visual") or {}).get("person_action", ""),
            "camera_move": (cut.get("visual") or {}).get("camera_move", ""),
            "requirements": material.get("requirements") or {},
            "seconds": round(_cut_seconds(cut), 2),
            "has_pending": bool(first_pending),
            "pending_ids": [c.asset_id for c in first_pending],
            "covered_by_fallback": status == "代替で対応",
            "fallback_type": used_type if status == "代替で対応" else None,
        }
    return CutResult(cut.get("id"), status, used_type, chosen, first_pending, rejected, notes, missing)


def _cut_seconds(cut: dict) -> float:
    return (S.to_number(cut.get("end")) or 0.0) - (S.to_number(cut.get("start")) or 0.0)


def search_plan(plan: dict, catalog_rows: list) -> list:
    return [search_cut(cut, catalog_rows) for cut in plan.get("cuts") or []]


def assume_confirmed(catalog_rows: list) -> list:
    """「同意・使用可否が確認できたら」を試算するための台帳の写し（使用不可はそのまま）。

    実際の割当には使わない。確認を進めればどこまで実写で作れるかを見せるためだけのもの。
    """
    out = []
    for row in catalog_rows:
        copy = dict(row)
        if copy.get("usable") != "使用不可":
            copy["usable"] = "使用可"
            if copy.get("consent") in ("", "未確認", None):
                copy["consent"] = "書面"
        out.append(copy)
    return out


def material_seconds_after_assignment(plan: dict, results: list) -> dict:
    by_type = {}
    for cut, res in zip(plan.get("cuts") or [], results):
        key = res.used_type if res.status in ("割当OK", "代替で対応") else f"未割当（{res.status}）"
        by_type[key] = round(by_type.get(key, 0.0) + _cut_seconds(cut), 2)
    return by_type


def shooting_requests(plan: dict, results: list) -> list:
    """不足素材を「撮ってほしいもの」にまとめる。同じ被写体・動作・構図はまとめて1件にする。"""
    groups = {}
    for res in results:
        m = res.missing
        if not m or m["type"] != "miki_video":
            continue
        req = m["requirements"]
        key = (tuple(req.get("subjects_all") or []), tuple(req.get("subjects_any") or []),
               tuple(req.get("actions_any") or []), tuple(req.get("framing_any") or []))
        g = groups.setdefault(key, {"cuts": [], "shows": [], "person_action": [], "camera_move": [],
                                    "seconds": 0.0, "people": set(), "face": set(), "consent": "未確認",
                                    "has_pending": False})
        g["cuts"].append(m["cut_id"])
        for k in ("shows", "person_action", "camera_move"):
            if m[k] and m[k] not in g[k]:
                g[k].append(m[k])
        wanted = S.to_number(req.get("min_seconds"))
        g["seconds"] = max(g["seconds"], m["seconds"] if wanted is None else wanted)
        g["people"].update(req.get("people_allowed") or [])
        g["face"].update(req.get("face_allowed") or [])
        if CONSENT_RANK.get(req.get("consent_min") or "未確認", 0) > CONSENT_RANK.get(g["consent"], 0):
            g["consent"] = req["consent_min"]
        g["has_pending"] = g["has_pending"] or m["has_pending"]
    requests = []
    for (subjects_all, subjects_any, actions, framing), g in groups.items():
        requests.append({
            "subjects_all": list(subjects_all), "subjects": list(subjects_any),
            "actions": list(actions), "framing": list(framing),
            "cuts": g["cuts"], "shows": g["shows"], "person_action": g["person_action"],
            "camera_move": g["camera_move"],
            # 使う長さに前後の余白を足して頼む（撮影の頭と終わりは使えないため）
            "record_seconds": int(round(g["seconds"] + 3)),
            "people": sorted(g["people"]), "face": sorted(g["face"]), "consent": g["consent"],
            "has_pending": g["has_pending"],
        })
    return requests


def shooting_request_text(plan: dict, requests: list) -> str:
    """MIKIさんにLINEで送れる形の撮影依頼（まだ送らない。文面だけ作る）。"""
    if not requests:
        return ""
    lines = [
        f"【撮影のお願い】リール「{plan.get('theme')}」",
        "",
        "次の動画を撮っていただけると、写真ではなく実際の映像でリールを作れます。",
        "",
    ]
    for i, q in enumerate(requests, start=1):
        lines.append(f"{i}. {' / '.join(q['shows'])}")
        if q["person_action"]:
            lines.append(f"   動き：{' / '.join(q['person_action'])}")
        if q["camera_move"]:
            lines.append(f"   撮り方：{' / '.join(q['camera_move'])}")
        lines.append(f"   長さ：{q['record_seconds']}秒くらい（前後に少し余裕をもって）")
        people = "・".join(q["people"]) if q["people"] else "指定なし"
        face = "・".join(q["face"]) if q["face"] else "指定なし"
        lines.append(f"   写ってよい人：{people}（顔の写り：{face}）")
        if q["consent"] in ("口頭", "書面"):
            lines.append(f"   お客様が写る場合：{q['consent']}での同意をお願いします")
        if q["has_pending"]:
            lines.append("   ※似た素材はありますが同意・使用可否が未確認です。確認できれば撮影は不要です")
        lines.append("")
    lines += [
        "撮影のときのお願い",
        "・スマホは縦向き",
        "・iPhoneの設定で「HDRビデオ」をオフ（色が崩れるのを防ぐため）",
        "・編集アプリで書き出さず、撮ったままの動画をアップロード（透かしが入らないように）",
        "・アップロード先：Googleドライブ「instagram投稿素材 ＞ 動画」フォルダ（今ある動画と同じ場所）",
    ]
    return "\n".join(lines)
