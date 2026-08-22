import { AlertTriangle, CalendarDays, Lightbulb } from "lucide-react";
import type { Strategy } from "../lib/strategy";
import { themeDef } from "../config";
import { fmtInt } from "../lib/format";
import { Badge, Card, CardContent, CardHeader, CardTitle, SectionHeader, ThemeBadge } from "./ui";
import { FadeIn } from "./Motion";

const rangeInt = (r: [number, number] | null) =>
  r ? `${fmtInt(r[0])}〜${fmtInt(r[1])}` : "—";
const rangePct = (r: [number, number] | null) =>
  r ? `${(r[0] * 100).toFixed(1)}〜${(r[1] * 100).toFixed(1)}%` : "—";

/** ⑧ 来週の投稿戦略。投稿枠は実運用の固定枠、テーマだけ実績から選ぶ */
export function NextWeek({ strategy }: { strategy: Strategy }) {
  const slots = strategy.weekPlan.map((s) => `${s.weekdayLabel}${s.timeLabel}`).join(" / ");
  return (
    <section id="nextweek" aria-labelledby="nextweek-title">
      <SectionHeader
        index="08"
        title="来週の投稿戦略"
        desc={`投稿枠は実運用の固定枠（${slots}）。テーマはテーマ別の実績スコアから自動選定しています。想定値は該当テーマの実績平均±25%です。`}
      />
      <FadeIn>
        {strategy.scheduleDrift && (
          <Card className="mb-3 border-l-2 border-l-[var(--serious)]">
            <CardContent className="flex items-start gap-2 pt-4 text-xs leading-relaxed text-ink-2">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-serious" aria-hidden />
              <span>
                設定上の投稿枠（{strategy.scheduleDrift.expected.join(" / ")}）と、直近8週の実際の投稿
                （{strategy.scheduleDrift.actual.join(" / ")}）がズレています。
                運用を変えたなら <code>check_week_slots.py</code> の <code>SLOTS</code> を直してください。
              </span>
            </CardContent>
          </Card>
        )}

        {/* 週3投稿プラン */}
        <div className="mb-3 grid gap-3 md:grid-cols-3">
          {strategy.weekPlan.map((s) => {
            const t = themeDef(s.theme);
            const rec = strategy.themeRanking.find((r) => r.theme === s.theme);
            return (
              <Card key={s.slot} className="flex h-full flex-col p-4">
                <div className="flex items-center justify-between">
                  <span className="font-serif text-sm tracking-[0.2em] text-accent">
                    POST {s.slot}
                  </span>
                  <Badge variant="outline">
                    <CalendarDays className="size-3" aria-hidden />
                    {s.weekdayLabel} {s.timeLabel}
                  </Badge>
                </div>
                <div className="mt-2">
                  <ThemeBadge cssVar={t.cssVar} label={t.label} />
                </div>
                <p className="mt-2 flex-1 text-xs leading-relaxed text-ink-2">{s.angle}</p>
                {s.slotNote && (
                  <p className="mt-2 text-[10px] leading-relaxed text-muted">{s.slotNote}</p>
                )}
                {rec && (
                  <p className="tnum mt-2 border-t border-line pt-2 text-[10px] leading-relaxed text-muted">
                    想定リーチ {rangeInt(rec.expectedReach)} ／ 想定保存率 {rangePct(rec.expectedSaveRate)}
                    <br />
                    想定プロフィール閲覧率 {rangePct(rec.expectedPvRate)}
                  </p>
                )}
              </Card>
            );
          })}
        </div>

        {/* テーマランキング */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <Lightbulb className="size-4 text-accent" aria-hidden />
              おすすめテーマランキング
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="grid gap-2.5 sm:grid-cols-2">
              {strategy.themeRanking.map((r) => {
                const t = themeDef(r.theme);
                return (
                  <li key={r.theme} className="flex items-start gap-2.5 text-xs">
                    <span className="tnum mt-0.5 w-4 shrink-0 font-serif text-accent">{r.rank}</span>
                    <div>
                      <ThemeBadge cssVar={t.cssVar} label={t.label} />
                      <p className="mt-1 leading-relaxed text-muted">{r.reason}</p>
                    </div>
                  </li>
                );
              })}
            </ol>
          </CardContent>
        </Card>
      </FadeIn>
    </section>
  );
}
