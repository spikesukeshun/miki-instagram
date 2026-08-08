import type { ThemeKey } from "./types";

/**
 * ダッシュボード全体の設定。
 * スコア重み・閾値・テーマ定義・ファネル推定係数はすべてここに集約する
 * （コンポーネント側にマジックナンバーを書かない）。
 */

/** KPI重要度（ユーザー指定の星数）
 *  方針: DMにつながらないリーチは価値が低く、
 *  プロフィールに来る人が多い投稿ほど価値が高い。
 *  DM率はAPI非提供のためスコア構成からは除外（ファネルで手入力）。 */
export const METRIC_WEIGHTS = [
  { key: "pvRate", label: "プロフィール誘導率", stars: 5, isRate: true },
  { key: "saveRate", label: "保存率", stars: 5, isRate: true },
  { key: "follows", label: "フォロワー増加", stars: 5, isRate: false },
  { key: "reach", label: "リーチ", stars: 4, isRate: false },
  { key: "views", label: "インプレッション", stars: 4, isRate: false },
  { key: "comments", label: "コメント", stars: 3, isRate: false },
  { key: "likes", label: "いいね", stars: 3, isRate: false },
  { key: "shares", label: "シェア", stars: 2, isRate: false },
] as const;

export type MetricKey = (typeof METRIC_WEIGHTS)[number]["key"];

/** 投稿を「成功」とみなすスコア閾値（自アカウント内相対評価） */
export const SUCCESS_SCORE = 60;

/** テーマ定義（表示名・チャート色スロット）
 *  配列順がカテゴリカル色の固定スロット順（CVD検証済みの並び） */
export const THEMES: { key: ThemeKey; label: string; short: string; cssVar: string }[] = [
  { key: "bridal", label: "ブライダル", short: "ブライダル", cssVar: "--s-bridal" },
  { key: "menu", label: "メニュー・サービス", short: "メニュー", cssVar: "--s-menu" },
  { key: "reward", label: "ご褒美エステ", short: "ご褒美", cssVar: "--s-reward" },
  { key: "lifestyle", label: "ライフスタイル・自己語り", short: "自己語り", cssVar: "--s-lifestyle" },
  { key: "other", label: "その他", short: "その他", cssVar: "--s-other" },
];

export const themeDef = (key: ThemeKey) =>
  THEMES.find((t) => t.key === key) ?? THEMES[THEMES.length - 1];

/** 週次推移などで参照する分析ウィンドウ */
export const ANALYSIS = {
  /** 推移グラフ・週次比較に使う週数（アカウント週次データの範囲） */
  trendWeeks: 16,
  /** テーマ「直近」判定のウィンドウ（週） */
  recentWeeks: 8,
  /** スコアの参照分布に使う最大投稿数（新しい順） */
  referencePool: 140,
  /** 改善レポートに表示する投稿数 */
  reportPosts: 12,
  /** ランキングに表示する投稿数 */
  rankingPosts: 10,
} as const;

/** ファネルのDM・予約が未入力のときに使う推定係数
 *  （プロフィール閲覧→DM、DM→予約の想定転換率。実測が貯まったら調整） */
export const FUNNEL_ESTIMATES = {
  dmPerProfileView: 0.05,
  bookingPerDm: 0.4,
} as const;

/** 手入力値（DM・予約）の localStorage キー */
export const STORAGE_KEY = "miki-ig-dashboard-manual-v1";

/** 想定値レンジの幅（trailing平均 ×(1±この値)） */
export const FORECAST_MARGIN = 0.25;

/** 戦略提案で使うCTA・タイトル改善のテンプレート（実績パターン準拠） */
export const CTA_LIBRARY = [
  "「MIKI指名 初回限定20%OFF（VIPコースのみ）」を末尾に明記し、その直前に予約タイミングの一言（例：今週のご褒美に）を添える",
  "「DMからご相談」の前に、相談のハードルを下げる一文（例：質問だけでも大丈夫です）を入れる",
  "キャプション中盤に「保存しておくと便利です」の一文を入れ、保存からの再訪→DMの導線を作る",
];

export const TITLE_TIPS = [
  "数字を入れる（例：式まで3ヶ月/週1回のご褒美/40代の肌）と保存率が上がりやすい",
  "読者の悩みの言葉で始める（例：「なんだか疲れが取れない」）と自分ごと化されやすい",
  "カバータイトルは13文字前後×2行まで。助詞止めを避け文節で改行する",
];
