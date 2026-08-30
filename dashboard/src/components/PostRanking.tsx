import { ChevronDown, ExternalLink } from "lucide-react";
import type { ScoredPost } from "../types";
import { ANALYSIS, themeDef } from "../config";
import { monthsAgoJst } from "../lib/analytics";
import { fmtInt, fmtPct } from "../lib/format";
import { Badge, Card, ScoreBar, SectionHeader, ThemeBadge } from "./ui";
import { FadeIn } from "./Motion";

/** ランキング1行。上位ぶんと折りたたみぶんで同じ見た目を使う */
function RankRow({ post, rank }: { post: ScoredPost; rank: number }) {
  const t = themeDef(post.theme);
  return (
    <article className="flex items-start gap-3 p-3.5 sm:items-center sm:p-4">
      <span
        aria-label={`${rank}位`}
        className="tnum mt-0.5 w-7 shrink-0 text-center font-serif text-lg text-accent sm:mt-0"
      >
        {String(rank).padStart(2, "0")}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <ThemeBadge cssVar={t.cssVar} label={t.short} />
          <Badge variant="outline">
            {post.date.toISOString().slice(0, 10).split("-").join("/")}
          </Badge>
          {post.media_type === "VIDEO" && <Badge variant="outline">リール</Badge>}
        </div>
        <p className="mt-1 line-clamp-2 text-[13px] leading-snug text-ink">
          <a
            href={post.permalink}
            target="_blank"
            rel="noreferrer"
            className="hover:text-accent-strong hover:underline"
          >
            {post.titleLine}
            <ExternalLink className="mb-0.5 ml-1 inline size-3 text-muted" aria-hidden />
          </a>
        </p>
        <p className="tnum mt-1 text-[11px] text-muted">
          リーチ {fmtInt(post.insights?.reach)} ・ 保存率 {fmtPct(post.saveRate)} ・ 誘導率{" "}
          {fmtPct(post.pvRate)} ・ いいね {fmtInt(post.insights?.likes)}
        </p>
      </div>
      <div className="w-24 shrink-0 sm:w-36">
        <ScoreBar score={post.score} />
      </div>
    </article>
  );
}

/** ③ 投稿ランキング（AIスコア順・直近 rankingWindowMonths ヶ月）
 *  上位 rankingVisible 件だけ出し、それ以降は <details> で畳む。
 *  単一HTMLビルドなので state ではなく <details>（印刷・ページ内検索でも開ける）。 */
export function PostRanking({ insightPosts }: { insightPosts: ScoredPost[] }) {
  const months = ANALYSIS.rankingWindowMonths;
  // 古い投稿がいつまでも上位に居座らないよう、直近◯ヶ月の投稿だけを対象にする
  const cutoff = monthsAgoJst(months);
  const target = insightPosts.filter((p) => p.date >= cutoff);
  const ranked = [...target].sort((a, b) => b.score - a.score).slice(0, ANALYSIS.rankingPosts);
  const head = ranked.slice(0, ANALYSIS.rankingVisible);
  const rest = ranked.slice(ANALYSIS.rankingVisible);

  return (
    <section id="ranking" aria-labelledby="ranking-title">
      <SectionHeader
        index="03"
        title="投稿ランキング"
        desc={`直近${months}ヶ月でインサイトが取得できた${target.length}投稿をAIスコア順に表示。スコアは自アカウント内の相対評価（星重み×百分位）です。`}
      />
      <FadeIn>
        {ranked.length ? (
          <Card className="divide-y divide-[var(--border)]">
            {head.map((p, i) => (
              <RankRow key={p.media_id} post={p} rank={i + 1} />
            ))}
            {rest.length > 0 && (
              <details className="group">
                <summary className="flex cursor-pointer list-none items-center justify-center gap-1.5 p-3 text-[12px] font-medium text-muted transition-colors hover:text-accent-strong [&::-webkit-details-marker]:hidden">
                  <ChevronDown
                    className="size-3.5 transition-transform group-open:rotate-180"
                    aria-hidden
                  />
                  <span className="group-open:hidden">
                    {head.length + 1}位〜{ranked.length}位を表示
                  </span>
                  <span className="hidden group-open:inline">閉じる</span>
                </summary>
                <div className="divide-y divide-[var(--border)] border-t border-[var(--border)]">
                  {rest.map((p, i) => (
                    <RankRow key={p.media_id} post={p} rank={head.length + i + 1} />
                  ))}
                </div>
              </details>
            )}
          </Card>
        ) : (
          <Card className="p-4 text-xs text-muted">
            直近{months}ヶ月にインサイトを取得できた投稿がありません。
          </Card>
        )}
      </FadeIn>
    </section>
  );
}
