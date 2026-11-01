import { ExternalLink } from "lucide-react";
import type { Labels, Review, Upcoming as UpcomingPost } from "../types";
import { fmtSlot } from "../lib/format";
import { Badge, Card, Empty, SectionHeader, SubHeading } from "./ui";
import { EditsLine, TrialLine } from "./PostBits";

const STATUS_VARIANT: Record<string, "accent" | "default" | "outline"> = {
  承認済み: "accent",
  確認待ち: "outline",
};

/** ③ 今週の投稿と狙い: 前回の結果から決めた「次に試すこと」と、それを入れた予定の投稿 */
export function Upcoming({
  posts,
  review,
  labels,
  sheetError,
}: {
  posts: UpcomingPost[];
  review: Review | null;
  labels: Labels;
  sheetError: string | null;
}) {
  const next = review?.next ?? [];
  return (
    <section aria-labelledby="upcoming-title" id="upcoming" className="flex flex-col gap-4">
      <SectionHeader
        id="upcoming-title"
        index="03"
        title="今週の投稿と狙い"
        desc="振り返りで決めた「次に試すこと」と、それを入れた予定の投稿です。ご本人の修正が入った後の、最新の内容で表示しています。"
      />

      <div>
        <SubHeading note={review ? `${review.written_on.slice(5).replace("-", "/")}の振り返りで決めたこと` : undefined}>
          次に試すこと
        </SubHeading>
        {next.length ? (
          <ul className="grid gap-2 md:grid-cols-3">
            {next.map((n) => (
              <li key={n.tag}>
                <Card className="h-full p-3 text-xs leading-relaxed">
                  <p className="font-medium text-ink">{n.what}</p>
                  <p className="mt-0.5 text-[11px] text-muted">
                    {labels.levers[n.lever] ?? n.lever}・狙い: {labels.metrics[n.metric] ?? n.metric}
                  </p>
                  <p className="mt-1 text-[11px] text-ink-2">
                    <span className="text-muted">根拠: </span>
                    {n.why}
                  </p>
                </Card>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>まだありません（振り返りが作られると、ここに出ます）。</Empty>
        )}
      </div>

      <div>
        <SubHeading note="シートでまだ投稿されていない枠">予定の投稿</SubHeading>
        {sheetError && <p className="mb-2 text-[11px] text-warn">⚠ {sheetError}</p>}
        {posts.length ? (
          <div className="grid gap-2.5 md:grid-cols-3">
            {posts.map((p) => (
              <Card key={p.slug} className="flex flex-col gap-2 p-3.5">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="tnum text-xs font-medium text-ink-2">{fmtSlot(p.post_datetime, p.weekday)}</span>
                  <Badge variant={STATUS_VARIANT[p.status] ?? "default"}>{p.status}</Badge>
                  {p.menu && <Badge>{p.menu}</Badge>}
                </div>
                <p className="text-[13px] font-medium leading-snug text-ink">{p.cover_title || "（表紙の記録なし）"}</p>
                <TrialLine trial={p.trial} labels={labels} detail />
                <EditsLine edits={p.edits} />
                {p.preview_url && (
                  <a
                    href={p.preview_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-auto inline-flex items-center gap-1 text-[11px] text-accent-strong hover:underline"
                  >
                    プレビューを開く
                    <ExternalLink className="size-3" aria-hidden />
                  </a>
                )}
              </Card>
            ))}
          </div>
        ) : (
          <Empty>予定の投稿はシートにありません。</Empty>
        )}
      </div>
    </section>
  );
}
