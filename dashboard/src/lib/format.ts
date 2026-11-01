/** 表示フォーマット系ユーティリティ */
import type { Usual } from "../types";

export const WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"] as const;

export const fmtInt = (v: number | null | undefined): string =>
  v == null ? "—" : Math.round(v).toLocaleString("ja-JP");

/** 件数。範囲の端（2.5件など）は小数1桁まで出す */
export const fmtNum = (v: number | null | undefined): string => {
  if (v == null) return "—";
  return Number.isInteger(v) ? v.toLocaleString("ja-JP") : (Math.round(v * 10) / 10).toLocaleString("ja-JP");
};

export const fmtPct = (v: number | null | undefined, digits = 1): string =>
  v == null ? "—" : `${(v * 100).toFixed(digits)}%`;

export const fmtValue = (v: number | null | undefined, isRate: boolean): string =>
  isRate ? fmtPct(v) : fmtNum(v);

/** いつもの範囲: 「いつも 304〜551」。人数・件数の範囲は整数に丸める（550.8人とは書かない） */
export const fmtUsual = (u: Usual | null | undefined, isRate: boolean): string => {
  if (!u) return "比べる数が足りません";
  const f = (v: number) => (isRate ? fmtPct(v) : fmtInt(v));
  const lo = f(u.low);
  const hi = f(u.high);
  return lo === hi ? `いつも ${lo}前後` : `いつも ${lo}〜${hi}`;
};

/** 2026-10-19 → 10/19 */
export const fmtDateShort = (iso: string | null | undefined): string => {
  if (!iso) return "—";
  const [, m, d] = iso.slice(0, 10).split("-");
  return `${Number(m)}/${Number(d)}`;
};

/** 週の月曜（2026-10-19）→ 10/19〜10/25 */
export const fmtWeek = (weekStart: string | null | undefined): string => {
  if (!weekStart) return "—";
  const d = new Date(`${weekStart}T00:00:00Z`);
  const end = new Date(d.getTime() + 6 * 86400000);
  return `${d.getUTCMonth() + 1}/${d.getUTCDate()}〜${end.getUTCMonth() + 1}/${end.getUTCDate()}`;
};

/** 投稿の日時（JSTのISO文字列 2026-10-31T01:18+09:00）→ 10/31(土) 1:18 */
export const fmtPostDate = (iso: string): string => {
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (!m) return iso;
  const [, y, mo, d, h, mi] = m;
  const wd = (new Date(Date.UTC(Number(y), Number(mo) - 1, Number(d))).getUTCDay() + 6) % 7;
  return `${Number(mo)}/${Number(d)}(${WEEKDAYS_JA[wd]}) ${Number(h)}:${mi}`;
};

/** シートの日時（2026/11/09 22:00）→ 11/9(月) 22:00 */
export const fmtSlot = (value: string, weekday?: number): string => {
  const m = value.match(/^(\d{4})\/(\d{2})\/(\d{2}) (\d{2}):(\d{2})/);
  if (!m) return value;
  const [, , mo, d, h, mi] = m;
  const wd = weekday != null ? `(${WEEKDAYS_JA[weekday]})` : "";
  return `${Number(mo)}/${Number(d)}${wd} ${Number(h)}:${mi}`;
};

/** 遅れ（分）→ 「予定より3時間18分遅れ」 */
export const fmtDelay = (min: number): string => {
  const h = Math.floor(min / 60);
  const m = min % 60;
  if (h >= 24) return `予定より${Math.round(min / 1440)}日遅れ`;
  return `予定より${h ? `${h}時間` : ""}${m ? `${m}分` : ""}遅れ`;
};
