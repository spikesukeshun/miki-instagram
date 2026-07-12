/** 表示フォーマット系ユーティリティ */

export const fmtInt = (v: number | null | undefined): string =>
  v == null ? "—" : Math.round(v).toLocaleString("ja-JP");

export const fmtPct = (v: number | null | undefined, digits = 1): string =>
  v == null ? "—" : `${(v * 100).toFixed(digits)}%`;

export const fmtSigned = (v: number | null | undefined): string => {
  if (v == null) return "—";
  const r = Math.round(v);
  return r > 0 ? `+${r.toLocaleString("ja-JP")}` : r.toLocaleString("ja-JP");
};

/** 前週比などの変化率: 0.12 → "+12%" */
export const fmtDeltaPct = (v: number | null | undefined): string => {
  if (v == null || !isFinite(v)) return "—";
  const pct = Math.round(v * 100);
  return pct > 0 ? `+${pct}%` : `${pct}%`;
};

export const WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"] as const;

export const fmtDateShort = (iso: string): string => {
  const [, m, d] = iso.split("-");
  return `${Number(m)}/${Number(d)}`;
};

export const fmtDateJa = (d: Date): string =>
  `${d.getMonth() + 1}月${d.getDate()}日(${WEEKDAYS_JA[(d.getDay() + 6) % 7]})`;

/** 変化率を計算（基準0のときはnull） */
export const ratio = (now: number | null | undefined, prev: number | null | undefined): number | null => {
  if (now == null || prev == null || prev === 0) return null;
  return now / prev - 1;
};

export const mean = (xs: number[]): number | null =>
  xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;

export const sum = (xs: number[]): number => xs.reduce((a, b) => a + b, 0);

export const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
