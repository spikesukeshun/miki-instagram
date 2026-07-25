import { useCallback, useState } from "react";
import { STORAGE_KEY } from "../config";

/**
 * DM問い合わせ数・予約数の手入力値。
 * APIで取得できないため localStorage（端末ごと）に週キー（YYYY-MM-DD=週の月曜）で保存する。
 */

export interface ManualWeekInput {
  dm: number | null;
  booking: number | null;
}

type Store = Record<string, ManualWeekInput>;

function load(): Store {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Store) : {};
  } catch {
    return {};
  }
}

export function useManualStore() {
  const [store, setStore] = useState<Store>(load);

  const updateWeek = useCallback((week: string, patch: Partial<ManualWeekInput>) => {
    setStore((prev) => {
      const next: Store = {
        ...prev,
        [week]: { ...(prev[week] ?? { dm: null, booking: null }), ...patch },
      };
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        /* プライベートブラウズ等で保存不可でも表示は続行 */
      }
      return next;
    });
  }, []);

  return { store, updateWeek };
}

/** 期間内の手入力値を合算（1件も入力がなければ null のまま = 推定表示） */
export function aggregateManual(store: Store, weekStarts: string[]): ManualWeekInput {
  let dm: number | null = null;
  let booking: number | null = null;
  for (const w of weekStarts) {
    const e = store[w];
    if (!e) continue;
    if (e.dm != null) dm = (dm ?? 0) + e.dm;
    if (e.booking != null) booking = (booking ?? 0) + e.booking;
  }
  return { dm, booking };
}
