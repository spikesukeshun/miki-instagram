import type { DashboardData } from "../types";
// 画面が使う項目だけを名前で取り込む（vite.config.ts の json.stringify:false と組で、
// 使わない posts 全件などが公開ページに埋め込まれないようにする）
import { account, derived, fetched_at } from "../../data/dashboard_data.json";

/**
 * ビルド時に埋め込まれるデータスナップショット。
 * 更新は fetch_dashboard_data.py 実行 → npm run build → 公開。
 */
export const dashboardData = { account, derived, fetched_at } as unknown as DashboardData;
