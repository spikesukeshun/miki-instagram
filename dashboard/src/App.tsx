import { useEffect, useState } from "react";
import { Instagram, RefreshCw } from "lucide-react";
import { dashboardData } from "./data/embedded";
import { fmtInt } from "./lib/format";
import { cn, Empty } from "./components/ui";
import { Summary } from "./components/Summary";
import { Review } from "./components/Review";
import { Upcoming } from "./components/Upcoming";
import { LpSection } from "./components/LpSection";
import { PostTable } from "./components/PostTable";

const NAV = [
  { id: "summary", label: "01 まとめ" },
  { id: "review", label: "02 振り返り" },
  { id: "upcoming", label: "03 今週の投稿" },
  { id: "lp", label: "04 LP" },
  { id: "posts", label: "05 投稿の成績" },
];

export default function App() {
  const [activeSection, setActiveSection] = useState("summary");
  const d = dashboardData.derived;

  // スクロール位置に応じたナビのハイライト（ヘッダーの下を通り過ぎた最後のセクション）
  useEffect(() => {
    const onScroll = () => {
      let current = NAV[0].id;
      for (const n of NAV) {
        const el = document.getElementById(n.id);
        if (el && el.getBoundingClientRect().top <= 120) current = n.id;
      }
      setActiveSection(current);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const fetchedAt = dashboardData.fetched_at.slice(0, 16).replace("T", " ");
  const summary = d?.summary;

  return (
    <div className="min-h-screen bg-bg text-ink">
      {/* ヘッダー */}
      <header className="sticky top-0 z-40 border-b border-line bg-[color-mix(in_oklab,var(--bg)_88%,transparent)] backdrop-blur">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="flex items-center justify-between gap-3 pt-3">
            <div className="flex items-baseline gap-2.5">
              <h1 className="font-serif text-lg font-semibold tracking-[0.12em] text-ink sm:text-xl">MIKI</h1>
              <span className="text-[11px] tracking-wide text-muted">Instagram 週次の振り返り</span>
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
                フォロワー {fmtInt(summary?.followers ?? dashboardData.account.followers_count)}
                {summary?.followers_gain != null && `（${summary.followers_days}日で+${summary.followers_gain}）`}
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
                  activeSection === n.id ? "bg-[var(--accent-dim)] text-accent-strong" : "text-muted hover:text-ink-2",
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
        {d ? (
          <>
            <Summary summary={d.summary} review={d.review.latest} labels={d.labels} />
            <Review
              judged={d.judged}
              judgedWeek={d.judged_week}
              matureDays={d.mature_days}
              review={d.review}
              stats={d.trial_stats}
              edits={d.edits}
              labels={d.labels}
            />
            <Upcoming posts={d.upcoming} review={d.review.latest} labels={d.labels} sheetError={d.sheet_error} />
            <LpSection lp={d.lp} />
            <PostTable posts={d.posts} labels={d.labels} matureDays={d.mature_days} />
          </>
        ) : (
          <Empty>
            データが古い形式です。dashboard/fetch_dashboard_data.py を実行してから、もう一度ビルドしてください。
          </Empty>
        )}
      </main>

      {/* フッター */}
      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-col gap-1.5 px-4 py-5 text-[11px] leading-relaxed text-muted sm:px-6">
          <p className="flex items-center gap-1.5">
            <RefreshCw className="size-3" aria-hidden />
            データ最終更新: {fetchedAt}（JST）・毎週土曜の朝に自動で更新されます
          </p>
          <p>
            振り返りは週次更新のたびに Claude が書き、翌週の投稿はその「次に試すこと」を1本につき1つ入れて作られます。
            自動作成のあとの修正は、校閲（review_post.py）を通ったときに自動で記録されます。
          </p>
        </div>
      </footer>
    </div>
  );
}
