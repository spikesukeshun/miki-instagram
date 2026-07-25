import type { ReactNode } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  ListOrdered,
  MessageSquareText,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import type { Finding, WeeklyAnalysis } from "../lib/insights";
import { Badge, Card, CardContent, CardHeader, CardTitle, SectionHeader, cn } from "./ui";
import { FadeIn } from "./Motion";

function FindingList({ items, empty }: { items: Finding[]; empty: string }) {
  if (!items.length) return <p className="text-xs text-muted">{empty}</p>;
  return (
    <ul className="flex flex-col gap-3">
      {items.map((f, i) => (
        <li key={i} className="text-xs leading-relaxed">
          <p className="font-medium text-ink">{f.title}</p>
          <p className="mt-0.5 text-ink-2">{f.detail}</p>
          <p className="mt-1 flex gap-1 text-[11px] text-muted">
            <HelpCircle className="mt-0.5 size-3 shrink-0 text-accent" aria-hidden />
            <span>
              <span className="font-medium text-accent-strong">なぜ: </span>
              {f.why}
            </span>
          </p>
        </li>
      ))}
    </ul>
  );
}

function Panel({
  icon,
  title,
  tone,
  children,
}: {
  icon: ReactNode;
  title: string;
  tone?: "good" | "bad";
  children: ReactNode;
}) {
  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle
          className={cn(
            "flex items-center gap-1.5",
            tone === "good" && "text-good",
            tone === "bad" && "text-serious",
          )}
        >
          {icon}
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

const GRADE_DESC: Record<WeeklyAnalysis["grade"], string> = {
  S: "非常に良い",
  A: "良い",
  B: "標準",
  C: "要改善",
  D: "立て直し",
  "—": "評価不能",
};

/** ⑦ AI分析（総合評価・良かった点・改善点・要因・優先順位、すべて根拠つき） */
export function AiAnalysis({
  analysis,
  claudeComment,
  rangeLabel,
}: {
  analysis: WeeklyAnalysis;
  claudeComment: string | null;
  rangeLabel: string;
}) {
  return (
    <section id="ai" aria-labelledby="ai-title">
      <SectionHeader
        index="07"
        title="AI分析"
        desc={`${rangeLabel}のデータから自動生成した分析。各判断には「なぜそう判断したか」の根拠を添えています。`}
      />
      <FadeIn>
        <Card className="mb-3 border-l-2 border-l-[var(--accent)]">
          <CardContent className="flex flex-col gap-3 pt-4 sm:flex-row sm:items-center">
            <div className="flex items-center gap-3">
              <span
                aria-label={`総合評価 ${analysis.grade}`}
                className="grid size-14 shrink-0 place-items-center rounded-xl bg-[var(--accent-dim)] font-serif text-3xl font-semibold text-accent-strong"
              >
                {analysis.grade}
              </span>
              <div className="sm:hidden">
                <Badge variant="accent">{GRADE_DESC[analysis.grade]}</Badge>
              </div>
            </div>
            <div className="min-w-0">
              <div className="mb-1 hidden sm:block">
                <Badge variant="accent">総合評価: {GRADE_DESC[analysis.grade]}</Badge>
              </div>
              <p className="text-[13px] leading-relaxed text-ink">{analysis.summary}</p>
            </div>
          </CardContent>
        </Card>

        {claudeComment && (
          <Card className="mb-3">
            <CardHeader>
              <CardTitle className="flex items-center gap-1.5 text-accent-strong">
                <MessageSquareText className="size-4" aria-hidden />
                Claudeの所見（今週の更新時に記入）
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="whitespace-pre-wrap text-xs leading-relaxed text-ink-2">{claudeComment}</p>
            </CardContent>
          </Card>
        )}

        <div className="grid gap-3 md:grid-cols-2">
          <Panel icon={<CheckCircle2 className="size-4" aria-hidden />} title="良かった点" tone="good">
            <FindingList items={analysis.good} empty="前期間より10%以上改善した主要指標はありませんでした。" />
          </Panel>
          <Panel icon={<AlertTriangle className="size-4" aria-hidden />} title="改善点" tone="bad">
            <FindingList items={analysis.improve} empty="前期間より10%以上悪化した主要指標はありませんでした。" />
          </Panel>
          <Panel icon={<Sparkles className="size-4" aria-hidden />} title="数値変化の原因分析">
            <FindingList items={analysis.causes} empty="比較できる前期間データがまだ揃っていません。" />
          </Panel>
          <Panel icon={<ListOrdered className="size-4" aria-hidden />} title="改善優先順位">
            <FindingList items={analysis.priorities} empty="優先すべき弱点は検出されませんでした。" />
          </Panel>
          <Panel icon={<ThumbsUp className="size-4" aria-hidden />} title="成功要因" tone="good">
            <FindingList items={analysis.successFactors} empty="成功要因を特定できるだけのデータがありません。" />
          </Panel>
          <Panel icon={<ThumbsDown className="size-4" aria-hidden />} title="失敗要因" tone="bad">
            <FindingList items={analysis.failureFactors} empty="明確な失敗要因は検出されませんでした。" />
          </Panel>
        </div>
      </FadeIn>
    </section>
  );
}
