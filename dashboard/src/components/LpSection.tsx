import type { ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import type { LpDerived, LpFunnel } from "../types";
import { fmtDateShort, fmtInt, fmtNum, fmtWeek } from "../lib/format";
import { Card, Empty, SectionHeader, SubHeading } from "./ui";

const DEVICE_LABEL: Record<string, string> = { mobile: "スマホ", desktop: "パソコン", tablet: "タブレット" };

function Steps({ f }: { f: LpFunnel }) {
  const steps: { label: string; value: string; note?: string }[] = [
    { label: "プロフィールを見た", value: fmtInt(f.profile_views), note: "Instagram" },
    { label: "リンクをタップ", value: fmtInt(f.link_taps), note: "Instagram" },
    { label: "LPに着いた", value: fmtInt(f.arrivals), note: "GA4" },
    { label: "しっかり見た", value: fmtInt(f.engaged), note: "10秒以上など" },
    {
      label: "予約ボタン",
      value: fmtInt((f.cta_dm ?? 0) + (f.cta_hotpepper ?? 0)),
      note: `DM ${fmtInt(f.cta_dm)}・ホットペッパー ${fmtInt(f.cta_hotpepper)}`,
    },
  ];
  return (
    <ol className="flex flex-col gap-1.5 sm:flex-row sm:items-stretch sm:gap-0" aria-label="予約までの流れ">
      {steps.map((s, i) => (
        <li key={s.label} className="flex items-center gap-1.5 sm:flex-1">
          <div className="flex flex-1 items-baseline justify-between gap-2 rounded-lg bg-surface-2 px-3 py-2 sm:flex-col sm:items-start sm:justify-start">
            <span className="text-[11px] text-ink-2">{s.label}</span>
            <span className="tnum text-lg font-semibold text-ink">{s.value}</span>
            {s.note && <span className="text-[10px] text-muted">{s.note}</span>}
          </div>
          {i < steps.length - 1 && (
            <ChevronRight className="hidden size-4 shrink-0 text-line-strong sm:block" aria-hidden />
          )}
        </li>
      ))}
    </ol>
  );
}

/** 12週の推移: 棒=LPに着いた（Instagram経由）、点=リンクのタップ（Instagram側の数）。
 *  幅いっぱいに広げるため SVG ではなく列のならびで描く（点が楕円にならない） */
function Trend({ trend }: { trend: NonNullable<LpDerived["trend"]> }) {
  const max = Math.max(1, ...trend.map((t) => Math.max(t.arrivals ?? 0, t.link_taps ?? 0)));
  const pct = (v: number) => `${(v / max) * 100}%`;
  return (
    <figure>
      <div className="flex h-28 items-end gap-1 border-b border-line-strong" role="img"
        aria-label="LPに着いた人とリンクのタップの12週の推移">
        {trend.map((t) => (
          <div key={t.week_start} className="relative flex h-full flex-1 flex-col justify-end"
            title={`${fmtDateShort(t.week_start)}の週: LPに着いた ${fmtInt(t.arrivals)}・リンクのタップ ${fmtInt(t.link_taps)}`}>
            <span className="tnum mb-0.5 text-center text-[10px] text-ink-2">{fmtInt(t.arrivals)}</span>
            <div className="mx-auto w-3/5 rounded-t-sm"
              style={{ height: pct(t.arrivals ?? 0), minHeight: 1,
                       background: t.partial ? "var(--border-strong)" : "var(--accent)" }} />
            {t.link_taps != null && (
              <span aria-hidden className="absolute left-1/2 size-1.5 -translate-x-1/2 translate-y-1/2 rounded-full"
                style={{ bottom: pct(t.link_taps), background: "var(--ink)" }} />
            )}
          </div>
        ))}
      </div>
      <figcaption className="mt-1 flex flex-wrap justify-between gap-x-3 text-[10px] text-muted">
        <span>
          {fmtDateShort(trend[0]?.week_start)}の週 〜 {fmtDateShort(trend[trend.length - 1]?.week_start)}の週（右端は途中）
        </span>
        <span>
          <span className="mr-1 inline-block size-2 rounded-sm align-middle" style={{ background: "var(--accent)" }} />
          LPに着いた（数字）
          <span className="ml-2.5 mr-1 inline-block size-2 rounded-full align-middle" style={{ background: "var(--ink)" }} />
          リンクのタップ
        </span>
      </figcaption>
    </figure>
  );
}

function Chip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-line px-3 py-2">
      <p className="text-[10px] text-muted">{label}</p>
      <div className="tnum mt-0.5 text-xs text-ink">{children}</div>
    </div>
  );
}

