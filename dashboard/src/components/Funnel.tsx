import { useMemo } from "react";
import { PenLine } from "lucide-react";
import type { PeriodKpi } from "../lib/analytics";
import { FUNNEL_ESTIMATES } from "../config";
import { fmtInt, fmtPct } from "../lib/format";
import { Badge, Card, CardContent, SectionHeader } from "./ui";
import { FadeIn } from "./Motion";
import type { ManualWeekInput } from "../lib/manualStore";

interface Stage {
  key: string;
  label: string;
  value: number | null;
  estimated: boolean;
  note?: string;
}

/** ⑤ コンバージョンファネル（DM・予約はAPI非提供 → 手入力 or 推定） */
export function Funnel({
  kpi,
  rangeLabel,
  manual,
  onManualChange,
  editable,
}: {
  kpi: PeriodKpi | null;
  rangeLabel: string;
  manual: ManualWeekInput;
  onManualChange: (patch: Partial<ManualWeekInput>) => void;
  editable: boolean;
}) {
  const stages: Stage[] = useMemo(() => {
    const reach = kpi?.reach ?? null;
    const views = kpi?.views ?? null;
    const pv = kpi?.profileViews ?? null;
    const follows = kpi?.followerGain ?? null;
    const dmEst = pv != null ? pv * FUNNEL_ESTIMATES.dmPerProfileView : null;
    const dm = manual.dm ?? dmEst;
    const bookingEst = dm != null ? dm * FUNNEL_ESTIMATES.bookingPerDm : null;
    const booking = manual.booking ?? bookingEst;
    return [
      { key: "reach", label: "リーチ", value: reach, estimated: false, note: "届いた人数" },
      { key: "views", label: "インプレッション", value: views, estimated: false, note: "表示回数（同一人物の再閲覧含む）" },
      { key: "pv", label: "プロフィール閲覧", value: pv, estimated: false, note: "投稿→プロフィールへ移動した数" },
      { key: "follow", label: "フォロー", value: follows, estimated: false, note: follows == null ? "APIは直近30日のみ" : "純増数" },
      { key: "dm", label: "DM問い合わせ", value: dm, estimated: manual.dm == null, note: manual.dm == null ? "推定値（手入力で確定）" : "手入力値" },
      { key: "booking", label: "予約", value: booking, estimated: manual.booking == null, note: manual.booking == null ? "推定値（手入力で確定）" : "手入力値" },
    ];
  }, [kpi, manual]);

  const max = Math.max(...stages.map((s) => s.value ?? 0), 1);
  const reach = stages[0].value;

  return (
    <section id="funnel" aria-labelledby="funnel-title">
      <SectionHeader
        index="05"
        title="コンバージョンファネル"
        desc={`${rangeLabel}の「リーチ → DM予約」導線。DM・予約数はInstagram APIで取得できないため、実数を下の入力欄に記録してください（この端末に保存されます）。`}
      />
      <FadeIn>
        <Card>
          <CardContent className="pt-4">
            <ol className="flex flex-col gap-1.5" aria-label="コンバージョンファネルの段階">
              {stages.map((s, i) => {
                const widthPct =
                  s.value == null ? 0 : Math.max(4, Math.pow(s.value / max, 0.45) * 100);
                // インプレッションはリーチより大きくなる（同一人物の再閲覧）ため倍率で表示
                const isViews = s.key === "views";
                const convFromPrev =
                  i > 0 && !isViews && s.value != null && stages[i - 1].value
                    ? s.value / (stages[i - 1].value as number)
                    : null;
                const frequency =
                  isViews && s.value != null && reach ? s.value / reach : null;
                const convFromReach =
                  i > 1 && s.value != null && reach ? s.value / reach : null;
                return (
                  <li key={s.key} className="grid grid-cols-[7.5rem_1fr] items-center gap-2 sm:grid-cols-[9rem_1fr_10rem]">
                    <span className="text-xs font-medium text-ink-2">{s.label}</span>
                    <div className="flex items-center gap-2">
                      <div
                        className="h-7 rounded-md"
                        style={{
                          width: `${widthPct}%`,
                          background: s.estimated ? "transparent" : "var(--accent-dim)",
                          border: s.estimated
                            ? "1px dashed var(--border-strong)"
                            : "1px solid var(--accent)",
                          minWidth: s.value != null ? "2rem" : 0,
                        }}
                        aria-hidden
                      />
                      <span className="tnum shrink-0 text-sm font-semibold text-ink">
                        {s.value == null ? "—" : fmtInt(s.value)}
                        {s.estimated && s.value != null && (
                          <span className="ml-1 text-[10px] font-normal text-muted">推定</span>
                        )}
                      </span>
                    </div>
                    <span className="tnum col-start-2 -mt-1 text-[10px] text-muted sm:col-start-3 sm:mt-0">
                      {frequency != null && `リーチの${frequency.toFixed(1)}倍（再閲覧含む）`}
                      {convFromPrev != null && `前段から ${fmtPct(convFromPrev)}`}
                      {convFromReach != null && ` ／ リーチ比 ${fmtPct(convFromReach, 2)}`}
                      {convFromPrev == null && frequency == null && s.note && ` ${s.note}`}
                    </span>
                  </li>
                );
              })}
            </ol>

            {!editable && (
              <p className="mt-4 text-[11px] text-muted">
                DM・予約の実数入力は「今週」「先週」表示のときに週単位で記録できます（複数週表示では入力済みの週の合計を表示）。
              </p>
            )}
            {editable && (
            <div className="mt-5 rounded-lg border border-line bg-surface-2 p-3.5">
              <p className="flex items-center gap-1.5 text-xs font-semibold text-ink-2">
                <PenLine className="size-3.5 text-accent" aria-hidden />
                {rangeLabel}の実数を記録（DM・予約）
              </p>
              <div className="mt-2.5 flex flex-wrap items-end gap-4">
                <label className="flex flex-col gap-1 text-[11px] text-muted">
                  DM問い合わせ数
                  <input
                    type="number"
                    min={0}
                    inputMode="numeric"
                    value={manual.dm ?? ""}
                    placeholder="未入力=推定"
                    onChange={(e) =>
                      onManualChange({ dm: e.target.value === "" ? null : Math.max(0, Number(e.target.value)) })
                    }
                    className="tnum w-32 rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm text-ink placeholder:text-muted"
                  />
                </label>
                <label className="flex flex-col gap-1 text-[11px] text-muted">
                  予約数
                  <input
                    type="number"
                    min={0}
                    inputMode="numeric"
                    value={manual.booking ?? ""}
                    placeholder="未入力=推定"
                    onChange={(e) =>
                      onManualChange({ booking: e.target.value === "" ? null : Math.max(0, Number(e.target.value)) })
                    }
                    className="tnum w-32 rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm text-ink placeholder:text-muted"
                  />
                </label>
                <Badge variant="outline" className="mb-1.5">
                  破線バー = 推定（プロフィール閲覧×{Math.round(FUNNEL_ESTIMATES.dmPerProfileView * 100)}%、DM×
                  {Math.round(FUNNEL_ESTIMATES.bookingPerDm * 100)}%）
                </Badge>
              </div>
            </div>
            )}
          </CardContent>
        </Card>
      </FadeIn>
    </section>
  );
}
