import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { TraceDetail } from "../api/types";
import Markdown from "../components/Markdown";
import TraceSteps from "../components/TraceSteps";
import { confidenceScore, formatDate, formatMs } from "../utils/format";

export default function TraceDetailPage() {
  const { traceId } = useParams();
  const [trace, setTrace] = useState<TraceDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!traceId) return;
    api
      .getTrace(traceId)
      .then(setTrace)
      .catch((err) => setError(err instanceof Error ? err.message : "Not found"));
  }, [traceId]);

  if (error) {
    return (
      <div className="page">
        <p className="dim">{error}</p>
      </div>
    );
  }
  if (!trace) {
    return (
      <div className="page">
        <div className="status-line">
          <span className="spinner" /> Loading trace…
        </div>
      </div>
    );
  }

  const score = confidenceScore(trace.confidence);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <Link to="/traces" className="faint" style={{ fontSize: 12 }}>
            ← Traces
          </Link>
          <h1 style={{ fontSize: 18 }}>{trace.query}</h1>
          <p className="subtitle">
            {trace.mode} · {trace.strategy} · {trace.provider}/{trace.model} · {formatMs(trace.latency_ms)} ·{" "}
            {formatDate(trace.created_at)}
          </p>
        </div>
        {trace.abstained && <span className="badge yellow">abstained</span>}
      </div>

      <div className="stats-grid" style={{ marginBottom: 22 }}>
        <div className="stat-tile">
          <div className="label">Confidence</div>
          <div className="value">{score == null ? "—" : `${Math.round(score * 100)}%`}</div>
        </div>
        <div className="stat-tile">
          <div className="label">Tokens in/out</div>
          <div className="value">
            {trace.usage.prompt_tokens ?? 0}/{trace.usage.completion_tokens ?? 0}
          </div>
        </div>
        <div className="stat-tile">
          <div className="label">Est. cost</div>
          <div className="value">${(trace.usage.estimated_cost_usd ?? 0).toFixed(4)}</div>
        </div>
        <div className="stat-tile">
          <div className="label">Retrieved</div>
          <div className="value">{trace.retrieved.length}</div>
        </div>
      </div>

      {!!Object.keys(trace.query_analysis || {}).length && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h3 style={{ marginBottom: 8 }}>Query analysis</h3>
          <pre className="payload" style={{ margin: 0 }}>
            {JSON.stringify(trace.query_analysis, null, 2)}
          </pre>
        </div>
      )}

      <h3 style={{ marginBottom: 10 }}>Pipeline</h3>
      <TraceSteps steps={trace.steps} />

      {trace.retrieved.length > 0 && (
        <>
          <h3 style={{ margin: "22px 0 10px" }}>Retrieved candidates</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {trace.retrieved.slice(0, 20).map((item, index) => (
              <div key={index} className="evidence-card">
                <div className="src">
                  {(item.document_name as string) || (item.chunk_id as string) || `#${index + 1}`}
                  {item.page != null && <span className="faint">p.{String(item.page)}</span>}
                </div>
                <div className="snippet">{String(item.content ?? item.snippet ?? "").slice(0, 360)}</div>
              </div>
            ))}
          </div>
        </>
      )}

      {trace.answer && (
        <div className="card" style={{ marginTop: 22 }}>
          <h3 style={{ marginBottom: 8 }}>Answer</h3>
          <Markdown text={trace.answer} />
        </div>
      )}
    </div>
  );
}
