"""テーマからリールの設計図を作る流れの入口（フェーズ2）。

  python3 -m reels.plan new "背中が自分では見えないからこそケアが大切" --slug back-care
      → reels/work/plans/<slug>/plan.json の雛形を作り、台帳にある素材の傾向を表示する
        （中身は Claude Code が rules/reel-planning.md に沿って書く）

  python3 -m reels.plan check reels/work/plans/<slug>/plan.json
      → 設計図の検査 → 台帳から素材を探す → 不足素材と撮影依頼を作る
        → design.md（人が読む設計図）と shooting_request.txt を同じフォルダに書く
        ❌ があれば終了コード 1

  --offline を付けると台帳・BA登録を読まずに検査だけする（BAカットは確認できないので作らない扱い）
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from reels import config
from reels import plan_schema as S


def _skeleton(theme: str, slug: str) -> dict:
    return {
        "schema_version": S.SCHEMA_VERSION,
        "theme": theme,
        "slug": slug,
        "purpose": {"goal": "", "audience": "", "viewer_takeaway": "", "desired_action": ""},
        "duration": {"class": "short", "target_seconds": 15, "reason": ""},
        "hook": {"text": "", "visual": "", "why_it_stops": ""},
        "script": [],
        "voice_script": {"mode": "none", "lines": []},
        "cuts": [],
        "cta": {"message": "", "lp_guidance_text": ""},
        "cover": {"title_lines": [], "background_cut": "c01", "note": ""},
        "open_questions": [],
    }


def catalog_summary(rows: list) -> str:
    from reels.catalog import split_tags
    lines = []
    for kind in ("動画", "写真"):
        items = [r for r in rows if r["kind"] == kind]
        subjects = Counter(t for r in items for t in split_tags(r.get("subjects", "")))
        ready = sum(1 for r in items if r.get("usable") == "使用可")
        lines.append(f"{kind} {len(items)}件（使用可 {ready}件）: "
                     + "、".join(f"{k}×{v}" for k, v in subjects.most_common(15)))
    return "\n".join(lines)


def cmd_new(args) -> int:
    from reels.catalog import Catalog
    plan_dir = config.PLANS_DIR / args.slug
    path = plan_dir / "plan.json"
    if path.exists() and not args.force:
        print(f"すでにあります: {path}（上書きするなら --force）", file=sys.stderr)
        return 1
    plan_dir.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_skeleton(args.theme, args.slug), f, ensure_ascii=False, indent=2)
    print(f"雛形を作りました: {path.relative_to(config.REPO_ROOT)}")
    print("書き方: rules/reel-planning.md")
    print("\n台帳にある素材の傾向:")
    print(catalog_summary(Catalog().all()))
    return 0


def run_check(plan_path: Path, *, offline: bool = False) -> tuple:
    from reels.asset_search import (assume_confirmed, search_plan, shooting_request_text,
                                    shooting_requests)
    from reels.plan_report import build_markdown
    from reels.plan_validate import validate_plan

    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)

    rows, ba_cases, catalog_ids = [], None, None
    if not offline:
        from reels.catalog import BARegistry, Catalog, _open_spreadsheet
        spreadsheet = _open_spreadsheet()
        rows = Catalog(spreadsheet).all()
        ba_cases = BARegistry(spreadsheet).all()
        catalog_ids = {r["asset_id"] for r in rows}

    report = validate_plan(plan, ba_cases=ba_cases, catalog_ids=catalog_ids)
    # 検査で ❌ があっても素材探索はする（どこが足りないかは直す時の材料になる）。
    # 書き間違いで形が崩れていても止まらないよう、ここから先は整形した写しを使う
    from reels import plan_schema as S
    safe_plan, _ = S.sanitize_plan(plan)
    results = search_plan(safe_plan, rows)
    confirmed_results = search_plan(safe_plan, assume_confirmed(rows))
    requests = shooting_requests(safe_plan, results)
    request_text = shooting_request_text(safe_plan, requests)
    markdown = build_markdown(safe_plan, report, results, rows, requests, request_text, confirmed_results)

    out_dir = plan_path.parent
    (out_dir / "design.md").write_text(markdown, encoding="utf-8")
    (out_dir / "shooting_request.txt").write_text(request_text, encoding="utf-8")
    with open(out_dir / "check_result.json", "w", encoding="utf-8") as f:
        json.dump({
            "errors": [x.__dict__ for x in report.errors],
            "warnings": [x.__dict__ for x in report.warnings],
            "info": [x.__dict__ for x in report.findings if x.level == "info"],
            "metrics": report.metrics,
            "assignments": [{"cut_id": r.cut_id, "status": r.status, "used_type": r.used_type,
                             "asset_id": r.chosen.asset_id if r.chosen else None,
                             "segment": r.chosen.segment if r.chosen else None,
                             "pending": [c.asset_id for c in r.pending_candidates]} for r in results],
            "shooting_requests": requests,
        }, f, ensure_ascii=False, indent=2)
    return plan, report, results, requests


def cmd_check(args) -> int:
    plan_path = Path(args.plan)
    plan, report, results, requests = run_check(plan_path, offline=args.offline)
    print(f"検査: ❌ {len(report.errors)}件 / ⚠️ {len(report.warnings)}件 / "
          f"ℹ️ {len([f for f in report.findings if f.level == 'info'])}件")
    for f in report.findings:
        print("  " + f.text())
    print("割当: " + " / ".join(f"{r.cut_id}:{r.status}" for r in results))
    print(f"撮影依頼: {len(requests)}件")
    print(f"設計図: {(plan_path.parent / 'design.md')}")
    return 1 if report.errors else 0


def main(argv=None):
    from load_env import load_from_zshrc
    load_from_zshrc()

    parser = argparse.ArgumentParser(description="テーマからリールの設計図を作る")
    sub = parser.add_subparsers(dest="cmd", required=True)
    new = sub.add_parser("new")
    new.add_argument("theme")
    new.add_argument("--slug", required=True, help="英小文字とハイフン（フォルダ名になる）")
    new.add_argument("--force", action="store_true")
    check = sub.add_parser("check")
    check.add_argument("plan")
    check.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)
    return cmd_new(args) if args.cmd == "new" else cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
