import type { ReactNode } from "react";
import { Bookmark, Eye, Gauge, UserPlus, Users, Zap } from "lucide-react";
import type { PeriodComparison } from "../lib/analytics";
import { fmtInt, fmtPct, fmtSigned, ratio } from "../lib/format";
import { Card, Delta, SectionHeader } from "./ui";
import { FadeIn } from "./Motion";

interface KpiCardDef {
  key: string;
  label: string;
  icon: typeof Eye;
  value: string;
  delta: number | null;
  monthDelta: number | null;
  stars: number;
  note?: string;
}

export function KpiGrid({ cmp, rangeLabel, right }: { cmp: PeriodComparison; rangeLabel: string; right?: ReactNode }) {
  const c = cmp.current;
  const p = cmp.previous;
  const m = cmp.prevMonth;

  const defs: KpiCardDef[] = [
    {
      key: "reach",
      label: "リーチ",
      icon: Eye,
      value: fmtInt(c?.reach),
      delta: ratio(c?.reach, p?.reach),
      monthDelta: ratio(c?.reach, m?.reach),
      stars: 4,
    },
    {
      key: "views",
      label: "インプレッション",
      icon: Zap,
      value: fmtInt(c?.views),
      delta: ratio(c?.views, p?.views),
      monthDelta: ratio(c?.views, m?.views),
      stars: 4,
    },
    {
      key: "saveRate",
      label: "保存率",
      icon: Bookmark,
      value: fmtPct(c?.saveRate),
      delta: ratio(c?.saveRate, p?.saveRate),
      monthDelta: ratio(c?.saveRate, m?.saveRate),
      stars: 5,
      note: "保存 ÷ リーチ（投稿平均）",
    },
    {
      key: "pvRate",
      label: "プロフィール誘導率",
      icon: Users,
      value: fmtPct(c?.pvRate),
      delta: ratio(c?.pvRate, p?.pvRate),
      monthDelta: ratio(c?.pvRate, m?.pvRate),
      stars: 5,
      note: "プロフィール閲覧 ÷ リーチ",
    },
    {
      key: "followers",
      label: "フォロワー増加",
      icon: UserPlus,
      value: c?.followerGain == null ? "—" : fmtSigned(c.followerGain),
      delta: ratio(c?.followerGain, p?.followerGain),
      monthDelta: ratio(c?.followerGain, m?.followerGain),
      stars: 5,
      note: c?.followerGain == null ? "APIは直近30日のみ提供" : undefined,
    },
    {
      key: "score",
      label: "AI総合スコア",
      icon: Gauge,
      value: c?.compositeScore == null ? "—" : `${Math.round(c.compositeScore)}`,
      delta: c?.compositeScore != null && p?.compositeScore != null ? ratio(c.compositeScore, p.compositeScore) : null,
      monthDelta: c?.compositeScore != null && m?.compositeScore != null ? ratio(c.compositeScore, m.compositeScore) : null,
      stars: 5,
      note: "過去16週の自己分布に対する百分位×星重み（100点満点）",
    },
  ];

  return (
    <section id="kpi" aria-labelledby="kpi-title">
      <SectionHeader
        index="01"
        title="KPIダッシュボード"
        desc={`${rangeLabel}の主要指標。DM予約に近い指標（★5）ほど重要度が高い設計です。${c?.partial ? "※進行中の週を含むため数値は増えていきます" : ""}`}
        right={right}
      />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3" role="list">
        {defs.map((d, i) => (
          <FadeIn key={d.key} delay={i * 0.04}>
            <Card role="listitem" className="h-full p-4">
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-1.5 text-xs font-medium text-ink-2">
                  <d.icon className="size-3.5 text-accent" aria-hidden />
                  {d.label}
                </span>
                <span aria-label={`重要度 星${d.stars}`} className="text-[10px] text-accent">
                  {"★".repeat(d.stars)}
                </span>
              </div>
              <div className="tnum mt-2 text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
                {d.value}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="flex items-center gap-1 text-[11px] text-muted">
                  前期比 <Delta value={d.delta} />
                </span>
                <span className="flex items-center gap-1 text-[11px] text-muted">
                  前月比 <Delta value={d.monthDelta} />
                </span>
              </div>
              {d.note && <p className="mt-1.5 text-[10px] leading-relaxed text-muted">{d.note}</p>}
            </Card>
          </FadeIn>
        ))}
      </div>
    </section>
  );
}
