import type { Labels, Review, Summary as SummaryData, Tile } from "../types";
import { fmtDateShort, fmtInt, fmtNum, fmtPct, fmtUsual, fmtValue, fmtWeek } from "../lib/format";
import { Badge, Card, Empty, SectionHeader, VerdictTag } from "./ui";
import { Sparkline } from "./Sparkline";

const UNIT: Record<Tile["key"], string> = { reach: "人", saved: "件", profile_views: "人", lp: "人" };

function TileCard({ tile, labels }: { tile: Tile; labels: Labels }) {
  // 率のタイル（保存・プロフィール）は件数を大きく、率を添える。比べるのは率
  const main = tile.is_rate ? fmtInt(tile.count) : fmtNum(tile.value);
  return (
    <Card className="flex flex-col gap-1.5 p-3.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-ink-2">{tile.label}</span>
        <VerdictTag verdict={tile.verdict} labels={labels.verdicts} />
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className="tnum text-2xl font-semibold text-ink">{main}</span>
        <span className="text-xs text-muted">{UNIT[tile.key]}</span>
        {tile.is_rate && <span className="tnum text-xs text-ink-2">（{fmtPct(tile.value)}）</span>}
      </div>
      <p className="tnum text-[11px] text-muted">
        {fmtUsual(tile.usual, tile.is_rate)}
        {tile.is_rate && "（率で比較）"}
      </p>
      <Sparkline
        values={tile.spark.map((s) => s.value)}
        usual={tile.usual}
        label={`${tile.label}の12週の推移`}
      />
    </Card>
  );
}

/** ① 先週のまとめ: 振り返りの要約と、確定した先週の4つの数字 */
export function Summary({
  summary,
  review,
  labels,
}: {
  summary: SummaryData | null;
  review: Review | null;
  labels: Labels;
}) {
  const cur = summary?.current_week;
  return (
    <section aria-labelledby="summary-title" id="summary">
      <SectionHeader
        id="summary-title"
        index="01"
        title="先週のまとめ"
        desc={
          summary
            ? `${fmtWeek(summary.week_start)} の確定した数字です。「いつも」は直近12週の真ん中半分。増減の%は小さな数だと大きく揺れるので出していません。`
            : undefined
        }
      />
      {review ? (
        <Card className="mb-3 p-4">
          <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
            <Badge variant="accent">{fmtDateShort(review.written_on)}の振り返り</Badge>
            {review._draft && <Badge variant="outline">下書き</Badge>}
          </div>
          <p className="text-sm leading-relaxed text-ink">{review.summary}</p>
        </Card>
      ) : (
        <div className="mb-3">
          <Empty>振り返りはまだありません。最初の振り返りは次の土曜の週次更新で作られます。</Empty>
        </div>
      )}
      {summary ? (
        <>
          <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
            {summary.tiles.map((t) => (
              <TileCard key={t.key} tile={t} labels={labels} />
            ))}
          </div>
          {cur && (
            <p className="tnum mt-2.5 text-[11px] text-muted">
              今週（{fmtWeek(cur.week_start)}・途中）: 届いた人 {fmtInt(cur.reach)}・プロフィールを見た人{" "}
              {fmtInt(cur.profile_views)}・LPに来た人 {fmtValue(cur.lp_arrivals, false)}・投稿 {cur.posts}本
            </p>
          )}
        </>
      ) : (
        <Empty>確定した週のデータがまだありません。</Empty>
      )}
    </section>
  );
}
