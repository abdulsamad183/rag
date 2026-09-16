import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { ChunkDetail, ChunkRow } from "../api/types";
import Modal from "./Modal";

export interface SourceTarget {
  documentId: string;
  chunkId: string;
  documentName: string;
  page?: number | null;
  section?: string;
  sourceUrl?: string;
  sourceType?: string;
  snippet?: string;
}

function isWebSource(target: SourceTarget): boolean {
  if (target.sourceType === "web") return true;
  if (target.sourceUrl?.startsWith("http") && target.sourceType === "web") return true;
  return false;
}

export default function SourceViewer({
  target,
  onClose,
}: {
  target: SourceTarget;
  onClose: () => void;
}) {
  const [chunks, setChunks] = useState<ChunkRow[]>([]);
  const [detail, setDetail] = useState<ChunkDetail | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(!isWebSource(target));
  const highlightRef = useRef<HTMLDivElement | null>(null);

  const web = isWebSource(target);

  useEffect(() => {
    if (web) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const [chunk, siblings] = await Promise.all([
          api.getChunk(target.chunkId),
          api.documentChunks(target.documentId, 200, 0),
        ]);
        if (cancelled) return;
        setDetail(chunk);
        setChunks(siblings.length ? siblings : [chunk]);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load source");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [target.chunkId, target.documentId, web]);

  useEffect(() => {
    if (loading || web) return;
    const el = highlightRef.current ?? document.getElementById(`chunk-${target.chunkId}`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [loading, chunks, target.chunkId, web]);

  const title = detail?.document_name || target.documentName || "Source";

  return (
    <Modal title={title} onClose={onClose} wide={!web}>
      {web ? (
        <div>
          <dl className="kv">
            {(target.page != null || target.section) && (
              <>
                <dt>Page</dt>
                <dd>{target.page ?? "—"}</dd>
                <dt>Section</dt>
                <dd>{target.section || "—"}</dd>
              </>
            )}
            {target.sourceUrl && (
              <>
                <dt>URL</dt>
                <dd>
                  <a href={target.sourceUrl} target="_blank" rel="noreferrer">
                    {target.sourceUrl}
                  </a>
                </dd>
              </>
            )}
          </dl>
          {target.snippet && (
            <div className="card" style={{ marginTop: 14, background: "var(--bg-inset)" }}>
              {target.snippet}
            </div>
          )}
        </div>
      ) : (
        <div>
          <div className="row" style={{ gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
            {(detail?.page_start ?? target.page) != null && (
              <span className="badge">p.{detail?.page_start ?? target.page}</span>
            )}
            {(detail?.section_path || target.section) && (
              <span className="faint" style={{ fontSize: 12 }}>
                {detail?.section_path || target.section}
              </span>
            )}
            <a
              className="btn ghost small"
              style={{ marginLeft: "auto" }}
              href={api.documentRawUrl(target.documentId)}
              target="_blank"
              rel="noreferrer"
            >
              Open original
            </a>
          </div>

          {loading && <p className="dim">Loading document chunks…</p>}
          {error && <div className="abstained-banner" style={{ color: "var(--red)" }}>{error}</div>}

          {!loading && !error && (
            <div className="source-viewer-body">
              {chunks.map((chunk) => {
                const highlighted = chunk.id === target.chunkId;
                return (
                  <div
                    key={chunk.id}
                    id={`chunk-${chunk.id}`}
                    ref={highlighted ? highlightRef : undefined}
                    className={`source-chunk${highlighted ? " highlight" : ""}`}
                  >
                    <div className="chunk-meta">
                      <span className="mono">#{chunk.chunk_index}</span>
                      {chunk.page_start != null && <span>p.{chunk.page_start}</span>}
                      {chunk.heading && <span>{chunk.heading}</span>}
                      {highlighted && <span className="badge accent">cited</span>}
                    </div>
                    <div style={{ whiteSpace: "pre-wrap", fontSize: 13, lineHeight: 1.55 }}>
                      {chunk.content}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
