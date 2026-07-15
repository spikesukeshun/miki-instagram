import type { ScoredPost, ThemeKey, ThemeStats } from "../types";
import type { HeatmapData } from "./analytics";
import { CTA_LIBRARY, FORECAST_MARGIN, TITLE_TIPS, themeDef } from "../config";
import { WEEKDAYS_JA, fmtPct, mean } from "./format";

/**
 * 来週の投稿戦略エンジン。
 * 過去実績（テーマ統計・ヒートマップ・カルーセル枚数×スコア）から
 * 次週の週3投稿プランを組み立てる。
 */

export interface ThemeRecommendation {
  theme: ThemeKey;
  rank: number;
  totalScore: number;
  reason: string;
  expectedReach: [number, number] | null;
  expectedSaveRate: [number, number] | null;
  expectedPvRate: [number, number] | null;
}

export interface SlotPlan {
  slot: number;
  theme: ThemeKey;
  weekdayLabel: string;
  timeLabel: string;
  angle: string;
}

export interface Strategy {
  themeRanking: ThemeRecommendation[];
  bestSlots: { weekday: number; hour: number; avgScore: number; count: number }[];
  slideCount: { recommended: number; label: string; detail: string };
  weekPlan: SlotPlan[];
  ctaIdeas: string[];
  titleIdeas: string[];
  saveRateIdeas: string[];
  pvRateIdeas: string[];
}

const range = (v: number | null): [number, number] | null =>
  v == null ? null : [v * (1 - FORECAST_MARGIN), v * (1 + FORECAST_MARGIN)];

