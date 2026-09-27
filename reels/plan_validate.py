"""リール設計図（plan.json）の検査（フェーズ2）。

レベル:
  error … 設計として成立しない／ルール違反。直すまで次に進まない
  warn  … 確認警告。人が見て問題なければそのままでよい（3秒ルールなど）
  info  … 参考情報（実写の動きがあるので3秒を超えてもよい、など）
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from reels import plan_schema as S
from reels.catalog import CONSENT_RANK, FACE_CHOICES, PEOPLE_CHOICES, ba_case_problems
from review_post import LP_LINK_WORDS, LP_PROFILE_WORD


@dataclass
class Finding:
    level: str
    code: str
    message: str
    cut_id: str | None = None

    def text(self) -> str:
        where = f"[{self.cut_id}] " if self.cut_id else ""
        mark = {"error": "❌", "warn": "⚠️", "info": "ℹ️"}[self.level]
        return f"{mark} {where}{self.message}"


@dataclass
class Report:
    findings: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def add(self, level, code, message, cut_id=None):
        self.findings.append(Finding(level, code, message, cut_id))

    @property
    def errors(self):
        return [f for f in self.findings if f.level == "error"]

    @property
    def warnings(self):
        return [f for f in self.findings if f.level == "warn"]


_num = S.to_number


def _cut_duration(cut: dict) -> float:
    return (_num(cut.get("end")) or 0.0) - (_num(cut.get("start")) or 0.0)


# ---------------------------------------------------------------------
# 全体の構造
# ---------------------------------------------------------------------

def check_top_level(plan: dict, r: Report) -> None:
    if plan.get("schema_version") != S.SCHEMA_VERSION:
        r.add("error", "schema_version", f"schema_version は {S.SCHEMA_VERSION} にしてください")
    for key in ("theme", "slug"):
        if not str(plan.get(key, "")).strip():
            r.add("error", f"missing_{key}", f"{key} が空です")
    purpose = plan.get("purpose") or {}
    for key, label in (("goal", "リールの目的"), ("audience", "誰に向けたか"),
                       ("viewer_takeaway", "見た人に残すこと"), ("desired_action", "見た人にしてほしい行動")):
        if not str(purpose.get(key, "")).strip():
            r.add("error", "missing_purpose", f"purpose.{key}（{label}）が空です")

    duration = plan.get("duration") or {}
    cls = duration.get("class")
    if cls not in S.DURATION_CLASSES:
        r.add("error", "duration_class", f"duration.class は {list(S.DURATION_CLASSES)} のどれかにしてください")
    if _num(duration.get("target_seconds")) is None:
        r.add("error", "duration_target", "duration.target_seconds（想定尺）が数字ではありません")
    if not str(duration.get("reason", "")).strip():
        r.add("warn", "duration_reason", "duration.reason（その尺にした理由）が空です")

    hook = plan.get("hook") or {}
    for key, label in (("text", "Hookの言葉"), ("visual", "Hookの映像"), ("why_it_stops", "指が止まる理由")):
        if not str(hook.get(key, "")).strip():
            r.add("error", "missing_hook", f"hook.{key}（{label}）が空です")

    script = plan.get("script") or []
    if not script:
        r.add("error", "missing_script", "script（台本）が空です")
    for part in script:
        if not isinstance(part, dict) or part.get("section") not in S.ROLES:
            r.add("error", "script_section", f"台本の section「{part.get('section')}」が不正です（{S.ROLES}）")


def check_timeline(plan: dict, r: Report) -> None:
    cuts = plan.get("cuts") or []
    if not cuts:
        r.add("error", "no_cuts", "cuts（カット構成）が空です")
        return

    ids = [c.get("id") for c in cuts]
    if len(set(ids)) != len(ids):
        r.add("error", "duplicate_cut_id", f"カットIDが重複しています: {ids}")

    expected = 0.0
    for cut in cuts:
        cid = cut.get("id")
        start, end = _num(cut.get("start")), _num(cut.get("end"))
        if start is None or end is None or end <= start:
            r.add("error", "cut_time", f"開始 {cut.get('start')}・終了 {cut.get('end')} が不正です", cid)
            continue
        if abs(start - expected) > S.TIME_EPSILON:
            kind = "すき間" if start > expected else "重なり"
            r.add("error", "cut_gap", f"前のカットとの間に{kind}があります（{expected:.2f}秒 → {start:.2f}秒）", cid)
        if end - start < S.MIN_CUT_SECONDS - S.TIME_EPSILON:
            r.add("error", "cut_too_short", f"{end - start:.2f}秒は短すぎます（{S.MIN_CUT_SECONDS}秒以上）", cid)
        if cut.get("role") not in S.ROLES:
            r.add("error", "cut_role", f"role「{cut.get('role')}」が不正です（{S.ROLES}）", cid)
        expected = end

    total = _num(cuts[-1].get("end")) or 0.0
    duration = plan.get("duration") or {}
    target = _num(duration.get("target_seconds"))
    if target is not None and abs(total - target) > S.TOTAL_TOLERANCE_SECONDS:
        r.add("warn", "total_vs_target", f"カットの合計 {total:.1f}秒 が想定尺 {target:.1f}秒 とずれています")
    cls = S.DURATION_CLASSES.get(duration.get("class"))
    if cls and not (cls["min"] - S.TIME_EPSILON <= total <= cls["max"] + S.TIME_EPSILON):
        r.add("warn", "total_vs_class",
              f"合計 {total:.1f}秒 は「{cls['label']}」（{cls['min']}〜{cls['max']}秒）の範囲外です")

    first, last = cuts[0], cuts[-1]
    if first.get("role") != "hook":
        r.add("error", "first_not_hook", "最初のカットの role が hook ではありません", first.get("id"))
    elif (_num(first.get("end")) or 0) > S.HOOK_MAX_END_SECONDS + S.TIME_EPSILON:
        r.add("warn", "hook_long",
              f"Hookのカットが {S.HOOK_MAX_END_SECONDS}秒を超えています。平均視聴は約3秒なので、"
              "見せたいものが冒頭に入っているか確認してください", first.get("id"))
    if last.get("role") != "cta":
        r.add("error", "last_not_cta", "最後のカットの role が cta ではありません", last.get("id"))


# ---------------------------------------------------------------------
# カットごとの中身
# ---------------------------------------------------------------------

def check_cut_fields(cut: dict, r: Report) -> None:
    cid = cut.get("id")
    if not str(cut.get("purpose", "")).strip():
        r.add("error", "cut_purpose", "purpose（何を伝えるカットか）が空です", cid)
    visual = cut.get("visual") or {}
    for key, label in (("shows", "何を映すか"), ("person_action", "人物の動き（いなければ「なし」）"),
                       ("camera_move", "カメラの動き")):
        if not str(visual.get(key, "")).strip():
            r.add("error", "cut_visual", f"visual.{key}（{label}）が空です", cid)
    if "caption" not in cut or not isinstance(cut.get("caption"), list):
        r.add("error", "cut_caption", "caption（テロップ）を配列で書いてください。無い場合は []", cid)
    narration = cut.get("narration")
    if not isinstance(narration, dict) or not isinstance(narration.get("has"), bool):
        r.add("error", "cut_narration", "narration.has（ナレーションの有無）を true/false で書いてください", cid)


def _check_requirements(kind: str, req: dict, cut: dict, r: Report, where: str) -> None:
    cid = cut.get("id")
    if not isinstance(req, dict):
        r.add("error", "requirements", f"{where}.requirements が書かれていません", cid)
        return
    if not req.get("subjects_any") and not req.get("subjects_all"):
        r.add("error", "requirements_subjects",
              f"{where}.requirements に被写体（subjects_all か subjects_any）がありません", cid)
    for person in req.get("people_allowed", []) or []:
        if person not in PEOPLE_CHOICES:
            r.add("error", "requirements_people", f"people_allowed「{person}」は {PEOPLE_CHOICES} から選んでください", cid)
    for face in req.get("face_allowed", []) or []:
        if face not in FACE_CHOICES:
            r.add("error", "requirements_face", f"face_allowed「{face}」は {FACE_CHOICES} から選んでください", cid)
    if req.get("consent_min") and req["consent_min"] not in CONSENT_RANK:
        r.add("error", "requirements_consent", f"consent_min は {list(CONSENT_RANK)} のどれかです", cid)
    if kind == "miki_video":
        min_seconds = _num(req.get("min_seconds"))
        if min_seconds is None:
            r.add("error", "requirements_seconds", f"{where}.requirements.min_seconds（必要な長さ）がありません", cid)
        elif min_seconds + S.TIME_EPSILON < _cut_duration(cut):
            r.add("warn", "requirements_seconds_short",
                  f"必要な長さ {min_seconds}秒 がカットの長さ {_cut_duration(cut):.1f}秒 より短いです", cid)
        if req.get("motion_min") and req["motion_min"] not in S.MOTION_ORDER:
            r.add("error", "requirements_motion", f"motion_min は {S.MOTION_ORDER} のどれかです", cid)


def check_material(cut: dict, r: Report) -> None:
    cid = cut.get("id")
    material = cut.get("material") or {}
    preferred = material.get("preferred")
    known = set(S.MATERIAL_TYPES) | set(S.NON_MATERIAL_TYPES)
    if preferred not in known:
        r.add("error", "material_preferred", f"material.preferred「{preferred}」が不正です（{sorted(known)}）", cid)
        return
    if preferred == "change_cut":
        r.add("error", "material_preferred", "change_cut は代替手段専用です。第一希望には使えません", cid)
    if preferred == "ai_video" and not S.AI_VIDEO_ENABLED:
        r.add("error", "ai_video_preferred",
              "AI動画はフェーズ6の実験扱いで、第一希望にはできません", cid)
    if preferred in S.MATERIAL_TYPES:
        _check_requirements(preferred, material.get("requirements"), cut, r, "material")
    if preferred == "photo_motion":
        treatment = material.get("photo_treatment") or {}
        if treatment.get("type") not in S.PHOTO_TREATMENTS:
            r.add("error", "photo_treatment",
                  f"photo_treatment.type は {list(S.PHOTO_TREATMENTS)} のどれかにしてください", cid)

    fallbacks = material.get("fallbacks")
    if preferred in S.MATERIAL_TYPES and not fallbacks:
        r.add("error", "no_fallback", "素材が無かった時の代替（fallbacks）がありません", cid)
    last_priority = S.MATERIAL_TYPES.get(preferred, {}).get("priority", 0)
    for i, fb in enumerate(fallbacks or []):
        kind = fb.get("type")
        if kind not in known:
            r.add("error", "fallback_type", f"代替 {i + 1} の type「{kind}」が不正です", cid)
            continue
        if kind == "ai_video" and not S.AI_VIDEO_ENABLED:
            r.add("warn", "ai_video_fallback",
                  "代替にAI動画が入っています。フェーズ6までは割り当てません（実験扱い）", cid)
        if kind in S.MATERIAL_TYPES:
            priority = S.MATERIAL_TYPES[kind]["priority"]
            if priority < last_priority:
                r.add("warn", "fallback_order",
                      f"代替の順番が優先順位と逆です（{S.material_label(kind)} が後ろにあります）", cid)
            last_priority = priority
            if kind in ("miki_video", "photo_motion"):
                _check_requirements(kind, fb.get("requirements"), cut, r, f"fallbacks[{i}]")
            if kind == "photo_motion" and (fb.get("photo_treatment") or {}).get("type") not in S.PHOTO_TREATMENTS:
                r.add("error", "photo_treatment", f"代替 {i + 1}（写真）に photo_treatment.type がありません", cid)


def check_slideshow_structure(plan: dict, r: Report) -> None:
    """写真を並べるだけの設計になっていないか（第一希望の素材で判定）。"""
    cuts = plan.get("cuts") or []
    total = sum(max(_cut_duration(c), 0) for c in cuts) or 1.0
    by_kind = {}
    for c in cuts:
        kind = (c.get("material") or {}).get("preferred", "?")
        by_kind[kind] = by_kind.get(kind, 0.0) + max(_cut_duration(c), 0)

    video_seconds = sum(v for k, v in by_kind.items() if k == "miki_video")
    photo_seconds = by_kind.get("photo_motion", 0.0)
    if not any((c.get("material") or {}).get("preferred") == "miki_video" for c in cuts):
        r.add("error", "no_video_cut",
              "実写動画を第一希望にしたカットが1つもありません（静止画だけの設計です）")
    elif photo_seconds / total > S.MAX_PHOTO_SHARE_WHEN_VIDEO + 1e-9:
        r.add("warn", "photo_share",
              f"写真のカットが全体の {photo_seconds / total:.0%} を占めています"
              f"（実写がある企画では {S.MAX_PHOTO_SHARE_WHEN_VIDEO:.0%} 以下が目安）")

    # 写真が続く区間を切り出し、上限を超えた区間ごとに全体の長さで1件ずつ指摘する
    runs, current = [], []
    for c in cuts:
        if S.is_photo_based((c.get("material") or {}).get("preferred", "")):
            current.append(c.get("id"))
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    longest = max((len(x) for x in runs), default=0)
    for run_ids in runs:
        if len(run_ids) > S.MAX_CONSECUTIVE_PHOTO_CUTS:
            r.add("error", "photo_run",
                  f"写真のカットが {len(run_ids)}つ続いています（{', '.join(str(x) for x in run_ids)}）。"
                  f"{S.MAX_CONSECUTIVE_PHOTO_CUTS}つまでにして、間に実写や文字の場面を挟んでください")

    r.metrics.update({
        "cut_count": len(cuts),
        "average_cut_seconds": round(total / len(cuts), 2) if cuts else 0,
        "seconds_by_preferred_material": {k: round(v, 2) for k, v in by_kind.items()},
        "video_share": round(video_seconds / total, 2),
        "photo_share": round(photo_seconds / total, 2),
        "longest_photo_run": longest,
    })


def check_pacing(cut: dict, r: Report) -> float:
    """カット内で「画面に変化の予定がない時間」を測る。3秒超は確認警告。"""
    cid = cut.get("id")
    start, end = _num(cut.get("start")), _num(cut.get("end"))
    if start is None or end is None:
        return 0.0
    events = {round(start, 2), round(end, 2)}
    for change in (cut.get("visual") or {}).get("changes", []) or []:
        at = _num(change.get("at"))
        if at is None or not (start - S.TIME_EPSILON <= at <= end + S.TIME_EPSILON):
            r.add("error", "change_time", f"changes の at={change.get('at')} がカットの時間外です", cid)
            continue
        events.add(round(at, 2))
    for cap in cut.get("caption", []) or []:
        for key in ("start", "end"):
            t = _num(cap.get(key))
            if t is not None and start <= t <= end:
                events.add(round(t, 2))
    points = sorted(events)
    gap = max((b - a for a, b in zip(points, points[1:])), default=0.0)
    if gap > S.CHANGE_GAP_WARN_SECONDS + S.TIME_EPSILON:
        material = cut.get("material") or {}
        req = material.get("requirements") or {}
        person_action = str((cut.get("visual") or {}).get("person_action", "")).strip()
        moving_video = (material.get("preferred") == "miki_video"
                        and person_action not in ("", "なし")
                        and req.get("motion_min", "low") != "static")
        if moving_video:
            r.add("info", "long_take_ok",
                  f"変化の予定がない時間が {gap:.1f}秒ありますが、実写の動き（{person_action}）があるので問題ありません", cid)
        else:
            r.add("warn", "change_gap",
                  f"{gap:.1f}秒間、画面に変化の予定がありません（確認警告）。"
                  "ズーム・パン・切り抜き・テロップの出入りなどを予定に入れるか、このままでよいか確認してください", cid)
    return gap


def check_captions(cut: dict, r: Report) -> None:
    cid = cut.get("id")
    start, end = _num(cut.get("start")), _num(cut.get("end"))
    previous_end = None
    for cap in cut.get("caption", []) or []:
        lines = cap.get("lines") or []
        if not isinstance(lines, list):
            r.add("error", "caption_lines_shape", "テロップの lines は配列で書いてください", cid)
            continue
        if not lines:
            r.add("error", "caption_empty", "テロップの lines が空です", cid)
            continue
        if len(lines) > S.CAPTION_MAX_LINES:
            r.add("error", "caption_lines", f"テロップが {len(lines)}行あります（{S.CAPTION_MAX_LINES}行まで）", cid)
        for line in lines:
            n = S.caption_length(line)
            if n > S.CAPTION_LINE_MAX:
                r.add("error", "caption_too_long", f"「{line}」は {n}文字です（{S.CAPTION_LINE_MAX}文字まで。分けてください）", cid)
            elif n > S.CAPTION_LINE_TARGET:
                r.add("warn", "caption_long", f"「{line}」は {n}文字です（目安 {S.CAPTION_LINE_TARGET}文字）", cid)
        cs, ce = _num(cap.get("start")), _num(cap.get("end"))
        if cs is None or ce is None or ce <= cs:
            r.add("error", "caption_time", f"テロップ「{lines[0]}」の開始・終了が不正です", cid)
            continue
        if start is not None and end is not None and (cs < start - S.TIME_EPSILON or ce > end + S.TIME_EPSILON):
            r.add("error", "caption_outside_cut", f"テロップ「{lines[0]}」がカットの時間からはみ出しています", cid)
        chars = sum(S.caption_length(line) for line in lines)
        need = chars / S.READING_CHARS_PER_SECOND
        if ce - cs + S.TIME_EPSILON < need:
            r.add("warn", "caption_short_display",
                  f"テロップ「{''.join(lines)}」は {ce - cs:.1f}秒表示ですが、読むのに約 {need:.1f}秒かかります", cid)
        if previous_end is not None and cs < previous_end - S.TIME_EPSILON:
            r.add("warn", "caption_overlap", "テロップの表示時間が前のテロップと重なっています", cid)
        previous_end = ce


def check_narration(plan: dict, r: Report) -> None:
    voice = plan.get("voice_script") or {}
    mode = voice.get("mode")
    if mode not in S.VOICE_MODES:
        r.add("error", "voice_mode", f"voice_script.mode は {list(S.VOICE_MODES)} のどれかにしてください")
        return
    lines_by_cut = {}
    for line in voice.get("lines", []) or []:
        lines_by_cut.setdefault(line.get("cut_id"), []).append(str(line.get("text", "")))
    cuts = plan.get("cuts") or []
    any_narration = False
    for cut in cuts:
        cid = cut.get("id")
        narration = cut.get("narration") or {}
        if not narration.get("has"):
            if lines_by_cut.get(cid):
                r.add("warn", "narration_mismatch", "ボイス台本に行がありますが narration.has が false です", cid)
            continue
        any_narration = True
        text = str(narration.get("line", "")).strip()
        if not text:
            r.add("error", "narration_line", "narration.has が true ですが line（読む文）が空です", cid)
            continue
        if text not in lines_by_cut.get(cid, []):
            r.add("error", "narration_not_in_voice_script", "narration.line がボイス台本（voice_script.lines）にありません", cid)
        need = len(text.replace(" ", "")) / S.NARRATION_CHARS_PER_SECOND
        if need > _cut_duration(cut) + S.TIME_EPSILON:
            r.add("warn", "narration_too_long",
                  f"ナレーションは約 {need:.1f}秒かかりますが、カットは {_cut_duration(cut):.1f}秒です", cid)
    if any_narration and mode == "none":
        r.add("error", "voice_mode_none", "ナレーションのあるカットがあるのに voice_script.mode が none です")
    if not any_narration and mode != "none":
        r.add("warn", "voice_mode_unused", "voice_script.mode がありますが、ナレーションのあるカットがありません")
    if (plan.get("duration") or {}).get("class") == "long" and not any_narration:
        r.add("warn", "long_without_voice", "長い尺（30秒超）なのにナレーションがありません。最後まで見てもらえるか確認してください")


# ---------------------------------------------------------------------
# 事実・BA・CTA・カバー
# ---------------------------------------------------------------------

def _texts_of_cut(cut: dict) -> list:
    texts = ["".join(c.get("lines") or []) for c in cut.get("caption", []) or []]
    narration = cut.get("narration") or {}
    if narration.get("has") and narration.get("line"):
        texts.append(str(narration["line"]))
    return texts


def _viewer_texts(plan: dict) -> list:
    """見た人に届く文を全部集める（どこに書いても同じ基準で見るため）。

    (表示名, 文, 出典を引くカットID) の形で返す。カットIDが None の文は、
    設計図全体の facts をまとめて出典として見る。
    """
    out = []
    for cut in plan.get("cuts") or []:
        cid = cut.get("id")
        out += [(f"{cid} のテロップ", t, cid) for t in _texts_of_cut(cut)]
    hook = (plan.get("hook") or {}).get("text")
    if hook:
        out.append(("Hook", str(hook), None))
    for part in plan.get("script") or []:
        if part.get("text"):
            out.append((f"台本（{S.ROLE_LABELS.get(part.get('section'), part.get('section'))}）",
                        str(part["text"]), None))
    for line in (plan.get("voice_script") or {}).get("lines") or []:
        if line.get("text"):
            out.append((f"ボイス台本 {line.get('cut_id')}", str(line["text"]), line.get("cut_id")))
    cta = plan.get("cta") or {}
    for key, label in (("message", "CTA"), ("lp_guidance_text", "CTAのLP誘導")):
        if cta.get(key):
            out.append((label, str(cta[key]), None))
    out += [("カバー案", str(t), None) for t in (plan.get("cover") or {}).get("title_lines") or []]
    return out


def _normalized(text: str) -> str:
    return unicodedata.normalize("NFKC", text).replace(" ", "")


def check_facts_and_words(plan: dict, r: Report) -> None:
    sourced_by_cut, all_claims = {}, []
    for cut in plan.get("cuts") or []:
        cid = cut.get("id")
        claims = []
        for fact in cut.get("facts") or []:
            if fact.get("source_type") not in S.FACT_SOURCE_TYPES or not str(fact.get("source", "")).strip():
                r.add("error", "fact_source",
                      f"事実「{fact.get('claim')}」の出典（source_type / source）が不正か空です", cid)
                continue
            claims.append(str(fact.get("claim", "")))
        sourced_by_cut[cid] = _normalized("".join(claims))
        all_claims += claims
    all_sourced = _normalized("".join(all_claims))

    texts = _viewer_texts(plan)
    for label, text, cid in texts:
        sourced = sourced_by_cut.get(cid, "") if cid in sourced_by_cut else all_sourced
        for m in S.NUMERIC_CLAIM_RE.finditer(text):
            if _normalized(m.group(0)) not in sourced:
                r.add("error", "numeric_claim_without_source",
                      f"{label}の「{m.group(0)}」を含む表現に出典がありません"
                      "（facts に claim と出典を書くか、数字を外してください）", cid)

    for word in S.FORBIDDEN_WORDS:
        # 表記ゆれ（Amrta / amrta）も拾う
        hits = [(label, t) for label, t, _ in texts if word.upper() in t.upper()]
        if hits:
            r.add("error", "forbidden_word",
                  f"使ってはいけない言葉「{word}」が入っています（{hits[0][0]}：「{hits[0][1]}」）")
    for word in S.GUARANTEE_WORDS:
        hits = [(label, t) for label, t, _ in texts if word in t]
        if hits:
            r.add("warn", "guarantee_word",
                  f"効果を約束する言い方「{word}」があります（{hits[0][0]}：「{hits[0][1]}」）。"
                  "個人差のある施術で言い切らないか確認してください")


def check_before_after(plan: dict, r: Report, ba_cases: list | None, catalog_ids: set | None) -> None:
    """BAは「確認済み」の登録があるカットだけ許可する。確認できなければ作らない。"""
    for cut in plan.get("cuts") or []:
        cid = cut.get("id")
        material = cut.get("material") or {}
        req_list = [material.get("requirements") or {}] + [
            fb.get("requirements") or {} for fb in material.get("fallbacks", []) or []]
        case_ids = {q.get("ba_case_id") for q in req_list if q.get("ba_case_id")}
        uses_ba = "before_after" in (cut.get("tags") or []) or case_ids
        if not uses_ba:
            continue
        if not case_ids:
            r.add("error", "ba_without_case", "ビフォーアフターのカットに ba_case_id がありません。BA登録なしでは作りません", cid)
            continue
        if ba_cases is None:
            r.add("error", "ba_unverifiable", "BA登録を確認できないため、このBAカットは作りません（オフライン検査）", cid)
            continue
        by_id = {c.get("case_id"): c for c in ba_cases}
        for case_id in case_ids:
            problems = ba_case_problems(by_id.get(case_id), catalog_ids or set())
            for problem in problems:
                r.add("error", "ba_not_verified", f"BA「{case_id}」: {problem}。確認が済むまでこのカットは作りません", cid)
            if not problems:
                allowed = str(by_id[case_id].get("allowed_text", ""))
                for text in _texts_of_cut(cut):
                    if text and text not in allowed:
                        r.add("error", "ba_text_not_allowed",
                              f"BAカットの文「{text}」が、BA登録の「使ってよい説明文」にありません", cid)


def check_cta_and_cover(plan: dict, r: Report) -> None:
    cuts = plan.get("cuts") or []
    cta = plan.get("cta") or {}
    if not str(cta.get("message", "")).strip():
        r.add("error", "cta_message", "cta.message（見た人にしてほしい行動）が空です")
    last_texts = _texts_of_cut(cuts[-1]) if cuts else []
    pool = " ".join(last_texts + [str(cta.get("lp_guidance_text", ""))])
    if not (LP_PROFILE_WORD in pool and any(w in pool for w in LP_LINK_WORDS)):
        r.add("error", "cta_lp_guidance",
              "最後のカットか cta.lp_guidance_text に「プロフィール」＋「リンク」の誘導がありません（LP誘導の恒久ルール）")

    cover = plan.get("cover") or {}
    lines = cover.get("title_lines") or []
    if not lines:
        r.add("error", "cover_title", "cover.title_lines（カバーのタイトル）が空です")
    if len(lines) > S.COVER_MAX_LINES:
        r.add("warn", "cover_lines", f"カバーのタイトルが {len(lines)}行です（{S.COVER_MAX_LINES}行が目安）")
    for line in lines:
        if S.caption_length(line) > S.COVER_LINE_TARGET:
            r.add("warn", "cover_line_long",
                  f"カバーの「{line}」は {S.caption_length(line)}文字です（一覧で読めるのは {S.COVER_LINE_TARGET}文字程度）")
    if cover.get("background_cut") not in {c.get("id") for c in cuts}:
        r.add("error", "cover_background", "cover.background_cut が存在しないカットIDです")


def validate_plan(plan: dict, *, ba_cases: list | None = None, catalog_ids: set | None = None) -> Report:
    r = Report()
    # 形の崩れた設計図でも、例外で止めずに ❌ として報告する（検査結果と design.md を必ず残す）
    plan, problems = S.sanitize_plan(plan)
    for code, message, cid in problems:
        r.add("error", code, message, cid)
    check_top_level(plan, r)
    check_timeline(plan, r)
    max_gap = 0.0
    for cut in plan.get("cuts") or []:
        check_cut_fields(cut, r)
        check_material(cut, r)
        check_captions(cut, r)
        max_gap = max(max_gap, check_pacing(cut, r))
    check_slideshow_structure(plan, r)
    check_narration(plan, r)
    check_facts_and_words(plan, r)
    check_before_after(plan, r, ba_cases, catalog_ids)
    if plan.get("cuts"):
        check_cta_and_cover(plan, r)
    r.metrics["max_change_gap_seconds"] = round(max_gap, 2)
    return r
