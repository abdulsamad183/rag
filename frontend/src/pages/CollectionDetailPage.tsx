import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import type { ChunkRow, Collection, Document, DocumentVersion, GraphData } from "../api/types";
import EmptyState from "../components/EmptyState";
import GraphView from "../components/GraphView";
import Markdown from "../components/Markdown";
import Modal from "../components/Modal";
import StatusBadge from "../components/StatusBadge";
import { useApp } from "../state/AppContext";
import { formatBytes, formatDate } from "../utils/format";

const ACTIVE = new Set(["queued", "parsing", "chunking", "embedding", "indexing"]);

export default function CollectionDetailPage() {
  const { collectionId } = useParams();
  const navigate = useNavigate();
  const { config, toast, refreshCollections } = useApp();
  const [collection, setCollection] = useState<Collection | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [tab, setTab] = useState<"documents" | "settings" | "graph">("documents");
  const [drag, setDrag] = useState(false);
  const [selected, setSelected] = useState<Document | null>(null);
  const [chunks, setChunks] = useState<ChunkRow[]>([]);
  const [versions, setVersions] = useState<DocumentVersion[]>([]);
  const [summary, setSummary] = useState("");
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<"collection" | Document | null>(null);
  const [saving, setSaving] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    if (!collectionId) return;
    const [col, docs] = await Promise.all([
      api.getCollection(collectionId),
      api.listDocuments(collectionId),
    ]);
    setCollection(col);
    setDocuments(docs);
  }, [collectionId]);

  useEffect(() => {
    load().catch((err) => toast(err instanceof Error ? err.message : "Load failed", "error"));
  }, [load, toast]);

  useEffect(() => {
    const busy = documents.some((d) => ACTIVE.has(d.status));
    if (!busy) return;
    const timer = setInterval(() => {
      void load();
    }, 1500);
    return () => clearInterval(timer);
  }, [documents, load]);

  useEffect(() => {
    if (tab !== "graph" || !collectionId) return;
    api
      .collectionGraph(collectionId)
      .then(setGraph)
      .catch(() => setGraph({ nodes: [], edges: [] }));
  }, [tab, collectionId]);

  async function uploadFiles(files: FileList | File[]) {
    if (!collectionId) return;
    for (const file of Array.from(files)) {
      try {
        const result = await api.uploadDocument(collectionId, file);
        toast(result.message || `Uploaded ${file.name}`, result.is_new_content ? "success" : "info");
      } catch (err) {
        toast(err instanceof ApiError ? err.message : `Failed: ${file.name}`, "error");
      }
    }
    await load();
    await refreshCollections();
  }

  async function openDocument(doc: Document) {
    setSelected(doc);
    setSummary("");
    const [c, v] = await Promise.all([api.documentChunks(doc.id), api.documentVersions(doc.id)]);
    setChunks(c);
    setVersions(v);
  }

  async function saveSettings() {
    if (!collection) return;
    setSaving(true);
    try {
      const updated = await api.updateCollection(collection.id, {
        name: collection.name,
        description: collection.description,
        graph_enabled: collection.graph_enabled,
        temporal_enabled: collection.temporal_enabled,
        chunking_config: collection.chunking_config,
        retrieval_config: collection.retrieval_config,
      });
      setCollection(updated);
      await refreshCollections();
      toast("Settings saved", "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "Save failed", "error");
    } finally {
      setSaving(false);
    }
  }

  async function destroy() {
    if (!collection) return;
    if (confirmDelete === "collection") {
      await api.deleteCollection(collection.id);
      await refreshCollections();
      navigate("/collections");
      return;
    }
    if (confirmDelete && typeof confirmDelete === "object") {
      await api.deleteDocument(confirmDelete.id);
      setSelected(null);
      setConfirmDelete(null);
      await load();
      await refreshCollections();
    }
  }

  if (!collection) {
    return (
      <div className="page">
        <div className="status-line">
          <span className="spinner" /> Loading collection…
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <Link to="/collections" className="faint" style={{ fontSize: 12 }}>
            ← Collections
          </Link>
          <h1>{collection.name}</h1>
          <p className="subtitle">
            {collection.embedding_provider}/{collection.embedding_model} · {collection.embedding_dimension}d
            {collection.graph_enabled ? " · graph" : ""}
            {collection.temporal_enabled ? " · temporal" : ""}
          </p>
        </div>
        <button className="btn danger" onClick={() => setConfirmDelete("collection")}>
          Delete
        </button>
      </div>

      <div className="tabs">
        {(["documents", "settings", "graph"] as const).map((t) => (
          <button key={t} className={`tab${tab === t ? " active" : ""}`} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>

      {tab === "documents" && (
        <>
          <div
            className={`dropzone${drag ? " active" : ""}`}
            onClick={() => fileRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              if (e.dataTransfer.files.length) void uploadFiles(e.dataTransfer.files);
            }}
          >
            Drop PDF, Markdown, TXT, DOCX, HTML, CSV, or JSON — or click to browse
            <input
              ref={fileRef}
              type="file"
              multiple
              hidden
              accept=".pdf,.txt,.md,.markdown,.docx,.html,.htm,.csv,.json"
              onChange={(e) => e.target.files && void uploadFiles(e.target.files)}
            />
          </div>

          {!documents.length ? (
            <EmptyState icon="📄" title="No documents">
              <p>Upload files to start ingestion. Progress updates live while workers run.</p>
            </EmptyState>
          ) : (
            <table className="table" style={{ marginTop: 18 }}>
              <thead>
                <tr>
                  <th>Document</th>
                  <th>Status</th>
                  <th>Chunks</th>
                  <th>Size</th>
                  <th>Updated</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {documents.map((doc) => (
                  <tr key={doc.id} className="clickable" onClick={() => void openDocument(doc)}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{doc.title || doc.filename}</div>
                      <div className="faint" style={{ fontSize: 11.5 }}>
                        {doc.source_type} {doc.page_count ? `· ${doc.page_count} pages` : ""}
                      </div>
                      {doc.error && <div className="badge red" style={{ marginTop: 4 }}>{doc.error}</div>}
                    </td>
                    <td>
                      <StatusBadge status={doc.status} />
                      {ACTIVE.has(doc.status) && (
                        <div className="progress-track" style={{ marginTop: 6, width: 90 }}>
                          <div style={{ width: `${Math.round(doc.progress * 100)}%` }} />
                        </div>
                      )}
                    </td>
                    <td>{doc.chunk_count}</td>
                    <td>{formatBytes(doc.size_bytes)}</td>
                    <td className="faint">{formatDate(doc.updated_at)}</td>
                    <td>
                      <button
                        className="btn ghost small"
                        onClick={(e) => {
                          e.stopPropagation();
                          setConfirmDelete(doc);
                        }}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}

      {tab === "settings" && (
        <div className="card" style={{ maxWidth: 640 }}>
          <div className="field">
            <label>Name</label>
            <input
              className="input"
              value={collection.name}
              onChange={(e) => setCollection({ ...collection, name: e.target.value })}
            />
          </div>
          <div className="field">
            <label>Description</label>
            <textarea
              className="textarea"
              rows={3}
              value={collection.description}
              onChange={(e) => setCollection({ ...collection, description: e.target.value })}
            />
          </div>
          <div className="field">
            <label>Chunking strategy (applies on reingest)</label>
            <select
              className="select"
              value={String(collection.chunking_config.strategy ?? "recursive")}
              onChange={(e) =>
                setCollection({
                  ...collection,
                  chunking_config: { ...collection.chunking_config, strategy: e.target.value },
                })
              }
            >
              {(config?.chunking_strategies ?? []).map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <label className="row" style={{ gap: 8, marginBottom: 10 }}>
            <input
              type="checkbox"
              checked={collection.graph_enabled}
              onChange={(e) => setCollection({ ...collection, graph_enabled: e.target.checked })}
            />
            Graph extraction
          </label>
          <label className="row" style={{ gap: 8, marginBottom: 16 }}>
            <input
              type="checkbox"
              checked={collection.temporal_enabled}
              onChange={(e) => setCollection({ ...collection, temporal_enabled: e.target.checked })}
            />
            Temporal mode
          </label>
          <p className="hint faint">
            Embedding model is locked after the first document is indexed. Re-create the collection to
            change embedding space.
          </p>
          <button className="btn primary" disabled={saving} onClick={() => void saveSettings()}>
            Save
          </button>
        </div>
      )}

      {tab === "graph" && graph && <GraphView data={graph} />}

      {selected && (
        <Modal title={selected.title || selected.filename} onClose={() => setSelected(null)}>
          <dl className="kv">
            <dt>Status</dt>
            <dd>
              <StatusBadge status={selected.status} />
            </dd>
            <dt>Version</dt>
            <dd>{selected.current_version}</dd>
            <dt>Chunks</dt>
            <dd>{selected.chunk_count}</dd>
            <dt>Trust</dt>
            <dd>{selected.trust.toFixed(2)}</dd>
            <dt>Hash</dt>
            <dd className="mono">{selected.content_hash.slice(0, 12)}…</dd>
          </dl>
          <div className="row wrap" style={{ margin: "14px 0" }}>
            <button
              className="btn small"
              onClick={async () => {
                await api.reingestDocument(selected.id);
                toast("Reingest queued");
                setSelected(null);
                await load();
              }}
            >
              Reingest
            </button>
            <button
              className="btn small"
              onClick={async () => {
                const result = await api.summarizeDocument(selected.id);
                setSummary(result.summary);
              }}
            >
              Summarize
            </button>
            {collection.graph_enabled && (
              <button
                className="btn small"
                onClick={async () => {
                  await api.extractGraph(selected.id);
                  toast("Graph extraction queued");
                }}
              >
                Extract graph
              </button>
            )}
            <a className="btn small" href={api.documentRawUrl(selected.id)} target="_blank" rel="noreferrer">
              Open file
            </a>
          </div>
          {summary && (
            <div className="card" style={{ marginBottom: 12 }}>
              <Markdown text={summary} />
            </div>
          )}
          {versions.length > 1 && (
            <div style={{ marginBottom: 12 }}>
              <h3 style={{ fontSize: 13, marginBottom: 6 }}>Versions</h3>
              {versions.map((v) => (
                <div key={v.id} className="dim" style={{ fontSize: 12.5 }}>
                  v{v.version} · {formatBytes(v.size_bytes)} · {formatDate(v.created_at)}
                </div>
              ))}
            </div>
          )}
          <h3 style={{ fontSize: 13, marginBottom: 8 }}>Chunks</h3>
          <div style={{ maxHeight: 280, overflowY: "auto", display: "flex", flexDirection: "column", gap: 8 }}>
            {chunks.map((chunk) => (
              <div key={chunk.id} className="evidence-card">
                <div className="src">
                  #{chunk.chunk_index}
                  {chunk.heading && <span>{chunk.heading}</span>}
                  {chunk.page_start != null && <span className="faint">p.{chunk.page_start}</span>}
                </div>
                <div className="snippet">{chunk.content.slice(0, 400)}</div>
              </div>
            ))}
          </div>
        </Modal>
      )}

      {confirmDelete && (
        <Modal
          title={confirmDelete === "collection" ? "Delete collection?" : "Delete document?"}
          onClose={() => setConfirmDelete(null)}
        >
          <p className="dim">
            This cannot be undone. Embeddings, chunks, and traces attached to this{" "}
            {confirmDelete === "collection" ? "collection" : "document"} will be removed.
          </p>
          <div className="row" style={{ justifyContent: "flex-end", marginTop: 16 }}>
            <button className="btn ghost" onClick={() => setConfirmDelete(null)}>
              Cancel
            </button>
            <button className="btn danger" onClick={() => void destroy()}>
              Delete
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
