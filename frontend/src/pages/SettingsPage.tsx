import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { HealthReport } from "../api/types";
import { useApp } from "../state/AppContext";

export default function SettingsPage() {
  const { config, providers, refreshProviders } = useApp();
  const [health, setHealth] = useState<HealthReport | null>(null);

  useEffect(() => {
    api.ready().then(setHealth).catch(() => setHealth(null));
    void refreshProviders();
  }, [refreshProviders]);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Settings</h1>
          <p className="subtitle">
            Provider credentials live in the server environment — never in the browser. Change models
            here by selecting a configured catalog entry in chat.
          </p>
        </div>
      </div>

      {config?.local_mode && (
        <div className="abstained-banner" style={{ marginBottom: 18 }}>
          Local mode is on: generation and embeddings are restricted to Ollama.
          {config.web_search_enabled
            ? " Web search is available in chat (KB + Web / Web only)."
            : " Web search is off (set WEB_SEARCH_PROVIDER=ddg in .env)."}
        </div>
      )}

      <h2 style={{ fontSize: 15, marginBottom: 10 }}>LLM providers</h2>
      <div className="grid-cards">
        {providers.map((p) => (
          <div key={p.name} className="card">
            <div className="row spread">
              <h3>{p.label}</h3>
              <span className={`badge ${p.configured ? "green" : "red"}`}>
                {p.configured ? "configured" : "not configured"}
              </span>
            </div>
            <p className="dim" style={{ margin: "8px 0" }}>
              Default: {p.default_model || "—"}
              {p.is_local ? " · local" : ""}
            </p>
            {p.note && <p className="faint">{p.note}</p>}
            <div className="faint" style={{ fontSize: 12, marginTop: 8 }}>
              {p.models.slice(0, 6).map((m) => m.label).join(" · ")}
              {p.models.length > 6 ? " …" : ""}
            </div>
          </div>
        ))}
      </div>

      {config && (
        <>
          <h2 style={{ fontSize: 15, margin: "28px 0 10px" }}>Retrieval defaults</h2>
          <div className="card">
            <dl className="kv">
              {Object.entries(config.retrieval_defaults).map(([key, value]) => (
                <div key={key} style={{ display: "contents" }}>
                  <dt>{key}</dt>
                  <dd className="mono">{String(value)}</dd>
                </div>
              ))}
              <dt>Chunking strategies</dt>
              <dd>{config.chunking_strategies.join(", ")}</dd>
              <dt>Retrieval strategies</dt>
              <dd>{config.retrieval_strategies.join(", ")}</dd>
              <dt>Web search</dt>
              <dd>{config.web_search_enabled ? "enabled (DuckDuckGo HTML)" : "off"}</dd>
            </dl>
          </div>
        </>
      )}

      <h2 style={{ fontSize: 15, margin: "28px 0 10px" }}>Health</h2>
      <div className="card">
        {health ? (
          <dl className="kv">
            <dt>Ready</dt>
            <dd>{health.ready ? "yes" : "no"}</dd>
            <dt>Database</dt>
            <dd>{health.checks.database.ok ? "ok" : health.checks.database.error}</dd>
            <dt>Redis</dt>
            <dd>{health.checks.redis.ok ? "ok" : health.checks.redis.note ?? "down"}</dd>
            <dt>Storage</dt>
            <dd>{health.checks.storage.ok ? "ok" : "missing"}</dd>
          </dl>
        ) : (
          <p className="dim">Could not load /ready.</p>
        )}
      </div>
    </div>
  );
}
