import { CalendarDays, Clock3, Images, Lightbulb, MousePointerClick, Type } from "lucide-react";
import type { Strategy } from "../lib/strategy";
import { themeDef } from "../config";
import { WEEKDAYS_JA, fmtInt } from "../lib/format";
import { Badge, Card, CardContent, CardHeader, CardTitle, SectionHeader, ThemeBadge } from "./ui";
import { FadeIn } from "./Motion";

const rangeInt = (r: [number, number] | null) =>
  r ? `${fmtInt(r[0])}〜${fmtInt(r[1])}` : "—";
const rangePct = (r: [number, number] | null) =>
  r ? `${(r[0] * 100).toFixed(1)}〜${(r[1] * 100).toFixed(1)}%` : "—";

/** ⑧ 来週の投稿戦略（過去実績学習ベースの提案） */
export function NextWeek({ strategy }: { strategy: Strategy }) {
  return (
    <section id="nextweek" aria-labelledby="nextweek-title">
      <SectionHeader
        index="08"
        title="来週の投稿戦略"
        desc="過去実績（テーマ統計・曜日×時間・カルーセル枚数×スコア）から自動生成した次週プラン。想定値は該当テーマの実績平均±25%です。"
      />
      <FadeIn>
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

        <div className="grid gap-3 md:grid-cols-2">
          {/* テーマランキング */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-1.5">
                <Lightbulb className="size-4 text-accent" aria-hidden />
                おすすめテーマランキング
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="flex flex-col gap-2.5">
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

          {/* 曜日・時間・枚数 */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-1.5">
                <Clock3 className="size-4 text-accent" aria-hidden />
                おすすめ投稿枠・カルーセル枚数
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 text-xs">
              <div>
                <p className="mb-1.5 font-medium text-ink-2">実績の良い曜日×時間（平均スコア順）</p>
                <div className="flex flex-wrap gap-1.5">
                  {strategy.bestSlots.map((s, i) => (
                    <Badge key={i} variant={i === 0 ? "accent" : "default"}>
                      {WEEKDAYS_JA[s.weekday]}曜{s.hour}時台 ・ {Math.round(s.avgScore)}点（{s.count}件）
                    </Badge>
                  ))}
                </div>
              </div>
              <div className="border-t border-line pt-3">
                <p className="mb-1 flex items-center gap-1.5 font-medium text-ink-2">
                  <Images className="size-3.5 text-accent" aria-hidden />
                  推奨カルーセル枚数: {strategy.slideCount.label}
                </p>
                <p className="leading-relaxed text-muted">{strategy.slideCount.detail}</p>
              </div>
            </CardContent>
          </Card>

          {/* CTA・タイトル改善 */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-1.5">
                <MousePointerClick className="size-4 text-accent" aria-hidden />
                CTA改善案・プロフィール誘導改善案
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="flex list-disc flex-col gap-1.5 pl-4 text-xs leading-relaxed text-ink-2">
                {strategy.ctaIdeas.map((c, i) => (
                  <li key={`c${i}`}>{c}</li>
                ))}
                {strategy.pvRateIdeas.map((c, i) => (
                  <li key={`p${i}`}>{c}</li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-1.5">
                <Type className="size-4 text-accent" aria-hidden />
                タイトル改善案・保存率向上案
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="flex list-disc flex-col gap-1.5 pl-4 text-xs leading-relaxed text-ink-2">
                {strategy.titleIdeas.map((c, i) => (
                  <li key={`t${i}`}>{c}</li>
                ))}
                {strategy.saveRateIdeas.map((c, i) => (
                  <li key={`s${i}`}>{c}</li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      </FadeIn>
    </section>
  );
}
