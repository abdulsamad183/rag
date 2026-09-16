import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { HealthReport, RetrievalStats, TraceSummary } from "../api/types";
import EmptyState from "../components/EmptyState";
import { useApp } from "../state/AppContext";
import { confidenceScore, formatDate, formatMs } from "../utils/format";

type WindowDays = 1 | 7 | 30;

function formatUsd(value: number): string {
  if (value <= 0) return "$0";
  if (value < 0.01) return `$${value.toFixed(4)}`;
  return `$${value.toFixed(2)}`;
}

function formatPct(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}

export default function DashboardPage() {
  const { collections, providers, backendDown, config } = useApp();
  const [health, setHealth] = useState<HealthReport | null>(null);
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [statsDays, setStatsDays] = useState<WindowDays>(7);
  const [stats, setStats] = useState<RetrievalStats | null>(null);

  const collectionName = useMemo(() => {
    const map = new Map(collections.map((c) => [c.id, c.name]));
    return (id: string) => (id === "none" ? "Web / none" : map.get(id) ?? id.slice(0, 8));
  }, [collections]);

  useEffect(() => {
    api.ready().then(setHealth).catch(() => setHealth(null));
    api.listTraces(8).then(setTraces).catch(() => setTraces([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .retrievalStats(statsDays)
      .then((data) => {
        if (!cancelled) setStats(data);
      })
      .catch(() => {
        if (!cancelled) setStats(null);
      });
    return () => {
      cancelled = true;
    };
  }, [statsDays]);

  const docs = collections.reduce((n, c) => n + c.document_count, 0);
  const chunks = collections.reduce((n, c) => n + c.chunk_count, 0);
  const configured = providers.filter((p) => p.configured).length;
  const totals = stats?.totals;

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

      <div className="row spread" style={{ marginTop: 28, marginBottom: 12, alignItems: "center" }}>
        <h2 style={{ fontSize: 15, margin: 0 }}>Cost &amp; latency</h2>
        <div className="chip-row">
          {([1, 7, 30] as WindowDays[]).map((d) => (
            <button
              key={d}
              type="button"
              className={`chip${statsDays === d ? " on" : ""}`}
              onClick={() => setStatsDays(d)}
            >
              {d === 1 ? "24h" : `${d}d`}
            </button>
          ))}
        </div>
      </div>

      <div className="stats-grid">
        <div className="stat-tile">
          <div className="label">Queries</div>
          <div className="value">{totals?.queries ?? "—"}</div>
        </div>
        <div className="stat-tile">
          <div className="label">Est. cost</div>
          <div className="value" style={{ fontSize: 22 }}>
            {totals ? formatUsd(totals.estimated_cost_usd) : "—"}
          </div>
        </div>
        <div className="stat-tile">
          <div className="label">Latency p50 / p95</div>
          <div className="value" style={{ fontSize: 18 }}>
            {totals
              ? `${formatMs(Math.round(totals.latency_ms.p50))} / ${formatMs(Math.round(totals.latency_ms.p95))}`
              : "—"}
          </div>
        </div>
        <div className="stat-tile">
          <div className="label">Abstain rate</div>
          <div className="value" style={{ fontSize: 22 }}>
            {totals ? formatPct(totals.abstain_rate) : "—"}
          </div>
        </div>
      </div>

      {totals && totals.queries > 0 && (
        <div className="faint" style={{ fontSize: 12, marginTop: 8 }}>
          {totals.prompt_tokens.toLocaleString()} prompt · {totals.completion_tokens.toLocaleString()}{" "}
          completion tokens · mean latency {formatMs(Math.round(totals.latency_ms.mean))}
        </div>
      )}

      <div className="grid-cards" style={{ marginTop: 18 }}>
        <div className="card">
          <h3 style={{ marginBottom: 12 }}>By provider</h3>
          {!stats?.by_provider.length ? (
            <p className="dim">No queries in this window.</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Provider</th>
                  <th>Queries</th>
                  <th>Cost</th>
                  <th>p50</th>
                  <th>p95</th>
                  <th>Abstain</th>
                </tr>
              </thead>
              <tbody>
                {stats.by_provider.map((row) => (
                  <tr key={row.provider}>
                    <td className="mono">{row.provider}</td>
                    <td>{row.queries}</td>
                    <td>{formatUsd(row.estimated_cost_usd)}</td>
                    <td>{formatMs(Math.round(row.latency_ms_p50))}</td>
                    <td>{formatMs(Math.round(row.latency_ms_p95))}</td>
                    <td>{formatPct(row.abstain_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div className="card">
          <h3 style={{ marginBottom: 12 }}>By collection</h3>
          {!stats?.by_collection.length ? (
            <p className="dim">No queries in this window.</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Collection</th>
                  <th>Queries</th>
                  <th>Cost</th>
                  <th>p50</th>
                  <th>p95</th>
                  <th>Abstain</th>
                </tr>
              </thead>
              <tbody>
                {stats.by_collection.map((row) => (
                  <tr key={row.collection_id}>
                    <td>{collectionName(row.collection_id)}</td>
                    <td>{row.queries}</td>
                    <td>{formatUsd(row.estimated_cost_usd)}</td>
                    <td>{formatMs(Math.round(row.latency_ms_p50))}</td>
                    <td>{formatMs(Math.round(row.latency_ms_p95))}</td>
                    <td>{formatPct(row.abstain_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
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
