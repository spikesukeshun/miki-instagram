import type {
  AccountWeekly,
  DashboardData,
  MediaInsights,
  RawPost,
  ScoredPost,
  ScorePart,
  ThemeStats,
  WeekAgg,
} from "../types";
import { ANALYSIS, METRIC_WEIGHTS, SUCCESS_SCORE, THEMES } from "../config";
import { mean, sum } from "./format";

/* ───────── 日付（JST） ───────── */

/** timestamp(+0000) を JST の壁時計に合わせた Date にする（getUTC* で読む） */
export function toJstClock(ts: string): Date {
  return new Date(new Date(ts).getTime() + 9 * 3600 * 1000);
}

/** JST壁時計Dateから「その週の月曜（YYYY-MM-DD）」 */
export function weekStartKey(jst: Date): string {
  const d = new Date(jst.getTime());
  const dow = (d.getUTCDay() + 6) % 7; // 0=月
  d.setUTCDate(d.getUTCDate() - dow);
  return d.toISOString().slice(0, 10);
}

const addDays = (iso: string, days: number): string => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
};

/* ───────── パーセンタイル ───────── */

/** 参照分布内での位置（0〜1、midrank方式） */
export function percentile(sortedPool: number[], v: number): number {
  if (!sortedPool.length) return 0.5;
  let below = 0;
  let equal = 0;
  for (const x of sortedPool) {
    if (x < v) below++;
    else if (x === v) equal++;
  }
  return (below + equal / 2) / sortedPool.length;
}

const sorted = (xs: number[]) => [...xs].sort((a, b) => a - b);

/* ───────── メトリクス抽出 ───────── */

function rateOf(ins: MediaInsights | null, num: keyof MediaInsights): number | null {
  if (!ins) return null;
  const n = ins[num];
  const reach = ins.reach;
  if (n == null || reach == null || reach <= 0) return null;
  return n / reach;
}

function metricValue(p: RawPost, key: string): number | null {
  const ins = p.insights;
  switch (key) {
    case "pvRate":
      return rateOf(ins, "profile_visits");
    case "saveRate":
      return rateOf(ins, "saved");
    case "follows":
      return ins?.follows ?? null;
    case "reach":
      return ins?.reach ?? null;
    case "views":
      return ins?.views ?? null;
    case "comments":
      return ins?.comments ?? p.comments ?? null;
    case "likes":
      return ins?.likes ?? p.likes ?? null;
    case "shares":
      return ins?.shares ?? null;
    default:
      return null;
  }
}

/* ───────── 投稿スコアリング ───────── */

export interface Analyzed {
  posts: ScoredPost[]; // 全投稿（新しい順）
  insightPosts: ScoredPost[]; // インサイトあり
  weeks: WeekAgg[]; // アカウント週次 + 投稿集計（古い→新しい）
  themes: ThemeStats[];
  heatmap: HeatmapData;
  currentWeekStart: string;
}

export interface HeatmapCell {
  weekday: number;
  hour: number;
  count: number;
  avgScore: number | null;
}

export interface HeatmapData {
  cells: HeatmapCell[];
  hours: number[]; // 表示対象の時間帯（投稿が存在する時間のみ）
  maxScore: number;
}

