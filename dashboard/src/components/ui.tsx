import type { HTMLAttributes, ReactNode } from "react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { cva, type VariantProps } from "class-variance-authority";
import type { Verdict } from "../types";

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

/* ───────── Badge ───────── */

const badgeVariants = cva(
  "inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium leading-4",
  {
    variants: {
      variant: {
        default: "border-line bg-surface-2 text-ink-2",
        accent: "border-transparent bg-[var(--accent-dim)] text-accent-strong",
        outline: "border-line-strong bg-transparent text-ink-2",
        warn: "border-transparent bg-[color-mix(in_oklab,var(--warn)_16%,transparent)] text-warn",
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
      <span aria-hidden className="size-2 rounded-full" style={{ background: `var(${cssVar})` }} />
      {label}
    </Badge>
  );
}

/* ───────── いつもとの比較 ───────── */

const VERDICT_STYLE: Record<"high" | "usual" | "low", string> = {
  high: "text-good",
  usual: "text-muted",
  low: "text-serious",
};
const VERDICT_MARK: Record<"high" | "usual" | "low", string> = { high: "▲", usual: "―", low: "▼" };

/** 「多い／いつもどおり／少ない」。記号と文字の両方で示す（色だけに頼らない） */
export function VerdictTag({
  verdict,
  labels,
  className,
}: {
  verdict: Verdict;
  labels: Record<string, string>;
  className?: string;
}) {
  if (!verdict) return null;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 whitespace-nowrap text-[11px] font-medium",
        VERDICT_STYLE[verdict],
        className,
      )}
    >
      <span aria-hidden className="text-[9px]">
        {VERDICT_MARK[verdict]}
      </span>
      {labels[verdict] ?? verdict}
    </span>
  );
}

/* ───────── セクション見出し ───────── */

export function SectionHeader({
  id,
  index,
  title,
  desc,
  right,
}: {
  id: string;
  index: string;
  title: string;
  desc?: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <div className="mb-1 flex items-baseline gap-2.5">
          <span aria-hidden className="font-serif text-sm tracking-[0.2em] text-accent">
            {index}
          </span>
          <h2 id={id} className="font-serif text-lg font-semibold tracking-wide text-ink sm:text-xl">
            {title}
          </h2>
        </div>
        {desc && <p className="max-w-2xl text-xs leading-relaxed text-muted">{desc}</p>}
      </div>
      {right}
    </div>
  );
}

/** 小見出し（セクション内のまとまり） */
export function SubHeading({ children, note }: { children: ReactNode; note?: ReactNode }) {
  return (
    <div className="mb-2 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
      <h3 className="text-sm font-semibold text-ink">{children}</h3>
      {note && <span className="text-[11px] text-muted">{note}</span>}
    </div>
  );
}

/** 空のときの一言 */
export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-lg border border-dashed border-line px-3 py-3 text-xs text-muted">{children}</p>;
}
