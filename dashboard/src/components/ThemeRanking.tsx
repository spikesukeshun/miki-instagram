import { useState } from "react";
import { TrendingDown, TrendingUp } from "lucide-react";
import type { ThemeStats } from "../types";
import { themeDef } from "../config";
import { fmtInt, fmtPct } from "../lib/format";
import { Badge, Card, SectionHeader, Segmented, ThemeBadge } from "./ui";
import { FadeIn } from "./Motion";

type SortKey = "total" | "saveRate" | "pvRate";

/** ④ テーマランキング + 成功/改善テーマの自動判定 */
export function ThemeRanking({ themes }: { themes: ThemeStats[] }) {
  const [sort, setSort] = useState<SortKey>("total");

  const usable = themes.filter((t) => t.count >= 3);
  const sortedThemes = [...usable].sort((a, b) => {
    if (sort === "saveRate") return (b.avgSaveRate ?? -1) - (a.avgSaveRate ?? -1);
    if (sort === "pvRate") return (b.avgPvRate ?? -1) - (a.avgPvRate ?? -1);
    return b.totalScore - a.totalScore;
  });

  const best = [...usable].sort((a, b) => b.totalScore - a.totalScore)[0];
  const worst = [...usable].sort((a, b) => a.totalScore - b.totalScore)[0];

  return (
    <section id="themes" aria-labelledby="themes-title">
      <SectionHeader
        index="04"
        title="テーマランキング"
        desc="テーマごとの平均実績。総合はスコアの全期間6割+直近8週4割のブレンドで、AIが成功テーマ・改善テーマを自動判定します。"
        right={
          <Segmented
            label="並び替え"
            options={[
              { key: "total", label: "総合" },
              { key: "saveRate", label: "保存率順" },
              { key: "pvRate", label: "誘導率順" },
            ]}
            value={sort}
            onChange={setSort}
          />
        }
      />
      <FadeIn>
        <div className="mb-3 grid gap-2 sm:grid-cols-2">
          {best && (
            <Card className="border-l-2 border-l-[var(--good)] p-3.5">
              <p className="flex items-center gap-1.5 text-xs font-semibold text-good">
                <TrendingUp className="size-3.5" aria-hidden /> 成功テーマ（伸ばす）
              </p>
              <p className="mt-1 text-sm font-medium text-ink">{themeDef(best.theme).label}</p>
              <p className="mt-0.5 text-[11px] leading-relaxed text-muted">
                総合{Math.round(best.totalScore)}点・成功率{fmtPct(best.successRate, 0)}。翌週プランの軸に据える
              </p>
            </Card>
          )}
          {worst && worst.theme !== best?.theme && (
            <Card className="border-l-2 border-l-[var(--serious)] p-3.5">
              <p className="flex items-center gap-1.5 text-xs font-semibold text-serious">
                <TrendingDown className="size-3.5" aria-hidden /> 改善テーマ（切り口を変える）
              </p>
              <p className="mt-1 text-sm font-medium text-ink">{themeDef(worst.theme).label}</p>
              <p className="mt-0.5 text-[11px] leading-relaxed text-muted">
                総合{Math.round(worst.totalScore)}点。本数を絞り、保存される形式（Q&A・早見表）に変える
              </p>
            </Card>
          )}
        </div>
        <Card>
          <div className="scroll-x">
            <table className="w-full min-w-[560px] text-left text-xs">
              <caption className="sr-only">テーマ別の平均実績一覧</caption>
              <thead>
                <tr className="border-b border-line text-[11px] text-muted">
                  <th scope="col" className="p-3 font-medium">テーマ</th>
                  <th scope="col" className="tnum p-3 text-right font-medium">投稿数</th>
                  <th scope="col" className="tnum p-3 text-right font-medium">平均リーチ</th>
                  <th scope="col" className="tnum p-3 text-right font-medium">平均保存率</th>
                  <th scope="col" className="tnum p-3 text-right font-medium">誘導率</th>
                  <th scope="col" className="tnum p-3 text-right font-medium">フォロー/投稿</th>
                  <th scope="col" className="tnum p-3 text-right font-medium">成功率</th>
                  <th scope="col" className="tnum p-3 text-right font-medium">総合</th>
                </tr>
              </thead>
              <tbody>
                {sortedThemes.map((t, i) => {
                  const def = themeDef(t.theme);
                  return (
                    <tr key={t.theme} className="border-b border-line last:border-0">
                      <td className="p-3">
                        <span className="flex items-center gap-2">
                          <span className="tnum w-4 font-serif text-accent">{i + 1}</span>
                          <ThemeBadge cssVar={def.cssVar} label={def.label} />
                        </span>
                      </td>
                      <td className="tnum p-3 text-right text-ink-2">{t.count}</td>
                      <td className="tnum p-3 text-right text-ink">{fmtInt(t.avgReach)}</td>
                      <td className="tnum p-3 text-right text-ink">{fmtPct(t.avgSaveRate)}</td>
                      <td className="tnum p-3 text-right text-ink">{fmtPct(t.avgPvRate)}</td>
                      <td className="tnum p-3 text-right text-ink">
                        {t.followsPerPost == null ? "—" : t.followsPerPost.toFixed(2)}
                      </td>
                      <td className="tnum p-3 text-right text-ink">{fmtPct(t.successRate, 0)}</td>
                      <td className="tnum p-3 text-right font-semibold text-ink">
                        {Math.round(t.totalScore)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {themes.some((t) => t.count < 3) && (
            <p className="border-t border-line p-3 text-[10px] text-muted">
              投稿数3件未満のテーマはサンプル不足のためランキング対象外:{" "}
              {themes
                .filter((t) => t.count < 3)
                .map((t) => `${themeDef(t.theme).short}(${t.count})`)
                .join("、")}
            </p>
          )}
        </Card>
        <div className="mt-2 flex flex-wrap gap-1.5" aria-hidden>
          <Badge variant="outline">成功率 = スコア60点以上の投稿の割合</Badge>
          <Badge variant="outline">誘導率 = プロフィール閲覧 ÷ リーチ</Badge>
        </div>
      </FadeIn>
    </section>
  );
}