/** ④ LP（予約導線）: Instagram → LP → 予約ボタンの流れと、来た人の内訳 */
export function LpSection({ lp }: { lp: LpDerived }) {
  return (
    <section aria-labelledby="lp-title" id="lp">
      <SectionHeader
        id="lp-title"
        index="04"
        title="LP（予約導線）"
        desc="Instagram経由の訪問だけを数えています（直接アクセスには海外からの自動アクセスが混ざるため）。件数が少ないので、内訳は直近4週の合計です。"
      />
      {!lp.available || !lp.funnel ? (
        <Empty>{lp.reason ?? "LPのデータがありません。"}</Empty>
      ) : (
        <div className="flex flex-col gap-3">
          <Card className="p-3.5">
            <SubHeading note={lp.period_start ? `${fmtWeek(lp.period_start).split("〜")[0]}〜 直近${lp.period_weeks}週の合計` : undefined}>
              予約までの流れ
            </SubHeading>
            <Steps f={lp.funnel} />
            {lp.funnel_all && (
              <p className="tnum mt-2 text-[11px] text-muted">
                公開（{fmtDateShort(lp.since)}の週）からの合計: LPに着いた {fmtInt(lp.funnel_all.arrivals)}・予約ボタン DM{" "}
                {fmtInt(lp.funnel_all.cta_dm)}・ホットペッパー {fmtInt(lp.funnel_all.cta_hotpepper)}
              </p>
            )}
          </Card>
          {lp.trend && lp.trend.length > 1 && (
            <Card className="p-3.5">
              <SubHeading>週ごとの推移</SubHeading>
              <Trend trend={lp.trend} />
            </Card>
          )}
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            <Chip label="平均の滞在時間">{lp.avg_engagement_sec != null ? `${lp.avg_engagement_sec}秒` : "—"}</Chip>
            <Chip label="ホットペッパーから戻ってきた">
              {lp.funnel.bounced != null ? `${fmtInt(lp.funnel.bounced)}回` : "次回の更新から"}
              <span className="block text-[10px] text-muted">満席などで予約まで進めなかった人</span>
            </Chip>
            <Chip label="端末">
              {lp.devices?.length
                ? lp.devices.map((d) => `${DEVICE_LABEL[d.device] ?? d.device} ${fmtNum(d.sessions)}`).join("・")
                : "次回の更新から"}
            </Chip>
            <Chip label="初めて／再訪">
              {lp.visitors ? `初めて ${fmtNum(lp.visitors.new)}・再訪 ${fmtNum(lp.visitors.returning)}` : "次回の更新から"}
            </Chip>
          </div>
          <div className="grid gap-2 md:grid-cols-3">
            <Chip label="コース別の予約ボタン">
              {lp.courses?.length ? (
                <>
                  <ul className="flex flex-col gap-0.5">
                    {lp.courses.map((c) => (
                      <li key={c.course}>
                        {c.course}: DM {fmtInt(c.cta_dm)}・ホットペッパー {fmtInt(c.cta_hotpepper)}
                      </li>
                    ))}
                  </ul>
                  {lp.courses.some((c) => c.course === "未選択" || c.course === "（不明）") && (
                    <p className="mt-0.5 text-[10px] text-muted">
                      「未選択」はコースを選ばないままボタンを押した分、「（不明）」はコースが記録されなかった分
                    </p>
                  )}
                </>
              ) : (
                <span className="text-[11px] text-muted">{lp.courses_note ?? "まだ押されていません"}</span>
              )}
            </Chip>
            <Chip label={lp.sources_period === "recent" ? "参照元（直近4週・全部）" : "参照元（公開からの全部）"}>
              <p className="mb-0.5 text-[10px] text-muted">(direct) / (none) は海外からの自動アクセスが多く、上の流れには入れていません</p>
              <ul className="flex flex-col gap-0.5">
                {(lp.sources ?? []).slice(0, 4).map((s) => (
                  <li key={s.source_medium}>
                    {s.source_medium} {fmtInt(s.sessions)}
                    <span className="text-muted">（しっかり見た {fmtInt(s.engaged_sessions)}）</span>
                  </li>
                ))}
              </ul>
            </Chip>
            <Chip label="Google検索（公開から）">
              {lp.search
                ? `表示 ${fmtInt(lp.search.impressions)}・クリック ${fmtInt(lp.search.clicks)}・平均 ${lp.search.position}位`
                : "—"}
            </Chip>
          </div>
        </div>
      )}
    </section>
  );
}
