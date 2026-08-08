import type { ScoredPost, ThemeStats } from "../types";
import type { PeriodComparison, PeriodKpi } from "./analytics";
import { SUCCESS_SCORE, themeDef } from "../config";
import { fmtInt, fmtPct, fmtDeltaPct, ratio } from "./format";

/**
 * ルールベースのAI分析文生成。
 * すべての判断に「なぜ（根拠となる数値比較）」を必ず添える。
 * dashboard_data.json の claude_comment（Claude Codeの所見）があれば併記される。
 */

export interface Finding {
  title: string;
  detail: string;
  why: string;
}

export interface WeeklyAnalysis {
  grade: "S" | "A" | "B" | "C" | "D" | "—";
  gradeScore: number | null;
  summary: string;
  good: Finding[];
  improve: Finding[];
  causes: Finding[];
  successFactors: Finding[];
  failureFactors: Finding[];
  priorities: Finding[];
}

const gradeOf = (score: number | null): WeeklyAnalysis["grade"] => {
  if (score == null) return "—";
  if (score >= 80) return "S";
  if (score >= 65) return "A";
  if (score >= 50) return "B";
  if (score >= 35) return "C";
  return "D";
};

interface KpiDelta {
  key: string;
  label: string;
  stars: number;
  cur: number | null;
  prev: number | null;
  delta: number | null;
  isRate: boolean;
}

function deltas(cur: PeriodKpi | null, prev: PeriodKpi | null): KpiDelta[] {
  const defs: { key: keyof PeriodKpi & string; label: string; stars: number; isRate: boolean }[] = [
    { key: "pvRate", label: "プロフィール誘導率", stars: 5, isRate: true },
    { key: "saveRate", label: "保存率", stars: 5, isRate: true },
    { key: "followerGain", label: "フォロワー純増", stars: 5, isRate: false },
    { key: "reach", label: "リーチ", stars: 4, isRate: false },
    { key: "views", label: "インプレッション", stars: 4, isRate: false },
    { key: "profileViews", label: "プロフィール閲覧", stars: 5, isRate: false },
  ];
  return defs.map((d) => {
    const c = (cur?.[d.key] ?? null) as number | null;
    const p = (prev?.[d.key] ?? null) as number | null;
    return { ...d, cur: c, prev: p, delta: ratio(c, p) };
  });
}

const fmtVal = (v: number | null, isRate: boolean) => (isRate ? fmtPct(v) : fmtInt(v));

