/** dashboard_data.json のスキーマ（fetch_dashboard_data.py の出力） */

export interface MediaInsights {
  reach?: number;
  views?: number;
  saved?: number;
  shares?: number;
  likes?: number;
  comments?: number;
  total_interactions?: number;
  profile_visits?: number;
  follows?: number;
}

export type ThemeKey = "lifestyle" | "menu" | "bridal" | "reward" | "other";

export interface RawPost {
  media_id: string;
  timestamp: string;
  media_type: "CAROUSEL_ALBUM" | "IMAGE" | "VIDEO";
  permalink: string;
  caption_head: string;
  slide_count: number;
  likes: number;
  comments: number;
  theme: ThemeKey;
  theme_source: "classified" | "heuristic" | "override";
  insights: MediaInsights | null;
}

export interface AccountDaily {
  date: string;
  reach?: number;
  follower_count?: number;
}

export interface AccountWeekly {
  week_start: string;
  partial: boolean;
  error?: string;
  profile_views?: number;
  views?: number;
  accounts_engaged?: number;
  total_interactions?: number;
  website_clicks?: number;
  reach?: number;
}

export interface DashboardData {
  fetched_at: string;
  account: {
    username: string;
    followers_count: number;
    media_count: number;
  };
  account_daily: AccountDaily[];
  account_weekly: AccountWeekly[];
  posts: RawPost[];
  /** 実運用の投稿枠（0=月）。fetch_dashboard_data.py が check_week_slots.SLOTS から書き出す。
   *  古いスナップショットには無いので optional。 */
  posting_slots?: PostingSlot[];
  /** コンバージョンLPのGA4実測。fetch_ga4_data.py 由来。
   *  サービスアカウント未設定なら null（→ dashboard/GA4_SETUP.md）。 */
  lp?: LpData | null;
  claude_comment: string | null;
}

/** 曜日（0=月）と時（JST）。実運用の投稿枠1つぶん。 */
export interface PostingSlot {
  weekday: number;
  hour: number;
}

/* ───────── コンバージョンLP（GA4 / Search Console） ───────── */

export interface LpData {
  fetched_at: string;
  property_id?: string;
  since?: string;
  weeks?: LpWeek[];
  sources?: LpSource[];
  search_console?: LpSearchConsole;
  /** 取得に失敗したときだけ入る（画面は素直にこの文言を出す） */
  error?: string;
}

/** 月曜始まりJSTの週サマリ。account_weekly と同じ週の切り方に揃えてある。 */
export interface LpWeek {
  week_start: string;
  partial: boolean;
  sessions: number;
  engaged_sessions: number;
  avg_engagement_sec: number;
  /** Instagram経由だけを抜いた数。ファネルはこちらを使う（Directには自動化アクセスが混ざるため） */
  instagram_sessions: number;
  instagram_engaged_sessions: number;
  cta_dm: number;
  cta_hotpepper: number;
  generate_lead: number;
  instagram_cta_dm: number;
  instagram_cta_hotpepper: number;
  instagram_generate_lead: number;
}

/** 参照元/メディア別の合計。実ユーザーと自動化アクセスを見分けるための行。 */
export interface LpSource {
  source_medium: string;
  sessions: number;
  engaged_sessions: number;
  avg_engagement_sec: number;
  cta_dm: number;
  cta_hotpepper: number;
  generate_lead: number;
}

export interface LpSearchConsole {
  clicks: number;
  impressions: number;
  ctr: number;
  position: number;
  /** 表示回数が少ないとGoogleが匿名化して返さない。空配列は異常ではない。 */
  queries: { query: string; clicks: number; impressions: number; position: number }[];
}

/* ───────── 分析後の派生型 ───────── */

export interface ScorePart {
  key: string;
  label: string;
  stars: number;
  /** 0〜1 パーセンタイル（参照分布内での位置） */
  percentile: number | null;
  /** 表示用の実測値 */
  value: number | null;
  /** 率系メトリクスか */
  isRate: boolean;
}

export interface ScoredPost extends RawPost {
  date: Date;
  weekStart: string; // YYYY-MM-DD（JST月曜）
  weekday: number; // 0=月 … 6=日
  hourJst: number;
  saveRate: number | null;
  pvRate: number | null;
  followRate: number | null;
  /** 0〜100 */
  score: number;
  /** インサイト欠損（古い投稿）による推定スコアか */
  estimated: boolean;
  parts: ScorePart[];
  titleLine: string;
}

export interface ThemeStats {
  theme: ThemeKey;
  count: number;
  avgReach: number | null;
  avgSaveRate: number | null;
  avgPvRate: number | null;
  followsPerPost: number | null;
  successRate: number; // score >= threshold の割合
  avgScore: number;
  recentAvgScore: number | null; // 直近8週
  totalScore: number; // 総合順位用（星重み合成）
}

export interface WeekAgg {
  weekStart: string;
  label: string;
  postCount: number;
  avgScore: number | null;
  reach: number | null; // アカウント週次
  views: number | null;
  profileViews: number | null;
  pvRate: number | null; // profile_views / reach
  saveRate: number | null; // 投稿ベース
  websiteClicks: number | null;
  followerGain: number | null; // 日次follower_countの合計（直近30日内のみ）
  partial: boolean;
}
