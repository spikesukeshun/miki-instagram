"""設計図・検査結果・素材の割当を、人が読める1枚のMarkdownにまとめる（フェーズ2）。"""

from __future__ import annotations

from reels import plan_schema as S
from reels.asset_search import material_seconds_after_assignment


def _sec(value) -> str:
    n = S.to_number(value)
    return "?" if n is None else f"{n:.1f}"


def _fmt_time(cut: dict) -> str:
    return f"{_sec(cut.get('start'))}–{_sec(cut.get('end'))}秒"


def _cell(text) -> str:
    return str(text or "").replace("|", "／").replace("\n", " ")


def _material_cell(cut: dict) -> str:
    material = cut.get("material") or {}
    parts = [S.material_label(material.get("preferred", ""))]
    treatment = material.get("photo_treatment") or {}
    if treatment.get("type"):
        parts[0] += f"（{S.PHOTO_TREATMENTS.get(treatment['type'], treatment['type'])}）"
    for fb in material.get("fallbacks") or []:
        label = S.material_label(fb.get("type", ""))
        t = (fb.get("photo_treatment") or {}).get("type")
        if t:
            label += f"（{S.PHOTO_TREATMENTS.get(t, t)}）"
        parts.append(label)
    return " → ".join(parts)


def _assign_cell(res, rows_by_id: dict, assumed: bool = False) -> str:
    """assumed=True は「同意・使用可否が確認できたら」の試算。本割当と同じ記号にしない。"""
    if assumed:
        if res.status in ("割当OK", "代替で対応"):
            label = res.chosen.asset_id if res.chosen else S.material_label(res.used_type)
            return f"⬜ {label}（確認後）"
        return "❌ 不足"
    if res.status == "割当OK" and res.chosen:
        seg = res.chosen.segment
        where = f" {seg['start']:.1f}-{seg['end']:.1f}秒" if seg else ""
        return f"✅ {res.chosen.asset_id}{where}"
    if res.status == "割当OK":
        return f"✅ {S.material_label(res.used_type)}"
    if res.status == "代替で対応":
        base = f"🔁 {S.material_label(res.used_type)}"
        if res.chosen:
            base += f" {res.chosen.asset_id}"
        if res.pending_candidates:
            base += f"（第一希望の候補 {res.pending_candidates[0].asset_id} は同意・使用可否の確認待ち）"
        return base
    if res.status == "確認待ち":
        c = res.pending_candidates[0]
        return f"⏳ {c.asset_id}（{' / '.join(c.pending)}）"
    return "❌ 不足"


def _captions(cut: dict) -> str:
    caps = cut.get("caption") or []
    return " / ".join("「" + "＼".join(c.get("lines") or []) + f"」{_sec(c.get('start'))}s" for c in caps) or "なし"


def _share_text(plan: dict, results: list) -> str:
    return "、".join(
        f"{S.material_label(k) if k in S.MATERIAL_TYPES or k in S.NON_MATERIAL_TYPES else k} {v:.1f}秒"
        for k, v in material_seconds_after_assignment(plan, results).items())


