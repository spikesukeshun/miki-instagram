import type { HeatmapData } from "../lib/analytics";
import { WEEKDAYS_JA } from "../lib/format";
import { Card, CardContent, SectionHeader } from "./ui";
import { FadeIn } from "./Motion";

/**
 * ⑥ 投稿時間ヒートマップ（曜日×時間帯の平均スコア）
 * 色はゴールド単色のシーケンシャル（明→暗ではなく面→アクセントの濃度）。
 * 数字も併記して色だけに意味を持たせない。
 */
export function Heatmap({ heatmap }: { heatmap: HeatmapData }) {
  const { cells, hours, maxScore } = heatmap;

  const cellFor = (wd: number, h: number) => cells.find((c) => c.weekday === wd && c.hour === h);

  const bg = (score: number | null) => {
    if (score == null) return "transparent";
    const t = maxScore > 0 ? Math.max(0.12, score / maxScore) : 0.12;
    return `color-mix(in oklab, var(--accent) ${Math.round(t * 78)}%, var(--surface))`;
  };
  const fg = (score: number | null) => {
    if (score == null) return "var(--muted)";
    const t = maxScore > 0 ? score / maxScore : 0;
    return t > 0.55 ? "var(--bg)" : "var(--ink)";
  };

  return (
    <section id="heatmap" aria-labelledby="heatmap-title">
      <SectionHeader
        index="06"
        title="投稿時間ヒートマップ"
        desc="曜日×時間帯ごとの平均投稿スコア（インサイト実在の投稿のみ・2025年以降）。数字はスコア、括弧内は投稿数。n<3の薄いセルは参考。"
      />
      <FadeIn>
        <Card>
          <CardContent className="pt-4">
            <div className="scroll-x">
              <table className="w-full min-w-[520px] border-separate border-spacing-1 text-center text-[11px]">
                <caption className="sr-only">曜日と時間帯ごとの平均投稿スコア</caption>
                <thead>
                  <tr>
                    <th scope="col" className="w-8" aria-label="曜日" />
                    {hours.map((h) => (
                      <th scope="col" key={h} className="tnum pb-1 font-medium text-muted">
                        {h}時
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {WEEKDAYS_JA.map((wd, wi) => (
                    <tr key={wd}>
                      <th scope="row" className="pr-1 text-right font-medium text-ink-2">
                        {wd}
                      </th>
                      {hours.map((h) => {
                        const c = cellFor(wi, h);
                        const has = c && c.count > 0;
                        const reliable = c && c.count >= 3;
                        return (
                          <td
                            key={h}
                            className="tnum rounded-md py-1.5"
                            style={{
                              background: reliable ? bg(c.avgScore) : "var(--surface-2)",
                              color: reliable ? fg(c.avgScore) : "var(--muted)",
                              opacity: reliable ? 1 : has ? 0.6 : 0.45,
                            }}
                            title={
                              has
                                ? `${wd}曜${h}時台: 平均スコア${Math.round(c.avgScore ?? 0)}点（${c.count}投稿）${reliable ? "" : " ※参考（n<3）"}`
                                : `${wd}曜${h}時台: 投稿実績なし`
                            }
                          >
                            {has ? (
                              <>
                                <span className="font-semibold">{Math.round(c.avgScore ?? 0)}</span>
                                <span className="ml-0.5 text-[9px] opacity-75">({c.count})</span>
                              </>
                            ) : (
                              "·"
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-3 flex items-center gap-2 text-[10px] text-muted" aria-hidden>
              低
              <span className="flex h-2.5 w-28 overflow-hidden rounded-full">
                {[0.15, 0.35, 0.55, 0.78].map((t) => (
                  <span
                    key={t}
                    className="h-full flex-1"
                    style={{
                      background: `color-mix(in oklab, var(--accent) ${Math.round(t * 78)}%, var(--surface))`,
                    }}
                  />
                ))}
              </span>
              高（平均スコア）
            </div>
          </CardContent>
        </Card>
      </FadeIn>
    </section>
  );
}
