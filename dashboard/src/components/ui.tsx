import { type HTMLAttributes, type ReactNode, useId } from "react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { cva, type VariantProps } from "class-variance-authority";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { fmtDeltaPct } from "../lib/format";

export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));

/* ───────── Card ───────── */

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-xl border border-line bg-surface shadow-[0_1px_2px_rgba(0,0,0,0.25)]",
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-1 p-4 pb-2 sm:p-5 sm:pb-2", className)} {...props} />;
}

export function CardTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-sm font-semibold text-ink", className)} {...props} />;
}

export function CardDescription({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-xs leading-relaxed text-muted", className)} {...props} />;
}

export function CardContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-4 pt-2 sm:p-5 sm:pt-2", className)} {...props} />;
}

/* ───────── Badge ───────── */

const badgeVariants = cva(
  "inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium leading-4",
  {
    variants: {
      variant: {
        default: "border-line bg-surface-2 text-ink-2",
        accent: "border-transparent bg-[var(--accent-dim)] text-accent-strong",
        outline: "border-line-strong bg-transparent text-ink-2",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export function Badge({
  className,
  variant,
  ...props
}: HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

/** テーマ識別バッジ（色ドット + ラベル。色だけに意味を持たせない） */
export function ThemeBadge({ cssVar, label }: { cssVar: string; label: string }) {
  return (
    <Badge>
      <span
        aria-hidden
        className="size-2 rounded-full"
        style={{ background: `var(${cssVar})` }}
      />
      {label}
    </Badge>
  );
}

/* ───────── 前期比デルタ ───────── */

export function Delta({ value, invert = false }: { value: number | null; invert?: boolean }) {
  if (value == null || !isFinite(value)) {
    return (
      <span className="inline-flex items-center gap-0.5 text-[11px] text-muted">
        <Minus className="size-3" aria-hidden />
        比較なし
      </span>
    );
  }
  const good = invert ? value < 0 : value > 0;
  const Icon = value > 0 ? ArrowUpRight : value < 0 ? ArrowDownRight : Minus;
  const cls = value === 0 ? "text-muted" : good ? "text-good" : "text-crit";
  return (
    <span className={cn("tnum inline-flex items-center gap-0.5 text-[11px] font-medium", cls)}>
      <Icon className="size-3" aria-hidden />
      {fmtDeltaPct(value)}
    </span>
  );
}

/* ───────── セグメント切替（タブ） ───────── */

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { key: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
}) {
  const id = useId();
  return (
    <div
      role="tablist"
      aria-label={label}
      className="inline-flex max-w-full items-center gap-0.5 overflow-x-auto rounded-lg border border-line bg-surface-2 p-0.5"
    >
      {options.map((o) => {
        const active = o.key === value;
        return (
          <button
            key={o.key}
            id={`${id}-${o.key}`}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(o.key)}
            className={cn(
              "whitespace-nowrap rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
              active ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink-2",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/* ───────── セクション見出し ───────── */

export function SectionHeader({
  index,
  title,
  desc,
  right,
}: {
  index: string;
  title: string;
  desc?: string;
  right?: ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <div className="mb-1 flex items-baseline gap-2.5">
          <span aria-hidden className="font-serif text-sm tracking-[0.2em] text-accent">
            {index}
          </span>
          <h2 className="font-serif text-lg font-semibold tracking-wide text-ink sm:text-xl">
            {title}
          </h2>
        </div>
        {desc && <p className="max-w-2xl text-xs leading-relaxed text-muted">{desc}</p>}
      </div>
      {right}
    </div>
  );
}

/* ───────── スコアバー ───────── */

export function ScoreBar({ score, className }: { score: number; className?: string }) {
  const v = Math.round(score);
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div
        role="meter"
        aria-valuenow={v}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`スコア ${v}点`}
        className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2"
      >
        <div
          className="h-full rounded-full"
          style={{
            width: `${Math.min(100, Math.max(2, v))}%`,
            background: "var(--accent)",
          }}
        />
      </div>
      <span className="tnum w-9 shrink-0 text-right text-sm font-semibold text-ink">{v}</span>
    </div>
  );
}

/** 星の重要度表示 */
export function Stars({ n }: { n: number }) {
  return (
    <span aria-label={`重要度 星${n}`} className="text-[10px] tracking-tight text-accent">
      {"★".repeat(n)}
      <span className="text-line-strong">{"★".repeat(5 - n)}</span>
    </span>
  );
}
