import { useState } from "react";
import type { ChatResponse, Evidence } from "../api/types";
import { ConfidenceRing, ConfidenceSignals } from "./Confidence";

function EvidenceCard({ item, highlighted }: { item: Evidence; highlighted: boolean }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div
      id={`evidence-${item.marker}`}
      className={`evidence-card${highlighted ? " highlight" : ""}`}
    >
      <div className="src">
        <span className="citation-chip" style={{ cursor: "default" }}>
          {item.marker}
        </span>
        {item.source_type === "web" && <span className="badge accent">WEB</span>}
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {item.document_name}
        </span>
        {item.page != null && <span className="faint">p.{item.page}</span>}
      </div>
      {item.url && (
        <div className="faint" style={{ fontSize: 11, marginBottom: 5 }}>
          <a href={item.url} target="_blank" rel="noreferrer">
            {item.url}
          </a>
        </div>
      )}
      {item.section && (
        <div className="faint" style={{ fontSize: 11, marginBottom: 5 }}>
          {item.section}
        </div>
      )}
      <div className={`snippet${expanded ? " expanded" : ""}`}>{item.content}</div>
      <div className="row" style={{ marginTop: 8, gap: 8 }}>
        <div className="score-bar" title={`score ${item.score.toFixed(3)}`}>
          <div style={{ width: `${Math.min(100, item.score * 100)}%` }} />
        </div>
        <span className="faint mono" style={{ fontSize: 10.5 }}>
          {item.score.toFixed(2)}
        </span>
        <button className="btn ghost small" onClick={() => setExpanded(!expanded)}>
          {expanded ? "less" : "more"}
        </button>
      </div>
    </div>
  );
}

const VERDICT_BADGES: Record<string, { label: string; klass: string }> = {
  SUPPORTED: { label: "supported", klass: "green" },
  PARTIALLY_SUPPORTED: { label: "partial", klass: "yellow" },
  UNSUPPORTED: { label: "unsupported", klass: "yellow" },
  CONTRADICTED: { label: "contradicted", klass: "red" },
};

export default function EvidencePanel({
  response,
  highlightMarker,
}: {
  response: ChatResponse;
  highlightMarker: number | null;
}) {
  return (
    <div className="side-panel">
      <div className="row" style={{ gap: 14 }}>
        <ConfidenceRing confidence={response.confidence} />
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 13.5, textTransform: "capitalize" }}>
            {response.confidence.level} confidence
          </div>
          <div className="faint" style={{ fontSize: 12 }}>
            {response.strategy} · {response.provider}/{response.model.split("/").pop()} ·{" "}
            {(response.latency_ms / 1000).toFixed(1)}s
          </div>
        </div>
      </div>

      <ConfidenceSignals confidence={response.confidence} />

      {response.verification && response.verification.total > 0 && (
        <div>
          <h3>
            Claims · {response.verification.supported}/{response.verification.total} supported
          </h3>
          <div>
            {response.verification.claims.map((claim, index) => {
              const badge = VERDICT_BADGES[claim.verdict] ?? {
                label: claim.verdict.toLowerCase(),
                klass: "",
              };
              return (
                <div key={index} className="claim-row">
                  <span className={`badge ${badge.klass}`}>{badge.label}</span>
                  <span className="dim">{claim.text}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {response.queries_used.length > 1 && (
        <div>
          <h3>Queries used</h3>
          {response.queries_used.map((query, index) => (
            <div key={index} className="dim" style={{ fontSize: 12, padding: "3px 0" }}>
              · {query}
            </div>
          ))}
        </div>
      )}

      <div>
        <h3>Evidence · {response.evidence.length}</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 9, marginTop: 8 }}>
          {response.evidence.map((item) => (
            <EvidenceCard
              key={item.marker}
              item={item}
              highlighted={highlightMarker === item.marker}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