export function analyzeWeek(
  cmp: PeriodComparison,
  periodPosts: ScoredPost[],
  themes: ThemeStats[],
): WeeklyAnalysis {
  const { current, previous } = cmp;
  const ds = deltas(current, previous);
  const score = current?.compositeScore ?? null;
  const grade = gradeOf(score);

  const good: Finding[] = [];
  const improve: Finding[] = [];
  const causes: Finding[] = [];

  // KPIの前期比から良かった点・改善点・原因分析を作る（星の重い順）
  const ranked = [...ds].sort((a, b) => b.stars - a.stars);
  for (const d of ranked) {
    if (d.delta == null) continue;
    const line = `${d.label}: ${fmtVal(d.prev, d.isRate)} → ${fmtVal(d.cur, d.isRate)}（${fmtDeltaPct(d.delta)}）`;
    if (d.delta >= 0.1 && good.length < 3) {
      good.push({
        title: `${d.label}が改善（${fmtDeltaPct(d.delta)}）`,
        detail: line,
        why: `重要度★${d.stars}の指標が前期間より10%以上伸びたため。${d.isRate ? "率の改善は投稿の質の向上を意味する" : "母数の拡大はファネル全体の入口を広げる"}`,
      });
    }
    if (d.delta <= -0.1 && improve.length < 3) {
      improve.push({
        title: `${d.label}が低下（${fmtDeltaPct(d.delta)}）`,
        detail: line,
        why: `重要度★${d.stars}の指標が前期間より10%以上下がったため。DM予約への導線上、優先的に立て直す必要がある`,
      });
    }
  }

  // 原因分析：期間内のトップ/ボトム投稿とテーマ構成に帰着させる
  const withIns = periodPosts.filter((p) => p.insights);
  const top = [...withIns].sort((a, b) => b.score - a.score)[0];
  const bottom = withIns.length > 1 ? [...withIns].sort((a, b) => a.score - b.score)[0] : undefined;
  const reachDelta = ds.find((d) => d.key === "reach")?.delta;

  if (current && previous && current.postCount !== previous.postCount) {
    const grew = current.postCount > previous.postCount;
    const reachUp = (reachDelta ?? 0) > 0;
    causes.push({
      title: `投稿本数の変化（${previous.postCount}本 → ${current.postCount}本）`,
      detail:
        grew === reachUp
          ? "投稿本数はリーチ・インプレッション総量に直結する。総量系KPIの増減はまず本数差で説明できる"
          : grew
            ? `本数が増えたのにリーチは${fmtDeltaPct(reachDelta)}。1本あたりの届き方が弱く、量より切り口の見直しが必要`
            : `本数が減ったのにリーチは${fmtDeltaPct(reachDelta)}。1本あたりの質（届き方）が上がっているサイン`,
      why: `本数${previous.postCount}→${current.postCount}本に対しリーチが${fmtDeltaPct(reachDelta)}と、増減の向きを比較して判断`,
    });
  }
  if (top) {
    causes.push({
      title: "期間内トップ投稿の寄与",
      detail: `「${top.titleLine}」（${themeDef(top.theme).label}）がスコア${Math.round(top.score)}点、リーチ${fmtInt(top.insights?.reach)}・保存率${fmtPct(top.saveRate)}・誘導率${fmtPct(top.pvRate)}`,
      why: "期間KPIは少数の当たり投稿に大きく引っ張られる。伸びた指標はこの投稿の性質（テーマ・切り口）で説明できる可能性が高い",
    });
  }
  if (bottom && bottom.score < SUCCESS_SCORE) {
    causes.push({
      title: "低スコア投稿の影響",
      detail: `「${bottom.titleLine}」（${themeDef(bottom.theme).label}）がスコア${Math.round(bottom.score)}点にとどまり、平均を押し下げた`,
      why: `成功ライン${SUCCESS_SCORE}点を下回る投稿が混ざると期間平均スコアが下がるため`,
    });
  }

  // 成功要因・失敗要因：テーマ統計から
  const okThemes = themes.filter((t) => t.count >= 3).sort((a, b) => b.totalScore - a.totalScore);
  const successFactors: Finding[] = [];
  const failureFactors: Finding[] = [];
  if (okThemes.length) {
    const best = okThemes[0];
    successFactors.push({
      title: `勝ちテーマ: ${themeDef(best.theme).label}`,
      detail: `平均スコア${Math.round(best.avgScore)}点・成功率${fmtPct(best.successRate, 0)}・平均保存率${fmtPct(best.avgSaveRate)}・平均誘導率${fmtPct(best.avgPvRate)}`,
      why: `${best.count}投稿の実績で全テーマ中もっとも総合スコアが高いため（総合 = 全期間6割 + 直近8週4割）`,
    });
    const worst = okThemes[okThemes.length - 1];
    if (worst.theme !== best.theme) {
      failureFactors.push({
        title: `苦戦テーマ: ${themeDef(worst.theme).label}`,
        detail: `平均スコア${Math.round(worst.avgScore)}点・成功率${fmtPct(worst.successRate, 0)}。件数を絞るか切り口の変更が必要`,
        why: `${worst.count}投稿の実績で総合スコアが最下位のため。同じ作り方を続けても数字は変わらない`,
      });
    }
  }
  if (top) {
    successFactors.push({
      title: "高スコア投稿の共通点",
      detail: `保存率・誘導率が高い投稿は「あとで見返したい実用情報」か「MIKI個人への興味」を起点にしている`,
      why: `トップ投稿「${top.titleLine}」の保存率${fmtPct(top.saveRate)}・誘導率${fmtPct(top.pvRate)}は参照分布の上位。星5指標が高い投稿がスコア上位に来る設計のため`,
    });
  }
  const lowSaves = withIns.filter((p) => p.saveRate != null && p.saveRate === 0);
  if (lowSaves.length) {
    failureFactors.push({
      title: `保存ゼロの投稿が${lowSaves.length}本`,
      detail: "読み切りで完結してしまい「あとで使う理由」がない構成だった可能性が高い",
      why: "保存は★5指標。保存率0%の投稿はスコア計算上大きなマイナスになるため",
    });
  }

  // 改善優先順位：星の重い指標の弱い順
  const priorities: Finding[] = [];
  const weak = [...ds]
    .filter((d) => d.cur != null)
    .sort((a, b) => b.stars - a.stars || (a.delta ?? 0) - (b.delta ?? 0));
  const actions: Record<string, string> = {
    pvRate: "キャプション末尾のCTA前に「プロフィールのリンクから」等の一言を足し、カルーセル最終枚の誘導文を見直す",
    saveRate: "カルーセルに『保存して見返せる』要素（手順・チェックリスト・料金早見）を1枚入れる",
    followerGain: "プロフィール文の冒頭1行を「誰の何が解決できるか」に変え、投稿→プロフィールの期待を裏切らない",
    reach: "伸びているテーマの投稿比率を上げ、リールを月1〜2本挟んでフォロワー外リーチを取りに行く",
    views: "カバー1枚目のタイトルを数字入り・悩み言葉起点に変え、2枚目以降への遷移率を上げる",
    profileViews: "投稿本文でMIKI個人の体験・視点を必ず1段落入れ、「この人をもっと知りたい」を作る",
  };
  for (const d of weak) {
    if (priorities.length >= 3) break;
    if (d.delta != null && d.delta > 0.1) continue; // 伸びている指標は優先しない
    priorities.push({
      title: `優先${priorities.length + 1}: ${d.label}の底上げ`,
      detail: actions[d.key] ?? "直近の高スコア投稿の構成を踏襲する",
      why: `重要度★${d.stars}で、現状${fmtVal(d.cur, d.isRate)}${d.delta != null ? `（前期間比${fmtDeltaPct(d.delta)}）` : ""}。DM予約に近い指標ほど先に直す方針のため`,
    });
  }

  const summary = buildSummary(grade, score, current, ds);

  return { grade, gradeScore: score, summary, good, improve, causes, successFactors, failureFactors, priorities };
}

function buildSummary(
  grade: WeeklyAnalysis["grade"],
  score: number | null,
  current: PeriodKpi | null,
  ds: KpiDelta[],
): string {
  if (!current || score == null) {
    return "この期間はまだ集計できる完全なデータが揃っていません。週の後半に再確認してください。";
  }
  const up = ds.filter((d) => d.delta != null && d.delta >= 0.1).length;
  const down = ds.filter((d) => d.delta != null && d.delta <= -0.1).length;
  const tone =
    grade === "S" || grade === "A"
      ? "良い流れです。勝ちパターンを次週も再現しましょう"
      : grade === "B"
        ? "平常運転の範囲です。星5指標（誘導率・保存率）に集中すると一段上がります"
        : "立て直しの週です。本数より1本の質（保存される理由・プロフィールに行く理由）を優先してください";
  return `総合スコアは${Math.round(score)}点（${grade}評価）。過去16週の自己分布に対する位置づけで、主要指標のうち${up}個が改善・${down}個が悪化しました。${tone}。`;
}
