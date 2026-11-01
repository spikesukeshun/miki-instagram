import type { Usual } from "../types";

/**
 * 12週の小さな折れ線。「いつもの範囲」を帯で、最後の週（先週）を点で示す。
 * 色は CSS 変数（インラインSVGなのでテーマ切り替えにそのまま追従する）。
 */
export function Sparkline({
  values,
  usual,
  label,
}: {
  values: (number | null)[];
  usual?: Usual | null;
  label: string;
}) {
  const W = 120;
  const H = 32;
  const pad = 3;
  const nums = values.filter((v): v is number => v != null);
  if (nums.length < 2) return null;
  const lo = Math.min(...nums, usual?.low ?? Infinity);
  const hi = Math.max(...nums, usual?.high ?? -Infinity);
  const span = hi - lo || 1;
  const x = (i: number) => pad + (i * (W - pad * 2)) / Math.max(values.length - 1, 1);
  const y = (v: number) => H - pad - ((v - lo) / span) * (H - pad * 2);

  let d = "";
  values.forEach((v, i) => {
    if (v == null) return;
    d += `${d && values[i - 1] != null ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
  });
  const lastIdx = values.length - 1;
  const last = values[lastIdx];

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-8 w-full" role="img" aria-label={label} preserveAspectRatio="none">
      {usual && (
        <rect
          x={pad}
          width={W - pad * 2}
          y={y(usual.high)}
          height={Math.max(1, y(usual.low) - y(usual.high))}
          style={{ fill: "var(--accent-dim)" }}
        />
      )}
      <path d={d} fill="none" style={{ stroke: "var(--ink-2)" }} strokeWidth={1.25} vectorEffect="non-scaling-stroke" />
      {last != null && <circle cx={x(lastIdx)} cy={y(last)} r={2.5} style={{ fill: "var(--accent-strong)" }} />}
    </svg>
  );
}
