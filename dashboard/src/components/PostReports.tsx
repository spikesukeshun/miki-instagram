import { ExternalLink } from "lucide-react";
import type { ScoredPost, ScorePart } from "../types";
import { ANALYSIS, themeDef } from "../config";
import { fmtInt, fmtPct } from "../lib/format";
import { Badge, Card, ScoreBar, SectionHeader, Stars, ThemeBadge } from "./ui";
import { FadeIn } from "./Motion";

/** 弱点メトリクス → 次回の具体的な改善方法 */
const ADVICE: Record<string, string> = {
  pvRate:
    "最終スライドとキャプション末尾に「プロフィールから」の一言を入れ、本文にMIKI個人の視点を1段落足す",
  saveRate:
    "「あとで見返す理由」を作る（手順・チェックリスト・料金早見のスライドを1枚入れる）",
  follows: "プロフィール導線を強化した上で、シリーズ化して「次も見たい」を作る",
  reach: "伸びているテーマ・切り口に寄せる。カバータイトルに検索されやすいキーワードを入れる",
  views: "カバー1枚目を数字入り・悩み言葉起点にして、2枚目への遷移率を上げる",
  comments: "最後に軽い問いかけ（どちら派ですか？等）を1つだけ入れる",
  likes: "共感で始まる書き出しにする（悩みの言葉→寄り添い→提案の順）",
  shares: "「誰かに教えたくなる」一般性のある豆知識を1枚入れる",
};

function weakParts(parts: ScorePart[]): ScorePart[] {
  return parts
    .filter((p) => p.percentile != null && p.stars >= 3)
    .sort((a, b) => b.stars - a.stars || (a.percentile ?? 0) - (b.percentile ?? 0))
    .filter((p) => (p.percentile ?? 1) < 0.45)
    .slice(0, 2);
}

function strongParts(parts: ScorePart[]): ScorePart[] {
  return parts
    .filter((p) => p.percentile != null && (p.percentile ?? 0) >= 0.7)
    .sort((a, b) => (b.percentile ?? 0) - (a.percentile ?? 0))
    .slice(0, 2);
}

const partValue = (p: ScorePart) => (p.isRate ? fmtPct(p.value) : fmtInt(p.value));

/** ⑨ 投稿改善レポート（直近投稿ごとのスコア・改善点・次回の改善方法） */
export function PostReports({ insightPosts }: { insightPosts: ScoredPost[] }) {
  const recent = insightPosts.slice(0, ANALYSIS.reportPosts);

  return (
    <section id="reports" aria-labelledby="reports-title">
      <SectionHeader
        index="09"
        title="投稿改善レポート"
        desc={`直近${recent.length}投稿の個別カルテ。スコアの内訳から弱い星の重い指標を特定し、次回の改善方法を提示します。`}
      />
      <div className="grid gap-3 md:grid-cols-2">
        {recent.map((p, i) => {
          const t = themeDef(p.theme);
          const weak = weakParts(p.parts);
          const strong = strongParts(p.parts);
          return (
            <FadeIn key={p.media_id} delay={Math.min(i * 0.03, 0.15)}>
              <Card className="flex h-full flex-col p-4">
                <div className="flex flex-wrap items-center gap-1.5">
                  <ThemeBadge cssVar={t.cssVar} label={t.short} />
                  <Badge variant="outline">
                    {p.date.toISOString().slice(0, 10).split("-").join("/")}
                  </Badge>
                  {p.media_type === "VIDEO" && <Badge variant="outline">リール</Badge>}
                  <Badge variant="outline">{p.slide_count}枚</Badge>
                </div>
                <p className="mt-2 line-clamp-2 text-[13px] font-medium leading-snug text-ink">
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
                <div className="mt-2.5">
                  <ScoreBar score={p.score} />
                </div>

                <dl className="mt-3 flex flex-1 flex-col gap-2.5 text-[11px] leading-relaxed">
                  {strong.length > 0 && (
                    <div>
                      <dt className="font-semibold text-good">強み</dt>
                      {strong.map((s) => (
                        <dd key={s.key} className="mt-0.5 flex items-center gap-1.5 text-ink-2">
                          <Stars n={s.stars} />
                          {s.label} {partValue(s)}（上位{Math.round((1 - (s.percentile ?? 0)) * 100)}%）
                        </dd>
                      ))}
                    </div>
                  )}
                  <div>
                    <dt className="font-semibold text-serious">改善点</dt>
                    {weak.length ? (
                      weak.map((w) => (
                        <dd key={w.key} className="mt-0.5 flex items-center gap-1.5 text-ink-2">
                          <Stars n={w.stars} />
                          {w.label} {partValue(w)}（下位{Math.round((w.percentile ?? 0) * 100)}%）
                        </dd>
                      ))
                    ) : (
                      <dd className="mt-0.5 text-ink-2">大きな弱点なし。この型を横展開する</dd>
                    )}
                  </div>
                  {weak.length > 0 && (
                    <div>
                      <dt className="font-semibold text-accent-strong">次回の改善方法</dt>
                      {weak.map((w) => (
                        <dd key={w.key} className="mt-0.5 text-ink-2">
                          ・{ADVICE[w.key] ?? "高スコア投稿の構成を踏襲する"}
                        </dd>
                      ))}
                    </div>
                  )}
                </dl>
              </Card>
            </FadeIn>
          );
        })}
      </div>
    </section>
  );
}
