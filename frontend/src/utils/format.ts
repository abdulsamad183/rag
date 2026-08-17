export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatMs(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export function shortId(id: string): string {
  return id.replace(/-/g, "").slice(0, 8);
}

export function confidenceScore(value: unknown): number | null {
  if (value && typeof value === "object" && "score" in value) {
    const score = (value as { score?: unknown }).score;
    return typeof score === "number" ? score : null;
  }
  return null;
}

export function statusClass(status: string): string {
  if (status === "completed" || status === "ok" || status === "ready") return "green";
  if (status === "failed" || status === "error") return "red";
  if (status === "queued") return "";
  return "yellow";
}

export function ingestLabel(status: string): string {
  const labels: Record<string, string> = {
    queued: "Queued",
    parsing: "Parsing",
    chunking: "Chunking",
    embedding: "Embedding",
    indexing: "Indexing",
    completed: "Completed",
    failed: "Failed",
  };
  return labels[status] ?? status;
}