export function analyze(data: DashboardData): Analyzed {
  const rawPosts = data.posts;
  const insightRaw = rawPosts.filter((p) => p.insights);

  // 参照分布（インサイトあり投稿・新しい順で最大 referencePool 件）
  const refPosts = insightRaw.slice(0, ANALYSIS.referencePool);
  const pools = new Map<string, number[]>();
  for (const m of METRIC_WEIGHTS) {
    const vals = refPosts
      .map((p) => metricValue(p, m.key))
      .filter((v): v is number => v != null);
    pools.set(m.key, sorted(vals));
  }
  // 推定スコア用（インサイトなし投稿向け）: 全期間のいいね・コメント分布
  const likesPool = sorted(rawPosts.map((p) => p.likes ?? 0));
  const commentsPool = sorted(rawPosts.map((p) => p.comments ?? 0));

  const scorePost = (p: RawPost): { score: number; parts: ScorePart[]; estimated: boolean } => {
    if (p.insights) {
      const parts: ScorePart[] = METRIC_WEIGHTS.map((m) => {
        const v = metricValue(p, m.key);
        const pool = pools.get(m.key) ?? [];
        return {
          key: m.key,
          label: m.label,
          stars: m.stars,
          value: v,
          percentile: v == null || pool.length < 5 ? null : percentile(pool, v),
          isRate: m.isRate,
        };
      });
      const avail = parts.filter((x) => x.percentile != null);
      const wsum = sum(avail.map((x) => x.stars));
      const score = wsum
        ? (sum(avail.map((x) => x.stars * (x.percentile as number))) / wsum) * 100
        : 0;
      return { score, parts, estimated: false };
    }
    // インサイトが取れない古い投稿 → いいね・コメントのみで推定
    const pl = percentile(likesPool, p.likes ?? 0);
    const pc = percentile(commentsPool, p.comments ?? 0);
    return {
      score: ((pl + pc) / 2) * 100,
      parts: [],
      estimated: true,
    };
  };

  const posts: ScoredPost[] = rawPosts.map((p) => {
    const jst = toJstClock(p.timestamp);
    const { score, parts, estimated } = scorePost(p);
    return {
      ...p,
      date: jst,
      weekStart: weekStartKey(jst),
      weekday: (jst.getUTCDay() + 6) % 7,
      hourJst: jst.getUTCHours(),
      saveRate: rateOf(p.insights, "saved"),
      pvRate: rateOf(p.insights, "profile_visits"),
      followRate: rateOf(p.insights, "follows"),
      score,
      estimated,
      parts,
      titleLine: firstSentence(p.caption_head),
    };
  });

  const insightPosts = posts.filter((p) => p.insights);
  const nowJst = new Date(Date.now() + 9 * 3600 * 1000);
  const currentWeekStart = weekStartKey(nowJst);

  const weeks = buildWeeks(data, posts, currentWeekStart);
  const themes = buildThemes(insightPosts, currentWeekStart);
  const heatmap = buildHeatmap(posts);

  return { posts, insightPosts, weeks, themes, heatmap, currentWeekStart };
}

const GREETING = /^(miki|MIKI|ミキ|美喜)(です|だよ)?[。｡\s]*$|閲覧ありがとう|ご覧いただき/;

/** 意味のある文字（かな・漢字・英数）の数 */
const meaningfulChars = (s: string) =>
  (s.match(/[ぁ-んァ-ヶ一-龠々a-zA-Z0-9]/g) ?? []).length;

