import type { EditStats, Labels, Post, ReviewView, TrialStat } from "../types";
import { themeDef } from "../config";
import { fmtDateShort, fmtInt, fmtPct, fmtPostDate, fmtWeek } from "../lib/format";
import { Badge, Card, Empty, SectionHeader, SubHeading, ThemeBadge } from "./ui";
import { EditsLine, FIELD_INFO, MetricValue, TrialLine, targetField } from "./PostBits";

const DECISION_STYLE: Record<string, "accent" | "default" | "outline"> = {
  standard: "accent",
  again: "default",
  stop: "outline",
};

function JudgedPost({ post, review, labels }: { post: Post; review: ReviewView; labels: Labels }) {
  const theme = themeDef(post.theme);
  const field = targetField(post.trial, labels);
  const verdict = post.trial?.tag
    ? review.latest?.verdicts?.find((v) => v.tag === post.trial?.tag)
    : undefined;
  return (
    <Card className="flex flex-col gap-2 p-3.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="tnum text-xs font-medium text-ink-2">{fmtPostDate(post.date)}</span>
        <ThemeBadge cssVar={theme.cssVar} label={theme.short} />
        {post.media_type === "VIDEO" && <Badge variant="outline">リール</Badge>}
      </div>
      <a
        href={post.permalink}
        target="_blank"
        rel="noreferrer"
        className="line-clamp-2 text-[13px] font-medium leading-snug text-ink hover:text-accent-strong hover:underline"
      >
        {post.cover_title || post.title}
      </a>
      <TrialLine trial={post.trial} labels={labels} />
      <div className="flex flex-col gap-1 rounded-lg bg-surface-2 px-2.5 py-2 text-[11px]">
        {field ? (
          <p className="flex flex-wrap items-baseline gap-x-1.5">
            <span className="text-muted">狙った数字（{FIELD_INFO[field].label}）:</span>
            <MetricValue post={post} field={field} labels={labels} withUsual />
          </p>
        ) : (
          <dl className="grid grid-cols-3 gap-2">
            {(post.media_type === "VIDEO"
              ? (["reach", "saved_rate"] as const)
              : (["reach", "saved_rate", "pv_rate"] as const)
            ).map((f) => (
              <div key={f} className="flex flex-col">
                <dt className="text-[10px] text-muted">{FIELD_INFO[f].label}</dt>
                <dd>
                  <MetricValue post={post} field={f} labels={labels} />
                </dd>
              </div>
            ))}
          </dl>
        )}
        {verdict && (
          <p className="flex flex-wrap items-baseline gap-x-1.5">
            <Badge variant={DECISION_STYLE[verdict.decision] ?? "default"}>
              {labels.decisions[verdict.decision] ?? verdict.decision}
            </Badge>
            <span className="text-ink-2">{verdict.evidence}</span>
          </p>
        )}
      </div>
      <EditsLine edits={post.edits} />
    </Card>
  );
}

