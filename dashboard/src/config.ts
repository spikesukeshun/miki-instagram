import type { ThemeKey } from "./types";

/**
 * 画面の設定（テーマの表示名と色）。
 * 判定の数え方・指標や施策の名前は dashboard/review_inputs.py と review_post.py が正で、
 * スナップショットの derived.labels で渡ってくる（ここに同じ一覧を書かない）。
 */

/** テーマ定義（表示名・色スロット）。配列順がカテゴリカル色の固定スロット順（CVD検証済みの並び） */
export const THEMES: { key: ThemeKey; label: string; short: string; cssVar: string }[] = [
  { key: "bridal", label: "ブライダル", short: "ブライダル", cssVar: "--s-bridal" },
  { key: "menu", label: "メニュー・サービス", short: "メニュー", cssVar: "--s-menu" },
  { key: "reward", label: "ご褒美エステ", short: "ご褒美", cssVar: "--s-reward" },
  { key: "lifestyle", label: "ライフスタイル・自己語り", short: "自己語り", cssVar: "--s-lifestyle" },
  { key: "other", label: "その他", short: "その他", cssVar: "--s-other" },
];

export const themeDef = (key: ThemeKey | string | null | undefined) =>
  THEMES.find((t) => t.key === key) ?? THEMES[THEMES.length - 1];

/** 予定より遅れたと見なす分数（これを超えたら投稿一覧に遅れを出す） */
export const DELAY_NOTICE_MIN = 60;
