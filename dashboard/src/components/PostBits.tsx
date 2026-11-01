import { PenLine, TriangleAlert } from "lucide-react";
import type { Edits, Labels, MetricField, Post, Trial } from "../types";
import { fmtInt, fmtPct, fmtUsual } from "../lib/format";
import { VerdictTag } from "./ui";

/** 投稿の数字の表示名と、率かどうか */
export const FIELD_INFO: Record<MetricField, { label: string; isRate: boolean }> = {
  reach: { label: "届いた人", isRate: false },
  saved: { label: "保存", isRate: false },
  saved_rate: { label: "保存率", isRate: true },
  profile_visits: { label: "プロフィール", isRate: false },
  pv_rate: { label: "プロフィール率", isRate: true },
  follows: { label: "フォロー", isRate: false },
};

/** 施策が入っている trial か（lever=none は「施策なし」） */
const isRealTrial = (t: Trial | null | undefined): boolean => !!t && !!t.lever && t.lever !== "none";

/** 「試すこと」の1行。記録なし／施策なし／施策ありの3通り */
export function TrialLine({
  trial,
  labels,
  detail = false,
}: {
  trial: Trial | null | undefined;
  labels: Labels;
  /** 根拠と反映した箇所も出す（今週の投稿のカード用） */
  detail?: boolean;
}) {
  if (!trial) {
    return <p className="text-[11px] text-muted">試すこと: 記録なし（この仕組みの前に作った投稿）</p>;
  }
  if (!isRealTrial(trial)) {
    return <p className="text-[11px] text-ink-2">試すこと: なし{trial.why ? `（${trial.why}）` : ""}</p>;
  }
  return (
    <div className="flex flex-col gap-0.5 text-[11px] leading-relaxed text-ink-2">
      <p>
        <span className="text-muted">試すこと: </span>
        <span className="font-medium text-ink">{labels.levers[trial.lever] ?? trial.lever}</span>｜{trial.what}
        <span className="text-muted">（狙い: {labels.metrics[trial.metric ?? ""] ?? trial.metric}）</span>
      </p>
      {detail && trial.why && (
        <p>
          <span className="text-muted">根拠: </span>
          {trial.why}
        </p>
      )}
      {detail && trial.where && (
        <p>
          <span className="text-muted">反映した箇所: </span>
          {trial.where}
        </p>
      )}
    </div>
  );
}

/** 修正の記録の1行。直接編集の疑いは別に警告する */
export function EditsLine({ edits }: { edits: Edits | null | undefined }) {
  if (!edits) return null;
  const direct =
    edits.direct === "app"
      ? "投稿後にキャプションが書き換えられています（アプリでの編集など）"
      : edits.direct === "sheet"
        ? "シートの文が、最後に校閲を通った版と違います（シートでの直接編集か、校閲前の作り直し）"
        : null;
  return (
    <div className="flex flex-col gap-0.5 text-[11px] leading-relaxed">
      {edits.count > 0 ? (
        <p className="flex items-start gap-1 text-ink-2">
          <PenLine className="mt-0.5 size-3 shrink-0 text-accent" aria-hidden />
          <span>
            自動作成のあとに修正 {edits.count}回（{edits.changes.join("・")}）
          </span>
        </p>
      ) : (
        <p className="text-muted">{edits.base_origin === "weekly" ? "自動作成のまま（修正なし）" : "修正の記録なし"}</p>
      )}
      {direct && (
        <p className="flex items-start gap-1 text-warn">
          <TriangleAlert className="mt-0.5 size-3 shrink-0" aria-hidden />
          <span>{direct}</span>
        </p>
      )}
    </div>
  );
}

/** 投稿の数字1つ（値・いつもの範囲・比較） */
export function MetricValue({
  post,
  field,
  labels,
  withUsual = false,
}: {
  post: Post;
  field: MetricField;
  labels: Labels;
  withUsual?: boolean;
}) {
  const info = FIELD_INFO[field];
  const v = post.metrics[field];
  const shown = info.isRate ? fmtPct(v) : fmtInt(v);
  return (
    <span className="inline-flex flex-wrap items-baseline gap-x-1">
      <span className="tnum font-medium text-ink">{shown}</span>
      <VerdictTag verdict={post.vs[field] ?? null} labels={labels.verdicts} />
      {withUsual && <span className="tnum text-[10px] text-muted">{fmtUsual(post.usual[field], info.isRate)}</span>}
    </span>
  );
}

/** 試したことで狙った数字（無ければ null） */
export function targetField(trial: Trial | null | undefined, labels: Labels): MetricField | null {
  if (!trial || !isRealTrial(trial) || !trial.metric) return null;
  return labels.metric_fields[trial.metric] ?? null;
}
