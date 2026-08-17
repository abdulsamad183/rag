import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import type { Dataset, EvalRun, RunComparison } from "../api/types";
import EmptyState from "../components/EmptyState";
import Modal from "../components/Modal";
import { useApp } from "../state/AppContext";
import { formatDate, statusClass } from "../utils/format";

export default function EvaluationPage() {
  const { collections, providers, toast } = useApp();
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [runOpen, setRunOpen] = useState<Dataset | null>(null);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [comparison, setComparison] = useState<RunComparison | null>(null);
  const [dsName, setDsName] = useState("");
  const [dsDesc, setDsDesc] = useState("");
  const [dsFile, setDsFile] = useState<File | null>(null);
  const [runName, setRunName] = useState("");
  const [runCols, setRunCols] = useState<string[]>([]);
  const [runMode, setRunMode] = useState("balanced");
  const [runProvider, setRunProvider] = useState("");
  const [runModel, setRunModel] = useState("");
  const [runStrategy, setRunStrategy] = useState("");
  const [judge, setJudge] = useState(false);

  const load = useCallback(async () => {
    const [d, r] = await Promise.all([api.listDatasets(), api.listRuns()]);
    setDatasets(d);
    setRuns(r);
  }, []);

  useEffect(() => {
    load().catch((err) => toast(err instanceof Error ? err.message : "Load failed", "error"));
  }, [load, toast]);

  useEffect(() => {
    const busy = runs.some((r) => r.status === "queued" || r.status === "running");
    if (!busy) return;
    const timer = setInterval(() => void load(), 2000);
    return () => clearInterval(timer);
  }, [runs, load]);

  async function uploadDataset() {
    if (!dsFile || !dsName.trim()) return;
    await api.uploadDataset(dsName.trim(), dsDesc, dsFile);
    setUploadOpen(false);
    setDsName("");
    setDsFile(null);
    toast("Dataset imported", "success");
    await load();
  }

  async function startRun() {
    if (!runOpen || !runCols.length) return;
    await api.createRun(runOpen.id, {
      name: runName || `${runOpen.name} · ${runMode}`,
      collection_ids: runCols,
      mode: runMode,
      provider: runProvider || null,
      model: runModel || null,
      strategy: runStrategy || null,
      use_llm_judge: judge,
    });
    setRunOpen(null);
    toast("Evaluation queued", "success");
    await load();
  }

  async function compare() {
    if (compareIds.length < 2) return;
    setComparison(await api.compareRuns(compareIds));
  }

  const chartData = useMemo(() => {
    if (!comparison) return [];
    return Object.entries(comparison.metric_table).map(([metric, byRun]) => {
      const row: Record<string, string | number | null> = { metric };
      for (const run of comparison.runs) {
        row[run.name] = byRun[run.id] ?? null;
      }
      return row;
    });
  }, [comparison]);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Evaluation</h1>
          <p className="subtitle">
            JSONL datasets, retrieval metrics, citation quality, abstention accuracy, and A/B comparison.
          </p>
        </div>
        <button className="btn primary" onClick={() => setUploadOpen(true)}>
          Import dataset
        </button>
      </div>

      <h2 style={{ fontSize: 15, marginBottom: 10 }}>Datasets</h2>
      {!datasets.length ? (
        <EmptyState icon="📊" title="No datasets">
          <p>Import a JSONL file with question, expected_answer, relevant_documents, and answerable.</p>
        </EmptyState>
      ) : (
        <div className="grid-cards" style={{ marginBottom: 28 }}>
          {datasets.map((d) => (
            <div key={d.id} className="card">
              <div className="row spread">
                <h3>{d.name}</h3>
                <span className="badge">{d.question_count} questions</span>
              </div>
              <p className="dim" style={{ margin: "8px 0 14px" }}>
                {d.description || "—"}
              </p>
              <div className="row">
                <button className="btn small primary" onClick={() => setRunOpen(d)}>
                  Run
                </button>
                <button
                  className="btn small danger"
                  onClick={async () => {
                    if (!confirm(`Delete dataset “${d.name}”?`)) return;
                    await api.deleteDataset(d.id);
                    await load();
                  }}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="row spread" style={{ marginBottom: 10 }}>
        <h2 style={{ fontSize: 15 }}>Runs</h2>
        <button className="btn small" disabled={compareIds.length < 2} onClick={() => void compare()}>
          Compare selected ({compareIds.length})
        </button>
      </div>
      {!runs.length ? (
        <p className="dim">No runs yet.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th />
              <th>Name</th>
              <th>Status</th>
              <th>Recall@5</th>
              <th>Faithfulness</th>
              <th>Abstention</th>
              <th>When</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id}>
                <td>
                  <input
                    type="checkbox"
                    checked={compareIds.includes(run.id)}
                    onChange={(e) =>
                      setCompareIds((prev) =>
                        e.target.checked ? [...prev, run.id] : prev.filter((id) => id !== run.id),
                      )
                    }
                  />
                </td>
                <td>
                  <Link to={`/evaluation/runs/${run.id}`}>{run.name}</Link>
                </td>
                <td>
                  <span className={`badge ${statusClass(run.status)}`}>{run.status}</span>
                  {(run.status === "queued" || run.status === "running") && (
                    <div className="progress-track" style={{ marginTop: 6, width: 80 }}>
                      <div style={{ width: `${Math.round(run.progress * 100)}%` }} />
                    </div>
                  )}
                </td>
                <td className="mono">{fmt(run.metrics.ground_truth?.["recall@5"])}</td>
                <td className="mono">{fmt(run.metrics.ground_truth?.faithfulness)}</td>
                <td className="mono">{fmt(run.metrics.abstention_accuracy)}</td>
                <td className="faint">{formatDate(run.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {comparison && chartData.length > 0 && (
        <div className="card" style={{ marginTop: 24, height: 360 }}>
          <h3 style={{ marginBottom: 12 }}>A/B comparison</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2432" />
              <XAxis dataKey="metric" stroke="#9aa3b5" tick={{ fontSize: 11 }} />
              <YAxis stroke="#9aa3b5" tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={{ background: "#11151f", border: "1px solid #2a3244" }} />
              <Legend />
              {comparison.runs.map((run, index) => (
                <Bar
                  key={run.id}
                  dataKey={run.name}
                  fill={["#6366f1", "#22d3ee", "#34d399", "#fbbf24"][index % 4]}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {uploadOpen && (
        <Modal title="Import JSONL dataset" onClose={() => setUploadOpen(false)}>
          <div className="field">
            <label>Name</label>
            <input className="input" value={dsName} onChange={(e) => setDsName(e.target.value)} />
          </div>
          <div className="field">
            <label>Description</label>
            <input className="input" value={dsDesc} onChange={(e) => setDsDesc(e.target.value)} />
          </div>
          <div className="field">
            <label>JSONL file</label>
            <input className="input" type="file" accept=".jsonl,.json" onChange={(e) => setDsFile(e.target.files?.[0] ?? null)} />
          </div>
          <button className="btn primary" disabled={!dsFile || !dsName.trim()} onClick={() => void uploadDataset()}>
            Import
          </button>
        </Modal>
      )}

      {runOpen && (
        <Modal title={`Run “${runOpen.name}”`} onClose={() => setRunOpen(null)}>
          <div className="field">
            <label>Run name</label>
            <input className="input" value={runName} onChange={(e) => setRunName(e.target.value)} />
          </div>
          <div className="field">
            <label>Collections</label>
            {collections.map((c) => (
              <label key={c.id} className="row" style={{ gap: 8, marginBottom: 6 }}>
                <input
                  type="checkbox"
                  checked={runCols.includes(c.id)}
                  onChange={(e) =>
                    setRunCols((prev) => (e.target.checked ? [...prev, c.id] : prev.filter((id) => id !== c.id)))
                  }
                />
                {c.name}
              </label>
            ))}
          </div>
          <div className="field">
            <label>Mode</label>
            <select className="select" value={runMode} onChange={(e) => setRunMode(e.target.value)}>
              <option value="fast">fast (vector baseline)</option>
              <option value="balanced">balanced (hybrid + rerank)</option>
              <option value="adaptive">adaptive</option>
              <option value="deep">deep</option>
              <option value="research">research</option>
            </select>
          </div>
          <div className="field">
            <label>Provider override</label>
            <select
              className="select"
              value={runProvider}
              onChange={(e) => {
                setRunProvider(e.target.value);
                const p = providers.find((x) => x.name === e.target.value);
                setRunModel(p?.default_model ?? "");
              }}
            >
              <option value="">Default</option>
              {providers.map((p) => (
                <option key={p.name} value={p.name} disabled={!p.configured}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>
          {runProvider && (
            <div className="field">
              <label>Model</label>
              <select className="select" value={runModel} onChange={(e) => setRunModel(e.target.value)}>
                {(providers.find((p) => p.name === runProvider)?.models ?? []).map((m) => (
                  <option key={m.name} value={m.name}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="field">
            <label>Strategy override</label>
            <input
              className="input"
              placeholder="leave empty for mode default"
              value={runStrategy}
              onChange={(e) => setRunStrategy(e.target.value)}
            />
          </div>
          <label className="row" style={{ gap: 8, marginBottom: 14 }}>
            <input type="checkbox" checked={judge} onChange={(e) => setJudge(e.target.checked)} />
            LLM-as-judge (separate from ground-truth metrics)
          </label>
          <button className="btn primary" disabled={!runCols.length} onClick={() => void startRun()}>
            Start run
          </button>
        </Modal>
      )}
    </div>
  );
}

function fmt(value: number | null | undefined): string {
  return typeof value === "number" ? value.toFixed(3) : "—";
}