def build_markdown(plan: dict, report, results: list, catalog_rows: list, requests: list,
                   request_text: str, confirmed_results: list | None = None) -> str:
    confirmed_results = confirmed_results or results
    rows_by_id = {r["asset_id"]: r for r in catalog_rows}
    cuts = plan.get("cuts") or []
    purpose = plan.get("purpose") or {}
    duration = plan.get("duration") or {}
    hook = plan.get("hook") or {}
    cover = plan.get("cover") or {}
    cta = plan.get("cta") or {}
    voice = plan.get("voice_script") or {}
    m = report.metrics
    cls = S.DURATION_CLASSES.get(duration.get("class"), {})

    out = [f"# リール設計図：{plan.get('theme')}", ""]
    out += [
        "## 企画",
        "",
        f"- **目的**：{purpose.get('goal', '')}",
        f"- **誰に**：{purpose.get('audience', '')}",
        f"- **見た人に残すこと**：{purpose.get('viewer_takeaway', '')}",
        f"- **してほしい行動**：{purpose.get('desired_action', '')}",
        f"- **想定尺**：{duration.get('target_seconds')}秒（{cls.get('label', '')}）— {duration.get('reason', '')}",
        f"- **Hook**：「{hook.get('text', '')}」／映像：{hook.get('visual', '')}",
        f"  - 指が止まる理由：{hook.get('why_it_stops', '')}",
        f"- **CTA**：{cta.get('message', '')}",
        f"- **カバー案**：「{' ＼ '.join(cover.get('title_lines') or [])}」（背景：{cover.get('background_cut', '')}）"
        + (f" — {cover.get('note')}" if cover.get("note") else ""),
        "",
    ]

    total = (S.to_number(cuts[-1].get("end")) or 0.0) if cuts else 0.0
    first = m.get("seconds_by_preferred_material", {})
    out += [
        "## 動画としての設計になっているか",
        "",
        f"- カット数 {m.get('cut_count')}／平均 {m.get('average_cut_seconds')}秒／合計 {total:.1f}秒",
        "- 第一希望の素材の内訳："
        + "、".join(f"{S.material_label(k)} {v:.1f}秒" for k, v in first.items()),
        f"- 実写動画の割合（第一希望）：{m.get('video_share', 0):.0%}／写真の割合：{m.get('photo_share', 0):.0%}"
        f"／写真カットの最大連続：{m.get('longest_photo_run')}",
        f"- 画面に変化の予定がない最長時間：{m.get('max_change_gap_seconds')}秒",
        "- 今ある素材で割り当てた結果：" + _share_text(plan, results),
        "- 台帳の同意・使用可否が確認できた場合（試算）：" + _share_text(plan, confirmed_results),
        "",
    ]

    out += [
        "## カット構成",
        "",
        "| 時間 | 役割 | 伝えること | 映すもの | 人物の動き | カメラ | 素材（第一希望 → 代替） | 今ある素材での割当 | 確認後の割当（試算） | テロップ | ナレーション |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for cut, res, conf in zip(cuts, results, confirmed_results):
        visual = cut.get("visual") or {}
        narration = cut.get("narration") or {}
        out.append("| " + " | ".join([
            _fmt_time(cut),
            S.ROLE_LABELS.get(cut.get("role"), cut.get("role", "")),
            _cell(cut.get("purpose")),
            _cell(visual.get("shows")),
            _cell(visual.get("person_action")),
            _cell(visual.get("camera_move")),
            _cell(_material_cell(cut)),
            _cell(_assign_cell(res, rows_by_id)),
            _cell(_assign_cell(conf, rows_by_id, assumed=True)),
            _cell(_captions(cut)),
            _cell(narration.get("line") if narration.get("has") else "なし"),
        ]) + " |")
    out.append("")

    out += ["## 画面の変化の予定", ""]
    for cut in cuts:
        changes = (cut.get("visual") or {}).get("changes") or []
        items = "、".join(f"{_sec(c.get('at'))}秒 {c.get('what', '')}" for c in changes) or "（カットの切り替わりのみ）"
        out.append(f"- **{cut.get('id')}**（{_fmt_time(cut)}）{items}")
    out.append("")

    out += ["## 台本", ""]
    for part in plan.get("script") or []:
        out.append(f"- **{S.ROLE_LABELS.get(part.get('section'), part.get('section'))}**：{part.get('text', '')}")
    out += ["", f"## ボイス台本（{S.VOICE_MODES.get(voice.get('mode'), voice.get('mode'))}）", ""]
    if voice.get("lines"):
        for line in voice["lines"]:
            reading = f"（読み：{line['reading']}）" if line.get("reading") else ""
            out.append(f"- {line.get('cut_id')}：{line.get('text')}{reading}")
    else:
        out.append("- なし（テロップと音楽で見せる）")
    out.append("")

    out += ["## 検査結果", ""]
    if not report.findings:
        out.append("- 指摘なし")
    for level in ("error", "warn", "info"):
        for f in [x for x in report.findings if x.level == level]:
            out.append(f"- {f.text()}")
    out.append("")

    out += ["## 各カットの素材の探索結果", ""]
    for cut, res in zip(cuts, results):
        out.append(f"### {cut.get('id')}（{_fmt_time(cut)}）{res.status}")
        if res.chosen:
            c = res.chosen
            seg = f"、使う区間 {c.segment['start']:.1f}-{c.segment['end']:.1f}秒（動き:{c.segment.get('motion_class')}）" if c.segment else ""
            row = rows_by_id.get(c.asset_id, {})
            out.append(f"- 採用候補：{c.asset_id} {row.get('file_name', '')}（合った条件：{'・'.join(c.matched) or '-'}{seg}）")
        for c in res.pending_candidates[:3]:
            out.append(f"- 確認待ちの候補：{c.asset_id} {rows_by_id.get(c.asset_id, {}).get('file_name', '')} → {' / '.join(c.pending)}")
        for note in res.notes:
            out.append(f"- {note}")
        if res.rejected:
            shown = list(res.rejected.items())[:4]
            out.append("- 候補にしなかった素材：" + "、".join(f"{k}（{v}）" for k, v in shown)
                       + (f" ほか{len(res.rejected) - len(shown)}件" if len(res.rejected) > len(shown) else ""))
        out.append("")

    missing = [r.missing for r in results if r.missing]
    out += ["## 不足素材", ""]
    if not missing:
        out.append("- なし")
    for mm in missing:
        req = mm["requirements"]
        if mm.get("fallback_type") == "change_cut":
            state = "代替が「カットの内容を変更する」なので、素材が無ければ企画を変える必要がある"
        elif mm["covered_by_fallback"]:
            state = "代替で作れるが、第一希望の素材があると良い"
        else:
            state = "必要（代替も無い）"
        if mm["has_pending"]:
            state += "／似た素材は確認待ち：" + "、".join(mm["pending_ids"])
        subjects = [f"{x}（必須）" for x in req.get("subjects_all") or []] + list(req.get("subjects_any") or [])
        actions = f"・動作 {','.join(req['actions_any'])}" if req.get("actions_any") else ""
        out.append(f"- **{mm['cut_id']}** {S.material_label(mm['type'])}：{mm['shows']}"
                   f"（被写体 {','.join(subjects) or '-'}{actions}・{mm['seconds']}秒）— {state}")
    out += ["", "## 撮影依頼（MIKIさん向けの文面・未送信）", ""]
    out.append("```")
    out.append(request_text or "撮影依頼なし")
    out.append("```")
    out.append("")

    questions = plan.get("open_questions") or []
    out += ["## 作る前に確認すること", ""]
    out += [f"- {q}" for q in questions] or ["- なし"]
    out.append("")
    return "\n".join(out)
