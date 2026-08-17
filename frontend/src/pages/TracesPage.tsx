import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { TraceSummary } from "../api/types";
import EmptyState from "../components/EmptyState";
import { confidenceScore, formatDate, formatMs } from "../utils/format";

export default function TracesPage() {
  const [traces, setTraces] = useState<TraceSummary[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .listTraces(80)
      .then(setTraces)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load traces"));
  }, []);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Traces</h1>
          <p className="subtitle">Structured pipeline events — no private chain-of-thought.</p>
        </div>
      </div>
      {error && <div className="abstained-banner">{error}</div>}
      {traces && !traces.length && (
        <EmptyState icon="🔍" title="No traces">
          <p>Every chat turn records query analysis, retrieval, verification, and confidence here.</p>
        </EmptyState>
      )}
      {traces && traces.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>Query</th>
              <th>Mode</th>
              <th>Strategy</th>
              <th>Model</th>
              <th>Confidence</th>
              <th>Latency</th>
              <th>When</th>
            </tr>
          </thead>
          <tbody>
            {traces.map((t) => {
              const score = confidenceScore(t.confidence);
              return (
                <tr key={t.id}>
                  <td>
                    <Link to={`/traces/${t.id}`}>{t.query.slice(0, 90) || "(empty)"}</Link>
                    {t.abstained && (
                      <span className="badge yellow" style={{ marginLeft: 8 }}>
                        abstained
                      </span>
                    )}
                  </td>
                  <td>{t.mode}</td>
                  <td className="mono">{t.strategy}</td>
                  <td className="faint">
                    {t.provider}/{t.model.split("/").pop()}
                  </td>
                  <td>{score == null ? "—" : `${Math.round(score * 100)}%`}</td>
                  <td>{formatMs(t.latency_ms)}</td>
                  <td className="faint">{formatDate(t.created_at)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
