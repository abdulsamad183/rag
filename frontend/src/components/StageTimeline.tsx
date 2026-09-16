export const STAGE_ORDER = [
  "analyzing",
  "retrieving",
  "searching_web",
  "reranking",
  "generating",
  "verifying",
  "correcting",
] as const;

export type PipelineStage = (typeof STAGE_ORDER)[number];

export const STAGE_LABEL: Record<string, string> = {
  analyzing: "Understanding the question…",
  retrieving: "Retrieving evidence…",
  searching_web: "Searching the web…",
  reranking: "Reranking candidates…",
  generating: "Writing an answer…",
  verifying: "Verifying claims…",
  correcting: "Retrieving more evidence…",
};

const SHORT_LABEL: Record<string, string> = {
  analyzing: "Analyze",
  retrieving: "Retrieve",
  searching_web: "Web",
  reranking: "Rerank",
  generating: "Generate",
  verifying: "Verify",
  correcting: "Correct",
};

export type StageState = "pending" | "active" | "done" | "skipped";

/** Advance timeline when a new status SSE arrives. Unused stages stay skipped. */
export function advanceStages(
  seen: string[],
  next: string,
): { seen: string[]; states: Record<string, StageState> } {
  const ordered = STAGE_ORDER.filter((s) => seen.includes(s) || s === next);
  const updated = seen.includes(next) ? seen : [...seen, next];
  const states: Record<string, StageState> = {};
  for (const stage of STAGE_ORDER) {
    if (!ordered.includes(stage) && stage !== next) {
      // hide stages never reached unless they appear later; mark intervening skips
      const nextIdx = STAGE_ORDER.indexOf(next as PipelineStage);
      const stageIdx = STAGE_ORDER.indexOf(stage);
      if (nextIdx >= 0 && stageIdx >= 0 && stageIdx < nextIdx && !updated.includes(stage)) {
        states[stage] = "skipped";
      } else if (!updated.includes(stage)) {
        states[stage] = "pending";
      }
    }
  }
  for (const stage of updated) {
    states[stage] = stage === next ? "active" : "done";
  }
  return { seen: updated, states };
}

export function visibleStages(states: Record<string, StageState>): PipelineStage[] {
  return STAGE_ORDER.filter((s) => {
    const st = states[s];
    return st === "active" || st === "done" || st === "skipped";
  });
}

export default function StageTimeline({
  states,
  compact = false,
}: {
  states: Record<string, StageState>;
  compact?: boolean;
}) {
  const items = visibleStages(states);
  if (!items.length) return null;

  return (
    <ol className={`stage-timeline${compact ? " compact" : ""}`} aria-label="Pipeline stages">
      {items.map((stage, index) => {
        const state = states[stage] ?? "pending";
        return (
          <li key={stage} className={`stage-item ${state}`}>
            {index > 0 && <span className="stage-connector" aria-hidden />}
            <span className="stage-dot" aria-hidden />
            <span className="stage-label">
              {compact ? SHORT_LABEL[stage] ?? stage : STAGE_LABEL[stage] ?? stage}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
