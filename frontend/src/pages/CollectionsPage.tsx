import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import EmptyState from "../components/EmptyState";
import Modal from "../components/Modal";
import { useApp } from "../state/AppContext";
import { formatDate } from "../utils/format";

export default function CollectionsPage() {
  const { collections, config, providers, refreshCollections, toast } = useApp();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const embeddingProviders = providers.filter((p) => p.embedding_models.length);
  const [embeddingProvider, setEmbeddingProvider] = useState(
    config?.default_embedding_provider ?? "openai",
  );
  const [embeddingModel, setEmbeddingModel] = useState("");
  const [strategy, setStrategy] = useState("recursive");
  const [chunkSize, setChunkSize] = useState(800);
  const [chunkOverlap, setChunkOverlap] = useState(120);
  const [graphEnabled, setGraphEnabled] = useState(false);
  const [temporalEnabled, setTemporalEnabled] = useState(false);
  const [saving, setSaving] = useState(false);

  const embedModels =
    embeddingProviders.find((p) => p.name === embeddingProvider)?.embedding_models ?? [];

  async function create() {
    if (!name.trim()) return;
    setSaving(true);
    try {
      const created = await api.createCollection({
        name: name.trim(),
        description,
        embedding_provider: embeddingProvider,
        embedding_model: embeddingModel || undefined,
        chunking_strategy: strategy,
        chunk_size: chunkSize,
        chunk_overlap: chunkOverlap,
        graph_enabled: graphEnabled,
        temporal_enabled: temporalEnabled,
      });
      await refreshCollections();
      toast("Collection created", "success");
      setOpen(false);
      setName("");
      navigate(`/collections/${created.id}`);
    } catch (err) {
      toast(err instanceof Error ? err.message : "Create failed", "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Collections</h1>
          <p className="subtitle">Knowledge bases with their own embeddings, chunking, and retrieval settings.</p>
        </div>
        <button className="btn primary" onClick={() => setOpen(true)}>
          New collection
        </button>
      </div>

      {!collections.length ? (
        <EmptyState icon="🗂" title="No collections yet">
          <p>Create a collection, upload documents, then chat against the indexed evidence.</p>
          <button className="btn primary" onClick={() => setOpen(true)}>
            Create collection
          </button>
        </EmptyState>
      ) : (
        <div className="grid-cards">
          {collections.map((c) => (
            <div key={c.id} className="card clickable" onClick={() => navigate(`/collections/${c.id}`)}>
              <div className="row spread">
                <h3>{c.name}</h3>
                <span className="badge">{c.embedding_provider}</span>
              </div>
              <p className="dim" style={{ margin: "8px 0 14px", minHeight: 36 }}>
                {c.description || "No description"}
              </p>
              <div className="row wrap faint" style={{ fontSize: 12.5 }}>
                <span>{c.document_count} docs</span>
                <span>·</span>
                <span>{c.chunk_count} chunks</span>
                <span>·</span>
                <span>{(c.chunking_config.strategy as string) || "recursive"}</span>
                {c.graph_enabled && <span className="badge">graph</span>}
                {c.temporal_enabled && <span className="badge">temporal</span>}
              </div>
              <div className="faint" style={{ marginTop: 10, fontSize: 11.5 }}>
                {formatDate(c.created_at)}
              </div>
            </div>
          ))}
        </div>
      )}

      {open && (
        <Modal title="New collection" onClose={() => setOpen(false)}>
          <div className="field">
            <label>Name</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </div>
          <div className="field">
            <label>Description</label>
            <textarea className="textarea" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div className="field">
            <label>Embedding provider</label>
            <select
              className="select"
              value={embeddingProvider}
              onChange={(e) => {
                setEmbeddingProvider(e.target.value);
                setEmbeddingModel("");
              }}
            >
              {embeddingProviders.map((p) => (
                <option key={p.name} value={p.name} disabled={!p.configured}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Embedding model</label>
            <select className="select" value={embeddingModel} onChange={(e) => setEmbeddingModel(e.target.value)}>
              <option value="">Provider default</option>
              {embedModels.map((m) => (
                <option key={m.name} value={m.name}>
                  {m.name} ({m.dimension}d)
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Chunking strategy</label>
            <select className="select" value={strategy} onChange={(e) => setStrategy(e.target.value)}>
              {(config?.chunking_strategies ?? ["recursive"]).map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div className="row" style={{ gap: 12 }}>
            <div className="field" style={{ flex: 1 }}>
              <label>Chunk size</label>
              <input className="input" type="number" value={chunkSize} onChange={(e) => setChunkSize(Number(e.target.value))} />
            </div>
            <div className="field" style={{ flex: 1 }}>
              <label>Overlap</label>
              <input
                className="input"
                type="number"
                value={chunkOverlap}
                onChange={(e) => setChunkOverlap(Number(e.target.value))}
              />
            </div>
          </div>
          <label className="row" style={{ gap: 8, marginBottom: 10 }}>
            <input type="checkbox" checked={graphEnabled} onChange={(e) => setGraphEnabled(e.target.checked)} />
            Enable graph extraction
          </label>
          <label className="row" style={{ gap: 8, marginBottom: 16 }}>
            <input type="checkbox" checked={temporalEnabled} onChange={(e) => setTemporalEnabled(e.target.checked)} />
            Temporal validity
          </label>
          <div className="row" style={{ justifyContent: "flex-end" }}>
            <button className="btn ghost" onClick={() => setOpen(false)}>
              Cancel
            </button>
            <button className="btn primary" disabled={!name.trim() || saving} onClick={() => void create()}>
              Create
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
