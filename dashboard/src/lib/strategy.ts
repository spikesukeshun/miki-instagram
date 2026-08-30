import type { PostingSlot, ScoredPost, ThemeKey, ThemeStats } from "../types";
import { DEFAULT_POSTING_SLOTS, FORECAST_MARGIN } from "../config";
import { WEEKDAYS_JA, fmtPct } from "./format";

/**
 * 来週の投稿戦略エンジン。
 * 投稿枠は実運用の固定枠（check_week_slots.py の SLOTS 由来。既定は 月22:00 / 木21:00 / 金22:00）。
 * その3枠に、過去実績のテーマ統計から選んだテーマを割り当てる。
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
  /** その枠だけの運用上の注意（無いこともある） */
  slotNote?: string;
}

/** 設定上の投稿枠と、実際の投稿がズレたときの検知結果 */
export interface ScheduleDrift {
  expected: string[];
  actual: string[];
}

export interface Strategy {
  themeRanking: ThemeRecommendation[];
  weekPlan: SlotPlan[];
  scheduleDrift: ScheduleDrift | null;
}

const range = (v: number | null): [number, number] | null =>
  v == null ? null : [v * (1 - FORECAST_MARGIN), v * (1 + FORECAST_MARGIN)];

const slotLabel = (s: PostingSlot) => `${WEEKDAYS_JA[s.weekday]}曜${s.hour}時台`;

/** 直近 weeks 週の実投稿を 曜日×時 で数え、多い順に n 枠返す */
function observedSlots(posts: ScoredPost[], weeks: number, n: number): PostingSlot[] {
  const cutoff = new Date(Date.now() + 9 * 3600 * 1000 - weeks * 7 * 86400000);
  const counts = new Map<string, number>();
  for (const p of posts) {
    if (p.date < cutoff) continue;
    const k = `${p.weekday}-${p.hourJst}`;
    counts.set(k, (counts.get(k) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, n)
    .map(([k]) => {
      const [wd, h] = k.split("-").map(Number);
      return { weekday: wd, hour: h };
    });
}

/** 設定枠と実投稿がズレていたら返す（順不同で比較する） */
function detectDrift(slots: PostingSlot[], posts: ScoredPost[]): ScheduleDrift | null {
  const actual = observedSlots(posts, 8, slots.length);
  if (actual.length < slots.length) return null; // 実績が足りない週は判定しない
  const key = (xs: PostingSlot[]) => xs.map(slotLabel).sort().join(",");
  if (key(slots) === key(actual)) return null;
  return {
    expected: [...slots].sort((a, b) => a.weekday - b.weekday).map(slotLabel),
    actual: [...actual].sort((a, b) => a.weekday - b.weekday).map(slotLabel),
  };
}

export function buildStrategy(
  themes: ThemeStats[],
  allPosts: ScoredPost[],
  postingSlots?: PostingSlot[],
): Strategy {
  const slots = postingSlots?.length ? postingSlots : DEFAULT_POSTING_SLOTS;

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

  /* 週3投稿のテーマ: 上位2つ + 自己語り枠（リーチ・ファン化のため必ず1本） */
  const top1 = themeRanking[0]?.theme ?? "lifestyle";
  const top2 = themeRanking[1]?.theme ?? "reward";
  const third: ThemeKey = [top1, top2].includes("lifestyle")
    ? (themeRanking[2]?.theme ?? "reward")
    : "lifestyle";
  const picked: ThemeKey[] = [top1, top2, third];

  const angles: Record<ThemeKey, string> = {
    lifestyle: "MIKI個人の体験・想い（保存より誘導狙い。プロフィールへの興味を作る）",
    bridal: "式までの逆算ケア・卒花の変化（数字入りタイトルで保存を狙う）",
    reward: "疲れ・むくみのリセット提案（金曜夜〜週末の「自分ごと」訴求）",
    menu: "料金・時間・流れの早見情報（保存されるQ&A形式。冒頭テンプレ告知は禁止）",
    other: "実績のある切り口に寄せる",
  };

  /* 枠への割り当て。
     最終枠（既定では金22:00）は木21:00の25時間後で間隔が短いため、
     3テーマのうち平均保存率が最も高いもの＝保存される実用ネタを置いて弱さを補う。 */
  const ordered = [...slots].sort((a, b) => a.weekday - b.weekday || a.hour - b.hour);
  const saveRateOf = (t: ThemeKey) => themes.find((x) => x.theme === t)?.avgSaveRate ?? null;
  const withSaveRate = picked.filter((t) => saveRateOf(t) != null);
  const lastTheme = withSaveRate.length
    ? withSaveRate.reduce((a, b) => ((saveRateOf(b) as number) > (saveRateOf(a) as number) ? b : a))
    : picked[picked.length - 1];
  const restThemes = picked.filter((t) => t !== lastTheme);
  const assigned: ThemeKey[] = [...restThemes, lastTheme];

  const weekPlan: SlotPlan[] = ordered.map((s, i) => ({
    slot: i + 1,
    theme: assigned[i] ?? picked[i] ?? "lifestyle",
    weekdayLabel: `${WEEKDAYS_JA[s.weekday]}曜`,
    timeLabel: `${s.hour}時台`,
    angle: angles[assigned[i] ?? picked[i] ?? "lifestyle"],
    slotNote:
      i === ordered.length - 1 && ordered.length > 1
        ? `前の枠（${slotLabel(ordered[i - 1])}）の直後。保存される実用ネタで間隔の弱さを補う`
        : undefined,
  }));

  return { themeRanking, weekPlan, scheduleDrift: detectDrift(slots, allPosts) };
}