export function buildStrategy(
  themes: ThemeStats[],
  heatmap: HeatmapData,
  insightPosts: ScoredPost[],
): Strategy {
  /* テーマランキング（実績のあるテーマのみ・総合スコア順） */
  const ranked = [...themes]
    .filter((t) => t.theme !== "other" && t.count >= 3)
    .sort((a, b) => b.totalScore - a.totalScore);

  const themeRanking: ThemeRecommendation[] = ranked.map((t, i) => ({
    theme: t.theme,
    rank: i + 1,
    totalScore: t.totalScore,
    reason:
      `${t.count}投稿の平均スコア${Math.round(t.avgScore)}点` +
      (t.recentAvgScore != null ? `、直近8週は${Math.round(t.recentAvgScore)}点` : "") +
      `。保存率${fmtPct(t.avgSaveRate)}・誘導率${fmtPct(t.avgPvRate)}・成功率${fmtPct(t.successRate, 0)}`,
    expectedReach: range(t.avgReach),
    expectedSaveRate: range(t.avgSaveRate),
    expectedPvRate: range(t.avgPvRate),
  }));

  /* おすすめ曜日×時間（実績3件以上のセルの平均スコア上位。小標本の誤誘導を避ける） */
  const bestSlots = heatmap.cells
    .filter((c) => c.count >= 3 && c.avgScore != null)
    .map((c) => ({ weekday: c.weekday, hour: c.hour, avgScore: c.avgScore as number, count: c.count }))
    .sort((a, b) => b.avgScore - a.avgScore)
    .slice(0, 4);

  /* 推奨カルーセル枚数（枚数帯ごとの平均スコア） */
  const buckets = new Map<number, number[]>();
  for (const p of insightPosts) {
    if (p.media_type !== "CAROUSEL_ALBUM") continue;
    const b = Math.min(Math.max(p.slide_count, 5), 9);
    (buckets.get(b) ?? buckets.set(b, []).get(b)!).push(p.score);
  }
  const bucketStats = [...buckets.entries()]
    .map(([n, scores]) => ({ n, avg: mean(scores) ?? 0, count: scores.length }))
    .filter((b) => b.count >= 3)
    .sort((a, b) => b.avg - a.avg);
  const bucketLabel = (n: number) => (n >= 9 ? "9枚以上" : `${n}枚`);
  const bestBucket = bucketStats[0];
  const slideCount = bestBucket
    ? {
        recommended: bestBucket.n,
        label: bucketLabel(bestBucket.n),
        detail:
          `${bucketLabel(bestBucket.n)}構成の平均スコアが${Math.round(bestBucket.avg)}点で最高（${bestBucket.count}投稿）。` +
          bucketStats
            .slice(0, 3)
            .map((b) => `${bucketLabel(b.n)}: ${Math.round(b.avg)}点`)
            .join(" / "),
      }
    : { recommended: 8, label: "8枚", detail: "カルーセル実績が少ないため既定の8枚（本文5〜6枚+固定2枚）を推奨" };

  /* 週3投稿プラン: テーマ上位2つ + 自己語り枠（リーチ・ファン化のため必ず1本） */
  const top1 = themeRanking[0]?.theme ?? "lifestyle";
  const top2 = themeRanking[1]?.theme ?? "reward";
  const third: ThemeKey = [top1, top2].includes("lifestyle")
    ? (themeRanking[2]?.theme ?? "reward")
    : "lifestyle";
  const slots = [...bestSlots];
  const fallbackSlot = { weekday: 2, hour: 21, avgScore: 0, count: 0 };
  const slotAt = (i: number) => slots[i] ?? slots[0] ?? fallbackSlot;
  const angles: Record<ThemeKey, string> = {
    lifestyle: "MIKI個人の体験・想い（保存より誘導狙い。プロフィールへの興味を作る）",
    bridal: "式までの逆算ケア・卒花の変化（数字入りタイトルで保存を狙う）",
    reward: "疲れ・むくみのリセット提案（金曜夜〜週末の「自分ごと」訴求）",
    menu: "料金・時間・流れの早見情報（保存されるQ&A形式。冒頭テンプレ告知は禁止）",
    other: "実績のある切り口に寄せる",
  };
  const weekPlan: SlotPlan[] = [top1, top2, third].map((theme, i) => {
    const s = slotAt(i);
    return {
      slot: i + 1,
      theme,
      weekdayLabel: `${WEEKDAYS_JA[s.weekday]}曜`,
      timeLabel: `${s.hour}時台`,
      angle: angles[theme],
    };
  });

  /* 保存率・誘導率の改善アイデア（実績上位投稿から抽出） */
  const topSave = [...insightPosts]
    .filter((p) => p.saveRate != null)
    .sort((a, b) => (b.saveRate ?? 0) - (a.saveRate ?? 0))
    .slice(0, 2);
  const topPv = [...insightPosts]
    .filter((p) => p.pvRate != null)
    .sort((a, b) => (b.pvRate ?? 0) - (a.pvRate ?? 0))
    .slice(0, 2);

  const saveRateIdeas = [
    ...topSave.map(
      (p) =>
        `保存率${fmtPct(p.saveRate)}の「${p.titleLine}」（${themeDef(p.theme).short}）の型を再利用する`,
    ),
    "「あとで見返す理由」を1枚に集約する（手順・チェックリスト・料金早見表）",
  ];
  const pvRateIdeas = [
    ...topPv.map(
      (p) =>
        `誘導率${fmtPct(p.pvRate)}の「${p.titleLine}」（${themeDef(p.theme).short}）のように、MIKI個人への興味を起点にする`,
    ),
    "最終スライドの一言を「続きはプロフィールから」型に統一する",
  ];

  return {
    themeRanking,
    bestSlots,
    slideCount,
    weekPlan,
    ctaIdeas: CTA_LIBRARY,
    titleIdeas: [
      ...[...insightPosts]
        .sort((a, b) => b.score - a.score)
        .slice(0, 2)
        .map((p) => `高スコア実例: 「${p.titleLine}」（${Math.round(p.score)}点）`),
      ...TITLE_TIPS,
    ],
    saveRateIdeas,
    pvRateIdeas,
  };
}