function TrialStats({ stats, labels }: { stats: TrialStat[]; labels: Labels }) {
  return (
    <div className="scroll-x">
      <table className="w-full min-w-[34rem] text-left text-[11px]">
        <thead className="text-muted">
          <tr className="border-b border-line">
            <th className="py-1.5 pr-2 font-medium">施策</th>
            <th className="px-2 py-1.5 font-medium">試した本数</th>
            <th className="px-2 py-1.5 font-medium">狙った数字（中央値）</th>
            <th className="px-2 py-1.5 font-medium">いつもとの比較</th>
            <th className="py-1.5 pl-2 font-medium">判定</th>
          </tr>
        </thead>
        <tbody>
          {stats.map((t) => {
            const field = labels.metric_fields[t.metric];
            const isRate = field ? FIELD_INFO[field].isRate : false;
            const fmt = (v: number | null) => (isRate ? fmtPct(v) : fmtInt(v));
            return (
              <tr key={t.tag} className="border-b border-line align-top last:border-0">
                <td className="py-1.5 pr-2">
                  <span className="font-medium text-ink">{t.what}</span>
                  <span className="block text-muted">{labels.levers[t.lever] ?? t.lever}</span>
                </td>
                <td className="tnum px-2 py-1.5 text-ink-2">
                  {t.count}本（判定済み{t.judged}本）
                </td>
                <td className="tnum px-2 py-1.5 text-ink-2">
                  {labels.metrics[t.metric] ?? t.metric}: {fmt(t.median_with)}
                  <span className="block text-muted">試さなかった投稿 {fmt(t.median_without)}</span>
                </td>
                <td className="tnum px-2 py-1.5 text-ink-2">
                  {labels.verdicts.high} {t.high}・{labels.verdicts.usual} {t.usual}・{labels.verdicts.low} {t.low}
                </td>
                <td className="py-1.5 pl-2">
                  {t.decision ? (
                    <Badge variant={DECISION_STYLE[t.decision] ?? "default"}>{labels.decisions[t.decision]}</Badge>
                  ) : (
                    <span className="text-muted">まだ</span>
                  )}
                  {t.again > 0 && <span className="block text-muted">もう一度 {t.again}回</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function EditSummary({ edits }: { edits: EditStats }) {
  return (
    <p className="text-xs leading-relaxed text-ink-2">
      直近{edits.weeks}週の枠 {edits.slots}本のうち、<span className="font-semibold text-ink">{edits.edited}本</span>
      に自動作成のあとの修正が入りました
      {edits.known < edits.slots && <span className="text-muted">（記録が無い枠 {edits.slots - edits.known}本）</span>}。
      {edits.top_changes.length > 0 && (
        <>
          {" "}
          よく直された箇所: {edits.top_changes.map((c) => `${c.label} ${c.count}回`).join("・")}
        </>
      )}
    </p>
  );
}

/** ② 振り返り: 試したこと → 結果 → 判定、いまの標準、人の修正 */
export function Review({
  judged,
  judgedWeek,
  matureDays,
  review,
  stats,
  edits,
  labels,
}: {
  judged: Post[];
  judgedWeek: string | null;
  matureDays: number;
  review: ReviewView;
  stats: TrialStat[];
  edits: EditStats;
  labels: Labels;
}) {
  const latest = review.latest;
  const standards = latest?.standards ?? [];
  const stopped = latest?.stopped ?? [];
  return (
    <section aria-labelledby="review-title" id="review" className="flex flex-col gap-6">
      <SectionHeader
        id="review-title"
        index="02"
        title="振り返り"
        desc={`試したこと → 結果 → 判定。判定は投稿から${matureDays}日たってから行います（それまでは数字が伸びている途中のため）。`}
      />

      <div>
        <SubHeading note={judgedWeek ? `${fmtWeek(judgedWeek)} の投稿` : undefined}>先週の投稿の結果</SubHeading>
        {judged.length ? (
          <div className="grid gap-2.5 md:grid-cols-3">
            {judged.map((p) => (
              <JudgedPost key={p.media_id} post={p} review={review} labels={labels} />
            ))}
          </div>
        ) : (
          <Empty>判定できる投稿がありません。</Empty>
        )}
      </div>

      <div>
        <SubHeading note="同じ施策を何回試して、どうだったか">施策の通算</SubHeading>
        {stats.length ? (
          <Card className="p-3">
            <TrialStats stats={stats} labels={labels} />
          </Card>
        ) : (
          <Empty>まだ試した施策がありません。次の週次更新から、投稿1本につき1つ試します。</Empty>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <SubHeading note="毎回入れる型">いまの標準</SubHeading>
          {standards.length ? (
            <ul className="flex flex-col gap-1.5">
              {standards.map((s) => (
                <li key={s.tag} className="flex flex-wrap items-baseline gap-1.5 text-xs text-ink-2">
                  <Badge variant={s.source === "edits" ? "accent" : "default"}>
                    {labels.standard_sources[s.source ?? ""] ?? s.source ?? "標準"}
                  </Badge>
                  <span className="text-ink">{s.what}</span>
                  {s.source === "edits" && s.based_on?.length ? (
                    <span className="text-[11px] text-muted">
                      （{s.based_on.map((b) => fmtDateShort(b)).join("・")}の修正から）
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <Empty>まだありません。</Empty>
          )}
        </div>
        <div>
          <SubHeading note="もう提案しないこと">やめたこと</SubHeading>
          {stopped.length ? (
            <ul className="flex flex-col gap-1 text-xs text-ink-2">
              {stopped.map((s) => (
                <li key={s.tag}>
                  {s.what ?? s.tag}
                  {s.since && <span className="text-[11px] text-muted">（{fmtDateShort(s.since)}〜）</span>}
                </li>
              ))}
            </ul>
          ) : (
            <Empty>まだありません。</Empty>
          )}
        </div>
      </div>

      <div>
        <SubHeading>人の修正</SubHeading>
        <Card className="p-3.5">
          <EditSummary edits={edits} />
          <p className="mt-1.5 text-[11px] leading-relaxed text-muted">
            同じ種類の修正が2本以上あったら（または「今後も」と依頼があったら）、作り方の標準に取り入れます。修正依頼の文はこのページには載せません。
          </p>
        </Card>
      </div>

      {review.history.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer text-xs font-medium text-ink-2 hover:text-ink">
            これまでの振り返り（{review.history.length}件）
          </summary>
          <ul className="mt-2 flex flex-col gap-2">
            {review.history.map((h) => (
              <li key={h.written_on} className="text-xs leading-relaxed text-ink-2">
                <span className="tnum mr-1.5 text-muted">{fmtDateShort(h.written_on)}</span>
                {h.summary}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