function firstSentence(caption: string): string {
  // 「mikiです。」等の挨拶・メンション・装飾行はスキップして、意味のある最初の一文を取る
  const segments = caption
    .replace(/@[\w.]+/g, " ")
    .split(/[。｡\n]/)
    .map((s) => s.replace(/^[\s⭐️☆★~〜・:*.#]+|[\s⭐️☆★~〜・:*.#]+$/g, "").trim())
    .filter((s) => meaningfulChars(s) >= 6);
  const head = segments.find((s) => s.length >= 8 && !GREETING.test(s)) ?? segments[0] ?? "";
  return head.length > 42 ? `${head.slice(0, 42)}…` : head || "(キャプションなし)";
}

/* ───────── 週次集計 ───────── */

function buildWeeks(data: DashboardData, posts: ScoredPost[], currentWeekStart: string): WeekAgg[] {
  const byWeekPosts = new Map<string, ScoredPost[]>();
  for (const p of posts) {
    (byWeekPosts.get(p.weekStart) ?? byWeekPosts.set(p.weekStart, []).get(p.weekStart)!).push(p);
  }

  // 日次フォロワー純増 → 週次へ
  const gainByWeek = new Map<string, number>();
  const daysByWeek = new Map<string, number>();
  for (const d of data.account_daily) {
    if (d.follower_count == null) continue;
    const wk = weekStartKey(new Date(`${d.date}T00:00:00Z`));
    gainByWeek.set(wk, (gainByWeek.get(wk) ?? 0) + d.follower_count);
    daysByWeek.set(wk, (daysByWeek.get(wk) ?? 0) + 1);
  }

  return data.account_weekly
    .filter((w): w is AccountWeekly => !w.error)
    .map((w) => {
      const wp = (byWeekPosts.get(w.week_start) ?? []).filter((p) => p.insights);
      const saveRates = wp.map((p) => p.saveRate).filter((v): v is number => v != null);
      const reach = w.reach ?? null;
      const pv = w.profile_views ?? null;
      const days = daysByWeek.get(w.week_start) ?? 0;
      return {
        weekStart: w.week_start,
        label: `${Number(w.week_start.slice(5, 7))}/${Number(w.week_start.slice(8, 10))}週`,
        postCount: (byWeekPosts.get(w.week_start) ?? []).length,
        avgScore: mean(wp.map((p) => p.score)),
        reach,
        views: w.views ?? null,
        profileViews: pv,
        pvRate: reach && pv != null ? pv / reach : null,
        saveRate: mean(saveRates),
        websiteClicks: w.website_clicks ?? null,
        // 7日分揃っている週だけフォロワー純増を確定値とする（30日制限のため）
        followerGain: days >= 7 || (w.week_start === currentWeekStart && days > 0)
          ? gainByWeek.get(w.week_start) ?? 0
          : null,
        partial: w.partial || w.week_start === currentWeekStart,
      };
    })
    .sort((a, b) => a.weekStart.localeCompare(b.weekStart));
}

/* ───────── テーマ集計 ───────── */

function buildThemes(insightPosts: ScoredPost[], currentWeekStart: string): ThemeStats[] {
  const recentCut = addDays(currentWeekStart, -7 * ANALYSIS.recentWeeks);
  const stats: ThemeStats[] = [];
  for (const t of THEMES) {
    const members = insightPosts.filter((p) => p.theme === t.key);
    if (!members.length) continue;
    const recent = members.filter((p) => p.weekStart >= recentCut);
    const follows = members
      .map((p) => p.insights?.follows)
      .filter((v): v is number => v != null);
    const avgScore = mean(members.map((p) => p.score)) ?? 0;
    const recentAvgScore = recent.length ? mean(recent.map((p) => p.score)) : null;
    stats.push({
      theme: t.key,
      count: members.length,
      avgReach: mean(members.map((p) => p.insights?.reach).filter((v): v is number => v != null)),
      avgSaveRate: mean(members.map((p) => p.saveRate).filter((v): v is number => v != null)),
      avgPvRate: mean(members.map((p) => p.pvRate).filter((v): v is number => v != null)),
      followsPerPost: follows.length ? sum(follows) / follows.length : null,
      successRate: members.filter((p) => p.score >= SUCCESS_SCORE).length / members.length,
      avgScore,
      recentAvgScore,
      // 総合 = 全期間6割 + 直近8週4割（直近データが無ければ全期間）
      totalScore: 0.6 * avgScore + 0.4 * (recentAvgScore ?? avgScore),
    });
  }
  return stats;
}

/* ───────── ヒートマップ ───────── */

function buildHeatmap(posts: ScoredPost[]): HeatmapData {
  const map = new Map<string, { total: number; count: number }>();
  const hourSet = new Set<number>();
  for (const p of posts) {
    hourSet.add(p.hourJst);
    const k = `${p.weekday}-${p.hourJst}`;
    const cur = map.get(k) ?? { total: 0, count: 0 };
    cur.total += p.score;
    cur.count += 1;
    map.set(k, cur);
  }
  const hours = [...hourSet].sort((a, b) => a - b);
  const cells: HeatmapCell[] = [];
  let maxScore = 0;
  for (let wd = 0; wd < 7; wd++) {
    for (const h of hours) {
      const e = map.get(`${wd}-${h}`);
      const avg = e ? e.total / e.count : null;
      if (avg != null) maxScore = Math.max(maxScore, avg);
      cells.push({ weekday: wd, hour: h, count: e?.count ?? 0, avgScore: avg });
    }
  }
  return { cells, hours, maxScore };
}

/* ───────── 期間集計（KPIグリッド・ファネル用） ───────── */

export type RangeKey = "this" | "last" | "4w" | "12w";

export const RANGES: { key: RangeKey; label: string; weeks: number; offset: number }[] = [
  { key: "this", label: "今週", weeks: 1, offset: 0 },
  { key: "last", label: "先週", weeks: 1, offset: 1 },
  { key: "4w", label: "過去4週", weeks: 4, offset: 0 },
  { key: "12w", label: "過去12週", weeks: 12, offset: 0 },
];

export interface PeriodKpi {
  weekStarts: string[];
  postCount: number;
  reach: number | null;
  views: number | null;
  profileViews: number | null;
  pvRate: number | null;
  saveRate: number | null;
  followerGain: number | null;
  websiteClicks: number | null;
  avgScore: number | null;
  /** 週次総合スコア（トレーリング分布に対する百分位・星重み） */
  compositeScore: number | null;
  partial: boolean;
}

function aggregate(weeks: WeekAgg[], picked: WeekAgg[]): PeriodKpi | null {
  if (!picked.length) return null;
  const sumOf = (f: (w: WeekAgg) => number | null) => {
    const vals = picked.map(f).filter((v): v is number => v != null);
    return vals.length ? sum(vals) : null;
  };
  const reach = sumOf((w) => w.reach);
  const pv = sumOf((w) => w.profileViews);
  const gains = picked.map((w) => w.followerGain);
  const kpi: PeriodKpi = {
    weekStarts: picked.map((w) => w.weekStart),
    postCount: sum(picked.map((w) => w.postCount)),
    reach,
    views: sumOf((w) => w.views),
    profileViews: pv,
    pvRate: reach && pv != null ? pv / reach : null,
    saveRate: mean(picked.map((w) => w.saveRate).filter((v): v is number => v != null)),
    followerGain: gains.every((g) => g == null) ? null : sum(gains.filter((g): g is number => g != null)),
    websiteClicks: sumOf((w) => w.websiteClicks),
    avgScore: mean(picked.map((w) => w.avgScore).filter((v): v is number => v != null)),
    compositeScore: null,
    partial: picked.some((w) => w.partial),
  };
  kpi.compositeScore = compositeWeekScore(weeks, kpi);
  return kpi;
}

/** 対象期間のKPIを、全週の分布に対する百分位×星重みで0〜100に合成 */
function compositeWeekScore(weeks: WeekAgg[], kpi: PeriodKpi): number | null {
  const full = weeks.filter((w) => !w.partial);
  if (full.length < 4) return null;
  const n = kpi.weekStarts.length;
  const per = (f: (w: WeekAgg) => number | null, v: number | null, scalePerWeek: boolean) => {
    if (v == null) return null;
    const pool = full.map(f).filter((x): x is number => x != null);
    if (pool.length < 4) return null;
    return percentile(sorted(pool), scalePerWeek ? v / n : v);
  };
  const parts: { stars: number; p: number | null }[] = [
    { stars: 5, p: per((w) => w.pvRate, kpi.pvRate, false) },
    { stars: 5, p: per((w) => w.saveRate, kpi.saveRate, false) },
    { stars: 5, p: per((w) => w.followerGain, kpi.followerGain, true) },
    { stars: 4, p: per((w) => w.reach, kpi.reach, true) },
    { stars: 4, p: per((w) => w.views, kpi.views, true) },
  ];
  const avail = parts.filter((x) => x.p != null);
  if (!avail.length) return null;
  const wsum = sum(avail.map((x) => x.stars));
  return (sum(avail.map((x) => x.stars * (x.p as number))) / wsum) * 100;
}

export interface PeriodComparison {
  current: PeriodKpi | null;
  previous: PeriodKpi | null;
  /** 前月比較用（同じ長さでさらに1期間前） */
  prevMonth: PeriodKpi | null;
}

export function periodKpis(weeks: WeekAgg[], range: RangeKey, currentWeekStart: string): PeriodComparison {
  const def = RANGES.find((r) => r.key === range) ?? RANGES[0];
  const ordered = [...weeks].sort((a, b) => b.weekStart.localeCompare(a.weekStart));
  // "今週"以外は部分週（今週）を除いた完全な週で集計する
  const base = def.key === "this" ? ordered : ordered.filter((w) => w.weekStart !== currentWeekStart);
  const current = aggregate(weeks, base.slice(0, def.weeks));
  const previous = aggregate(weeks, base.slice(def.weeks, def.weeks * 2));
  const prevMonth = aggregate(weeks, base.slice(4, 4 + def.weeks));
  return { current, previous, prevMonth };
}
