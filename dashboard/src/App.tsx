import { useEffect, useMemo, useState } from "react";
import { Instagram, RefreshCw } from "lucide-react";
import { dashboardData } from "./data/embedded";
import { RANGES, analyze, periodKpis, type RangeKey } from "./lib/analytics";
import { analyzeWeek } from "./lib/insights";
import { buildStrategy } from "./lib/strategy";
import { aggregateManual, useManualStore } from "./lib/manualStore";
import { fmtInt } from "./lib/format";
import { Segmented, cn } from "./components/ui";
import { KpiGrid } from "./components/KpiGrid";
import { TrendChart } from "./components/TrendChart";
import { PostRanking } from "./components/PostRanking";
import { ThemeRanking } from "./components/ThemeRanking";
import { Funnel } from "./components/Funnel";
import { Heatmap } from "./components/Heatmap";
import { AiAnalysis } from "./components/AiAnalysis";
import { NextWeek } from "./components/NextWeek";
import { PostReports } from "./components/PostReports";

const NAV = [
  { id: "kpi", label: "01 KPI" },
  { id: "trend", label: "02 推移" },
  { id: "ranking", label: "03 投稿" },
  { id: "themes", label: "04 テーマ" },
  { id: "funnel", label: "05 ファネル" },
  { id: "heatmap", label: "06 時間帯" },
  { id: "ai", label: "07 AI分析" },
  { id: "nextweek", label: "08 来週" },
  { id: "reports", label: "09 カルテ" },
];

export default function App() {
  const [range, setRange] = useState<RangeKey>("this");
  const [activeSection, setActiveSection] = useState("kpi");

  const analyzed = useMemo(() => analyze(dashboardData), []);
  const cmp = useMemo(
    () => periodKpis(analyzed.weeks, range, analyzed.currentWeekStart),
    [analyzed, range],
  );
  const rangeLabel = RANGES.find((r) => r.key === range)?.label ?? "今週";

  const periodPosts = useMemo(() => {
    const weeks = new Set(cmp.current?.weekStarts ?? []);
    return analyzed.posts.filter((p) => weeks.has(p.weekStart));
  }, [analyzed, cmp]);

  const analysis = useMemo(
    () => analyzeWeek(cmp, periodPosts, analyzed.themes),
    [cmp, periodPosts, analyzed],
  );
  const strategy = useMemo(
    () => buildStrategy(analyzed.themes, analyzed.heatmap, analyzed.insightPosts),
    [analyzed],
  );

  const { store, updateWeek } = useManualStore();
  const weekStarts = cmp.current?.weekStarts ?? [];
  const manual = aggregateManual(store, weekStarts);
  const editable = weekStarts.length === 1;

  // スクロール位置に応じたナビのハイライト
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) setActiveSection(e.target.id);
        }
      },
      { rootMargin: "-100px 0px -60% 0px", threshold: 0 },
    );
    for (const n of NAV) {
      const el = document.getElementById(n.id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, []);

  const fetchedAt = dashboardData.fetched_at.slice(0, 16).replace("T", " ");

  return (
    <div className="min-h-screen bg-bg text-ink">
      {/* ヘッダー */}
      <header className="sticky top-0 z-40 border-b border-line bg-[color-mix(in_oklab,var(--bg)_88%,transparent)] backdrop-blur">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="flex items-center justify-between gap-3 pt-3">
            <div className="flex items-baseline gap-2.5">
              <h1 className="font-serif text-lg font-semibold tracking-[0.12em] text-ink sm:text-xl">
                MIKI
              </h1>
              <span className="hidden text-[11px] tracking-wide text-muted sm:inline">
                Instagram AI マーケティングダッシュボード
              </span>
              <span className="text-[11px] tracking-wide text-muted sm:hidden">AI運用ダッシュボード</span>
            </div>
            <div className="flex items-center gap-3 text-[11px] text-muted">
              <a
                href={`https://www.instagram.com/${dashboardData.account.username}/`}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1 hover:text-accent-strong"
              >
                <Instagram className="size-3.5" aria-hidden />@{dashboardData.account.username}
              </a>
              <span className="tnum hidden sm:inline">
                フォロワー {fmtInt(dashboardData.account.followers_count)}
              </span>
            </div>
          </div>
          <nav aria-label="セクション" className="scroll-x -mx-1 flex gap-1 py-2">
            {NAV.map((n) => (
              <a
                key={n.id}
                href={`#${n.id}`}
                aria-current={activeSection === n.id ? "true" : undefined}
                className={cn(
                  "tnum whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors",
                  activeSection === n.id
                    ? "bg-[var(--accent-dim)] text-accent-strong"
                    : "text-muted hover:text-ink-2",
                )}
              >
                {n.label}
              </a>
            ))}
          </nav>
        </div>
      </header>

      {/* 本文 */}
      <main className="mx-auto flex max-w-6xl flex-col gap-12 px-4 py-6 sm:px-6 sm:py-8">
        <KpiGrid
          cmp={cmp}
          rangeLabel={rangeLabel}
          right={
            <Segmented
              label="集計期間"
              options={RANGES.map((r) => ({ key: r.key, label: r.label }))}
              value={range}
              onChange={setRange}
            />
          }
        />
        <TrendChart weeks={analyzed.weeks} />
        <PostRanking insightPosts={analyzed.insightPosts} />
        <ThemeRanking themes={analyzed.themes} />
        <Funnel
          kpi={cmp.current}
          rangeLabel={rangeLabel}
          manual={manual}
          editable={editable}
          onManualChange={(patch) => weekStarts[0] && updateWeek(weekStarts[0], patch)}
        />
        <Heatmap heatmap={analyzed.heatmap} />
        <AiAnalysis
          analysis={analysis}
          claudeComment={dashboardData.claude_comment}
          rangeLabel={rangeLabel}
        />
        <NextWeek strategy={strategy} />
        <PostReports insightPosts={analyzed.insightPosts} />
      </main>

      {/* フッター */}
      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-col gap-1.5 px-4 py-5 text-[11px] leading-relaxed text-muted sm:px-6">
          <p className="flex items-center gap-1.5">
            <RefreshCw className="size-3" aria-hidden />
            データ最終更新: {fetchedAt}（JST）・投稿{fmtInt(dashboardData.account.media_count)}件中、
            2025年1月以降のインサイトを分析対象としています
          </p>
          <p>
            毎週の更新はClaude Codeに「ダッシュボードを更新して」と依頼（データ再取得 → 再ビルド → 同じURLに再公開）。
            DM・予約数のみ手入力で、この端末のブラウザに保存されます。
          </p>
        </div>
      </footer>
    </div>
  );
}
