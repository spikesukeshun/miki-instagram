/**
 * dashboard_data.json のうち画面が使う部分の型。
 * 数字はすべて dashboard/review_inputs.py の derive() が計算する（画面は表示するだけ）。
 * 週次タスクの Claude も同じ数字を `review_inputs.py digest` で読むので、ここで計算し直さないこと。
 */

export type ThemeKey = "lifestyle" | "menu" | "bridal" | "reward" | "other";

/** いつもの範囲（直近の真ん中半分）との比較 */
export type Verdict = "high" | "usual" | "low" | null;

export interface Usual {
  low: number;
  median: number;
  high: number;
  n: number;
}

export interface Labels {
  levers: Record<string, string>;
  metrics: Record<string, string>;
  /** trial.metric → 投稿の数字のキー（saved → saved_rate など） */
  metric_fields: Record<string, MetricField>;
  decisions: Record<string, string>;
  verdicts: Record<string, string>;
  standard_sources: Record<string, string>;
}

/* ───────── 1. 先週のまとめ ───────── */

export interface WeekRow {
  week_start: string;
  partial: boolean;
  posts: number;
  reach: number | null;
  profile_views: number | null;
  pv_rate: number | null;
  link_taps: number | null;
  saved: number | null;
  saved_rate: number | null;
  lp_arrivals: number | null;
  lp_engaged: number | null;
  lp_cta_dm: number | null;
  lp_cta_hotpepper: number | null;
}

export interface Tile {
  key: "reach" | "saved" | "profile_views" | "lp";
  label: string;
  is_rate: boolean;
  value: number | null;
  /** 率のタイル（保存・プロフィール）で並べる件数 */
  count: number | null;
  usual: Usual | null;
  verdict: Verdict;
  spark: { week_start: string; value: number | null }[];
}

export interface Summary {
  week_start: string;
  tiles: Tile[];
  current_week: WeekRow | null;
  followers: number | null;
  followers_gain: number | null;
  followers_days: number;
}

/* ───────── 投稿・試すこと・修正 ───────── */

export interface Trial {
  tag?: string;
  lever: string;
  what?: string;
  metric?: string;
  why?: string;
  where?: string;
}

export interface Edits {
  count: number;
  changes: string[];
  base_origin: string | null;
  last_at: string | null;
  /** app = 投稿後にキャプションが書き換えられた / sheet = シートが校閲を通った版と違う */
  direct: "app" | "sheet" | null;
}

export interface PostMetrics {
  reach: number | null;
  saved: number | null;
  saved_rate: number | null;
  profile_visits: number | null;
  pv_rate: number | null;
  follows: number | null;
}

export type MetricField = keyof PostMetrics;

export interface Post {
  media_id: string;
  date: string;
  week_start: string;
  weekday: number;
  media_type: "CAROUSEL_ALBUM" | "IMAGE" | "VIDEO";
  permalink: string;
  theme: ThemeKey;
  title: string;
  age_days: number;
  mature: boolean;
  metrics: PostMetrics;
  usual: Partial<Record<MetricField, Usual | null>>;
  vs: Partial<Record<MetricField, Verdict>>;
  slug: string | null;
  scheduled_at: string | null;
  delay_min: number | null;
  menu: string | null;
  trial: Trial | null;
  cover_title: string;
  edits: Edits | null;
}

export interface Upcoming {
  slug: string;
  post_datetime: string;
  weekday: number;
  status: string;
  menu: string | null;
  preview_url: string | null;
  /** 校閲を通っているはずなのに前回版が無い（週次タスクが途中で止まった名残） */
  needs_review: boolean;
  trial: Trial | null;
  cover_title: string;
  edits: Edits | null;
}

export interface TrialStat {
  tag: string;
  lever: string;
  metric: string;
  what: string;
  count: number;
  judged: number;
  high: number;
  usual: number;
  low: number;
  median_with: number | null;
  median_without: number | null;
  posts: string[];
  last_posted: string;
  decision: "standard" | "again" | "stop" | null;
  again: number;
}

export interface EditStats {
  weeks: number;
  slots: number;
  known: number;
  edited: number;
  top_changes: { label: string; count: number }[];
}

/* ───────── 2. 振り返り ───────── */

export interface Review {
  written_on: string;
  summary: string;
  verdicts?: { tag: string; decision: string; evidence: string; note?: string }[];
  standards?: {
    tag: string;
    what: string;
    since?: string;
    source?: string;
    based_on?: string[];
    explicit?: boolean;
  }[];
  stopped?: { tag: string; what?: string; since?: string }[];
  next?: { tag: string; lever: string; what: string; metric: string; why: string }[];
  _draft?: boolean;
}

export interface ReviewView {
  latest: Review | null;
  history: { written_on: string; summary: string }[];
  decisions: Record<string, { again: number; last: string | null }>;
}

/* ───────── 4. LP ───────── */

export interface LpFunnel {
  profile_views: number | null;
  link_taps: number | null;
  arrivals: number | null;
  engaged: number | null;
  cta_dm: number | null;
  cta_hotpepper: number | null;
  bounced: number | null;
}

export interface LpDerived {
  available: boolean;
  reason?: string;
  period_weeks?: number;
  period_start?: string | null;
  since?: string;
  funnel?: LpFunnel;
  funnel_all?: LpFunnel;
  trend?: {
    week_start: string;
    partial: boolean;
    link_taps: number | null;
    arrivals: number | null;
    engaged: number | null;
    cta: number;
  }[];
  avg_engagement_sec?: number | null;
  devices?: { device: string; sessions: number }[] | null;
  visitors?: { new: number; returning: number } | null;
  courses?: { course: string; cta_dm: number; cta_hotpepper: number }[] | null;
  courses_note?: string | null;
  sources?: { source_medium: string; sessions: number; engaged_sessions: number }[];
  sources_period?: "recent" | "all";
  search?: { clicks: number; impressions: number; position: number } | null;
}

/* ───────── 全体 ───────── */

export interface Derived {
  generated_at: string;
  mature_days: number;
  usual_posts: number;
  usual_weeks: number;
  summary: Summary | null;
  judged_week: string | null;
  judged: Post[];
  posts: Post[];
  upcoming: Upcoming[];
  trial_stats: TrialStat[];
  edits: EditStats;
  lp: LpDerived;
  review: ReviewView;
  sheet_error: string | null;
  labels: Labels;
}

export interface DashboardData {
  fetched_at: string;
  account: {
    username: string;
    followers_count: number;
    media_count: number;
  };
  /** 古いスナップショット（2026-11 より前の形式）には無い */
  derived?: Derived;
}
