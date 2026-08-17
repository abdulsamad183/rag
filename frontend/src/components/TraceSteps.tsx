import type { TraceStep } from "../api/types";

const STEP_LABELS: Record<string, string> = {
  contextualize: "Contextualize follow-up",
  query_analysis: "Query analysis",
  route: "Strategy routing",
  rerank: "Reranking",
  evidence_builder: "Evidence building",
  generate: "Generation",
  claim_extraction: "Claim extraction",
  claim_verification: "Claim verification",
  self_correction: "Self-correction",
  contradiction_check: "Contradiction check",
  confidence: "Confidence scoring",
  abstention: "Abstention decision",
  provider_fallback: "Provider fallback",
};

function label(name: string): string {
  if (STEP_LABELS[name]) return STEP_LABELS[name];
  if (name.startsWith("retrieve.")) return `Retrieval · ${name.split(".")[1]}`;
  return name.replace(/_/g, " ");
}

export default function TraceSteps({ steps }: { steps: TraceStep[] }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {steps.map((step, index) => (
        <details key={index} className="trace-step">
          <summary>
            <span className={`step-dot ${step.status}`} />
            <span style={{ fontWeight: 500 }}>{label(step.name)}</span>
            {step.status === "skipped" && <span className="badge">skipped</span>}
            {step.status === "error" && <span className="badge red">error</span>}
            <span className="faint mono" style={{ marginLeft: "auto", fontSize: 11.5 }}>
              {step.latency_ms} ms
            </span>
          </summary>
          <div className="payload">{JSON.stringify(step.payload, null, 2)}</div>
        </details>
      ))}
    </div>
  );
}
