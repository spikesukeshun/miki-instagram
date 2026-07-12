import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { WeekAgg } from "../types";
import { fmtInt, fmtPct } from "../lib/format";
import { useChartTokens } from "../lib/useTheme";
import { Card, CardContent, SectionHeader, Segmented } from "./ui";
import { FadeIn } from "./Motion";

type MetricKey = "reach" | "saveRate" | "pvRate";

const METRICS: { key: MetricKey; label: string; isRate: boolean; desc: string }[] = [
  { key: "reach", label: "リーチ", isRate: false, desc: "週にアカウントが届いた人数（アカウント合計）" },
  { key: "saveRate", label: "保存率", isRate: true, desc: "その週の投稿の平均保存率（保存÷リーチ）" },
  { key: "pvRate", label: "プロフィール閲覧率", isRate: true, desc: "プロフィール閲覧 ÷ 週リーチ" },
];

export function TrendChart({ weeks }: { weeks: WeekAgg[] }) {
  const [metric, setMetric] = useState<MetricKey>("reach");
  const t = useChartTokens();
  const def = METRICS.find((m) => m.key === metric)!;

  const data = weeks.map((w) => ({
    label: w.label,
    value: w[metric],
    partial: w.partial,
    postCount: w.postCount,
  }));
  const lastIdx = data.length - 1;

  return (
    <section id="trend" aria-labelledby="trend-title">
      <SectionHeader
        index="02"
        title="週次推移"
        desc={def.desc}
        right={
          <Segmented
            label="表示する指標"
            options={METRICS.map((m) => ({ key: m.key, label: m.label }))}
            value={metric}
            onChange={setMetric}
          />
        }
      />
      <FadeIn>
        <Card>
          <CardContent className="pt-4">
            <div className="h-56 sm:h-64" role="img" aria-label={`${def.label}の週次推移グラフ`}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke={t.grid} strokeDasharray="0" vertical={false} />
                  <XAxis
                    dataKey="label"
                    tick={{ fill: t.muted, fontSize: 10 }}
                    tickLine={false}
                    axisLine={{ stroke: t.axis }}
                    interval="preserveStartEnd"
                    minTickGap={24}
                  />
                  <YAxis
                    tick={{ fill: t.muted, fontSize: 10 }}
                    tickLine={false}
                    axisLine={false}
                    width={44}
                    tickFormatter={(v: number) => (def.isRate ? `${(v * 100).toFixed(1)}%` : fmtInt(v))}
                  />
                  <Tooltip
                    cursor={{ stroke: t.axis, strokeWidth: 1 }}
                    contentStyle={{
                      background: t.surface,
                      border: `1px solid ${t.axis}`,
                      borderRadius: 8,
                      fontSize: 12,
                      color: t.ink,
                    }}
                    labelStyle={{ color: t.ink2, fontSize: 11 }}
                    formatter={(v: number | string, _n, item) => {
                      const val = typeof v === "number" ? (def.isRate ? fmtPct(v) : fmtInt(v)) : "—";
                      const suffix = item?.payload?.partial ? "（進行中）" : "";
                      return [`${val}${suffix}`, def.label];
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke={t.accent}
                    strokeWidth={2}
                    connectNulls
                    dot={(props) => {
                      const { cx, cy, index } = props;
                      if (cx == null || cy == null) return <g key={`d-${index}`} />;
                      const isLast = index === lastIdx;
                      return (
                        <circle
                          key={`d-${index}`}
                          cx={cx}
                          cy={cy}
                          r={isLast ? 4 : 2.5}
                          fill={isLast ? t.accent : t.surface}
                          stroke={t.accent}
                          strokeWidth={1.5}
                        />
                      );
                    }}
                    activeDot={{ r: 5, fill: t.accent, stroke: t.surface, strokeWidth: 2 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p className="mt-2 text-[10px] text-muted">
              右端の週は進行中のため確定値ではありません。リーチはアカウント合計、率は投稿平均です。
            </p>
          </CardContent>
        </Card>
      </FadeIn>
    </section>
  );
}
