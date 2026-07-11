import { ExternalLink } from "lucide-react";
import type { ScoredPost } from "../types";
import { ANALYSIS, themeDef } from "../config";
import { fmtInt, fmtPct } from "../lib/format";
import { Badge, Card, ScoreBar, SectionHeader, ThemeBadge } from "./ui";
import { FadeIn } from "./Motion";

/** ③ 投稿ランキング（AIスコア順） */
export function PostRanking({ insightPosts }: { insightPosts: ScoredPost[] }) {
  const ranked = [...insightPosts]
    .sort((a, b) => b.score - a.score)
    .slice(0, ANALYSIS.rankingPosts);

  return (
    <section id="ranking" aria-labelledby="ranking-title">
      <SectionHeader
        index="03"
        title="投稿ランキング"
        desc={`インサイトが取得できた直近${insightPosts.length}投稿をAIスコア順に表示。スコアは自アカウント内の相対評価（星重み×百分位）です。`}
      />
      <FadeIn>
        <Card className="divide-y divide-[var(--border)]">
          {ranked.map((p, i) => {
            const t = themeDef(p.theme);
            return (
              <article key={p.media_id} className="flex items-start gap-3 p-3.5 sm:items-center sm:p-4">
                <span
                  aria-label={`${i + 1}位`}
                  className="tnum mt-0.5 w-7 shrink-0 text-center font-serif text-lg text-accent sm:mt-0"
                >
                  {String(i + 1).padStart(2, "0")}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <ThemeBadge cssVar={t.cssVar} label={t.short} />
                    <Badge variant="outline">{p.date.toISOString().slice(0, 10).split("-").join("/")}</Badge>
                    {p.media_type === "VIDEO" && <Badge variant="outline">リール</Badge>}
                  </div>
                  <p className="mt-1 line-clamp-2 text-[13px] leading-snug text-ink">
                    <a
                      href={p.permalink}
                      target="_blank"
                      rel="noreferrer"
                      className="hover:text-accent-strong hover:underline"
                    >
                      {p.titleLine}
                      <ExternalLink className="mb-0.5 ml-1 inline size-3 text-muted" aria-hidden />
                    </a>
                  </p>
                  <p className="tnum mt-1 text-[11px] text-muted">
                    リーチ {fmtInt(p.insights?.reach)} ・ 保存率 {fmtPct(p.saveRate)} ・ 誘導率{" "}
                    {fmtPct(p.pvRate)} ・ いいね {fmtInt(p.insights?.likes)}
                  </p>
                </div>
                <div className="w-24 shrink-0 sm:w-36">
                  <ScoreBar score={p.score} />
                </div>
              </article>
            );
          })}
        </Card>
      </FadeIn>
    </section>
  );
}
