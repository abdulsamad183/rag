import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { EvalResult, EvalRun } from "../api/types";
import EmptyState from "../components/EmptyState";
import Markdown from "../components/Markdown";
import Modal from "../components/Modal";
import { formatDate, formatMs, statusClass } from "../utils/format";

export default function RunDetailPage() {
  const { runId } = useParams();
  const [run, setRun] = useState<EvalRun | null>(null);
  const [results, setResults] = useState<EvalResult[]>([]);
  const [filter, setFilter] = useState("");
  const [inspect, setInspect] = useState<EvalResult | null>(null);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    async function load() {
      const [r, rows] = await Promise.all([api.getRun(runId!), api.runResults(runId!)]);
      if (!cancelled) {
        setRun(r);
        setResults(rows);
      }
    }
    void load();
    const timer = setInterval(() => {
      if (run?.status === "queued" || run?.status === "running") void load();
    }, 2000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [runId, run?.status]);

  const filtered = useMemo(() => {
    if (!filter) return results;
    if (filter === "failed") return results.filter((r) => r.failure_category);
    if (filter === "abstained") return results.filter((r) => r.abstained);
    return results.filter((r) => r.failure_category === filter || r.question_type === filter);
  }, [results, filter]);

  if (!run) {
    return (
      <div className="page">
        <div className="status-line">
          <span className="spinner" /> Loading run…
        </div>
      </div>
    );
  }

  const gt = run.metrics.ground_truth ?? {};
  const failures = run.metrics.failures ?? {};

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <Link to="/evaluation" className="faint" style={{ fontSize: 12 }}>
            ← Evaluation
          </Link>
          <h1>{run.name}</h1>
          <p className="subtitle">
            {run.config.mode as string} · {String(run.config.strategy ?? "auto")} ·{" "}
            <span className={`badge ${statusClass(run.status)}`}>{run.status}</span> · {formatDate(run.created_at)}
          </p>
        </div>
        <a className="btn" href={api.exportRunUrl(run.id, "json")}>
          Export JSON
        </a>
      </div>

      {run.error && <div className="abstained-banner" style={{ marginBottom: 16 }}>{run.error}</div>}

      <div className="stats-grid">
        {[
          ["Recall@5", gt["recall@5"]],
          ["MRR", gt.mrr],
          ["NDCG", gt.ndcg],
          ["Faithfulness", gt.faithfulness],
          ["Citation P", gt.citation_precision],
          ["Abstention", run.metrics.abstention_accuracy],
        ].map(([label, value]) => (
          <div key={String(label)} className="stat-tile">
            <div className="label">{label}</div>
            <div className="value">{typeof value === "number" ? value.toFixed(3) : "—"}</div>
          </div>
        ))}
      </div>

      {!!Object.keys(failures).length && (
        <div className="card" style={{ marginTop: 18 }}>
          <h3 style={{ marginBottom: 8 }}>Failure categories</h3>
          <div className="row wrap">
            {Object.entries(failures).map(([name, count]) => (
              <button key={name} className="chip" onClick={() => setFilter(name)}>
                {name}: {count}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="row spread" style={{ margin: "22px 0 10px" }}>
        <h2 style={{ fontSize: 15 }}>Failure analysis</h2>
        <select className="mini-select" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">All questions</option>
          <option value="failed">Has failure category</option>
          <option value="abstained">Abstained</option>
          <option value="simple">simple</option>
          <option value="multi_hop">multi_hop</option>
          <option value="temporal">temporal</option>
          <option value="unanswerable">unanswerable</option>
          <option value="retrieval_failure">retrieval_failure</option>
          <option value="citation_failure">citation_failure</option>
          <option value="abstention_failure">abstention_failure</option>
          <option value="generation_failure">generation_failure</option>
        </select>
      </div>

      {!filtered.length ? (
        <EmptyState icon="✅" title="No matching results" />
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Question</th>
              <th>Type</th>
              <th>Failure</th>
              <th>Latency</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((row) => (
              <tr key={row.id} className="clickable" onClick={() => setInspect(row)}>
                <td>
                  {row.question || row.question_id}
                  {row.abstained && (
                    <span className="badge yellow" style={{ marginLeft: 8 }}>
                      abstained
                    </span>
                  )}
                  {row.error && <div className="faint">{row.error}</div>}
                </td>
                <td>{row.question_type}</td>
                <td>{row.failure_category || "—"}</td>
                <td>{formatMs(row.latency_ms)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {inspect && (
        <Modal title="Why did this fail?" onClose={() => setInspect(null)}>
          <dl className="kv">
            <dt>Question</dt>
            <dd>{inspect.question}</dd>
            <dt>Expected</dt>
            <dd>{inspect.expected_answer || "—"}</dd>
            <dt>Answerable</dt>
            <dd>{inspect.answerable ? "yes" : "no"}</dd>
            <dt>Category</dt>
            <dd>{inspect.failure_category || "none"}</dd>
            {inspect.trace_id && (
              <>
                <dt>Trace</dt>
                <dd>
                  <Link to={`/traces/${inspect.trace_id}`}>Open trace</Link>
                </dd>
              </>
            )}
          </dl>
          <h3 style={{ fontSize: 13, margin: "14px 0 6px" }}>Generated answer</h3>
          <Markdown text={inspect.answer || "(empty)"} />
          <h3 style={{ fontSize: 13, margin: "14px 0 6px" }}>Retrieved</h3>
          <pre className="payload" style={{ maxHeight: 180, overflow: "auto" }}>
            {JSON.stringify(inspect.retrieved, null, 2)}
          </pre>
          <h3 style={{ fontSize: 13, margin: "14px 0 6px" }}>Metrics</h3>
          <pre className="payload">{JSON.stringify(inspect.metrics, null, 2)}</pre>
        </Modal>
      )}
    </div>
  );
}
