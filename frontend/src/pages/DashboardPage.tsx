import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { HealthReport, TraceSummary } from "../api/types";
import EmptyState from "../components/EmptyState";
import { useApp } from "../state/AppContext";
import { confidenceScore, formatDate, formatMs } from "../utils/format";

export default function DashboardPage() {
  const { collections, providers, backendDown, config } = useApp();
  const [health, setHealth] = useState<HealthReport | null>(null);
  const [traces, setTraces] = useState<TraceSummary[]>([]);

  useEffect(() => {
    api.ready().then(setHealth).catch(() => setHealth(null));
    api.listTraces(8).then(setTraces).catch(() => setTraces([]));
  }, []);

  const docs = collections.reduce((n, c) => n + c.document_count, 0);
  const chunks = collections.reduce((n, c) => n + c.chunk_count, 0);
  const configured = providers.filter((p) => p.configured).length;

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p className="subtitle">
            Adaptive Evidence-Driven RAG Engine — retrieval quality, grounding, and auditable answers.
          </p>
        </div>
        <Link className="btn primary" to="/chat">
          Open chat
        </Link>
      </div>

      {backendDown && (
        <div className="abstained-banner" style={{ marginBottom: 18 }}>
          Backend is unreachable. Start PostgreSQL and the API (`uv run uvicorn app.main:app` from backend/).
        </div>
      )}

      <div className="stats-grid">
        <div className="stat-tile">
          <div className="label">Collections</div>
          <div className="value">{collections.length}</div>
        </div>
        <div className="stat-tile">
          <div className="label">Documents</div>
          <div className="value">{docs}</div>
        </div>
        <div className="stat-tile">
          <div className="label">Chunks</div>
          <div className="value">{chunks}</div>
        </div>
        <div className="stat-tile">
          <div className="label">Providers</div>
          <div className="value">{configured}</div>
        </div>
      </div>

      <div className="grid-cards" style={{ marginTop: 22 }}>
        <div className="card">
          <h3 style={{ marginBottom: 12 }}>System</h3>
          {health ? (
            <dl className="kv">
              <dt>Database</dt>
              <dd>{health.checks.database.ok ? "ok" : health.checks.database.error}</dd>
              <dt>Redis</dt>
              <dd>{health.checks.redis.ok ? "ok" : health.checks.redis.note ?? "fallback"}</dd>
              <dt>Local mode</dt>
              <dd>{config?.local_mode ? "on" : "off"}</dd>
              <dt>Web search</dt>
              <dd>{config?.web_search_enabled ? "on" : "off"}</dd>
              <dt>Ready</dt>
              <dd>{health.ready ? "yes" : "no"}</dd>
            </dl>
          ) : (
            <p className="dim">Health unavailable.</p>
          )}
        </div>
        <div className="card">
          <h3 style={{ marginBottom: 12 }}>Providers</h3>
          {providers.map((p) => (
            <div key={p.name} className="row spread" style={{ padding: "4px 0" }}>
              <span>{p.label}</span>
              <span className={`badge ${p.configured ? "green" : ""}`}>
                {p.configured ? "configured" : "missing credentials"}
              </span>
            </div>
          ))}
        </div>
      </div>

      <h2 style={{ fontSize: 15, margin: "28px 0 12px" }}>Recent queries</h2>
      {!traces.length ? (
        <EmptyState icon="🔍" title="No traces yet">
          <p>Ask a question in chat to produce an inspectable retrieval trace.</p>
        </EmptyState>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Query</th>
              <th>Strategy</th>
              <th>Confidence</th>
              <th>Latency</th>
              <th>When</th>
            </tr>
          </thead>
          <tbody>
            {traces.map((t) => {
              const score = confidenceScore(t.confidence);
              return (
                <tr key={t.id} className="clickable">
                  <td>
                    <Link to={`/traces/${t.id}`}>{t.query.slice(0, 80)}</Link>
                    {t.abstained && (
                      <span className="badge yellow" style={{ marginLeft: 8 }}>
                        abstained
                      </span>
                    )}
                  </td>
                  <td className="mono">{t.strategy}</td>
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
