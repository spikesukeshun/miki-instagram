import type { DashboardData } from "../types";
import raw from "../../data/dashboard_data.json";

/**
 * ビルド時に埋め込まれるデータスナップショット。
 * 更新は fetch_dashboard_data.py 実行 → npm run build → Artifact再公開。
 */
export const dashboardData = raw as unknown as DashboardData;
