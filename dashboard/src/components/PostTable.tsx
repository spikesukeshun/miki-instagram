import { ExternalLink } from "lucide-react";
import type { Labels, Post } from "../types";
import { DELAY_NOTICE_MIN, themeDef } from "../config";
import { fmtDelay, fmtInt, fmtPct, fmtPostDate } from "../lib/format";
import { Badge, Card, Empty, SectionHeader, ThemeBadge, VerdictTag } from "./ui";

function Metric({ label, count, unit, rate, verdict, labels }: {
  label: string;
  count: number | null;
  unit: string;
  rate?: number | null;
  verdict: Post["vs"][keyof Post["vs"]];
  labels: Labels;
}) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] text-muted">{label}</span>
      <span className="tnum text-xs font-medium text-ink">
        {fmtInt(count)}
        {count != null && unit}
        {rate !== undefined && <span className="font-normal text-ink-2">（{fmtPct(rate)}）</span>}
      </span>
      <VerdictTag verdict={verdict ?? null} labels={labels.verdicts} className="text-[10px]" />
    </div>
  );
}

/** ⑤ 投稿の成績: 直近の投稿の数字と、試したこと・修正の有無（固定文の助言は出さない） */
export function PostTable({ posts, labels, matureDays }: { posts: Post[]; labels: Labels; matureDays: number }) {
  return (
    <section aria-labelledby="posts-title" id="posts">
      <SectionHeader
        id="posts-title"
        index="05"
        title="投稿の成績"
        desc={`直近${posts.length}本。投稿から${matureDays}日未満は「集計中」で、いつもとの比較はまだしません。保存とプロフィールは率で比べています。`}
      />
      {posts.length ? (
        <div className="flex flex-col gap-2">
          {posts.map((p) => {
            const theme = themeDef(p.theme);
            const trial = p.trial && p.trial.lever !== "none" ? p.trial : null;
            return (
              <Card key={p.media_id} className="grid gap-2 p-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
                <div className="flex min-w-0 flex-col gap-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="tnum text-xs font-medium text-ink-2">{fmtPostDate(p.date)}</span>
                    <ThemeBadge cssVar={theme.cssVar} label={theme.short} />
                    {p.media_type === "VIDEO" && <Badge variant="outline">リール</Badge>}
                    {p.mature ? (
                      <Badge>確定</Badge>
                    ) : (
                      <Badge variant="outline">集計中 {Math.max(1, Math.floor(p.age_days) + 1)}日目</Badge>
                    )}
                    {p.delay_min != null && p.delay_min > DELAY_NOTICE_MIN && (
                      <Badge variant="warn">{fmtDelay(p.delay_min)}</Badge>
                    )}
                  </div>
                  <a
                    href={p.permalink}
                    target="_blank"
                    rel="noreferrer"
                    className="truncate text-[13px] font-medium text-ink hover:text-accent-strong hover:underline"
                  >
                    {p.cover_title || p.title}
                    <ExternalLink className="mb-0.5 ml-1 inline size-3 text-muted" aria-hidden />
                  </a>
                  <p className="truncate text-[11px] text-muted">
                    {trial
                      ? `試したこと: ${labels.levers[trial.lever] ?? trial.lever}｜${trial.what}`
                      : p.trial
                        ? "試したこと: なし"
                        : "試したこと: 記録なし"}
                    {p.edits && p.edits.count > 0 && `　修正 ${p.edits.count}回（${p.edits.changes.slice(0, 3).join("・")}${p.edits.changes.length > 3 ? "ほか" : ""}）`}
                    {p.edits?.direct && "　⚠ 直接の書き換えあり"}
                  </p>
                </div>
                <div className="grid grid-cols-3 gap-3 sm:w-72">
                  <Metric label="届いた人" count={p.metrics.reach} unit="人" verdict={p.vs.reach} labels={labels} />
                  <Metric
                    label="保存"
                    count={p.metrics.saved}
                    unit="件"
                    rate={p.metrics.saved_rate}
                    verdict={p.vs.saved_rate}
                    labels={labels}
                  />
                  {p.media_type === "VIDEO" ? (
                    <div className="flex flex-col">
                      <span className="text-[10px] text-muted">プロフィール</span>
                      <span className="text-[11px] text-muted">リールは取得不可</span>
                    </div>
                  ) : (
                    <Metric
                      label="プロフィール"
                      count={p.metrics.profile_visits}
                      unit="人"
                      rate={p.metrics.pv_rate}
                      verdict={p.vs.pv_rate}
                      labels={labels}
                    />
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      ) : (
        <Empty>投稿のデータがありません。</Empty>
      )}
    </section>
  );
}
