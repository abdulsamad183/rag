import type {
  AppConfig,
  ChatRequestBody,
  ChatResponse,
  ChunkDetail,
  ChunkRow,
  Collection,
  Conversation,
  ConversationDetail,
  Dataset,
  Document,
  DocumentVersion,
  EvalQuestion,
  EvalResult,
  EvalRun,
  GraphData,
  HealthReport,
  Provider,
  RetrievalStats,
  RunComparison,
  TraceDetail,
  TraceSummary,
  TraceStep,
  UploadResult,
} from "./types";

const BASE = "/api/v1";

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers:
      init?.body && !(init.body instanceof FormData)
        ? { "Content-Type": "application/json", ...init?.headers }
        : init?.headers,
    ...init,
  });
  if (!response.ok) {
    let code = "http_error";
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      code = body?.error?.code ?? code;
      message = body?.error?.message ?? message;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, code, message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  ready: () => request<HealthReport>("/ready"),
  config: () => request<AppConfig>("/config"),
  providers: () => request<Provider[]>("/providers"),

  listCollections: () => request<Collection[]>("/collections"),
  getCollection: (id: string) => request<Collection>(`/collections/${id}`),
  createCollection: (body: Record<string, unknown>) =>
    request<Collection>("/collections", { method: "POST", body: JSON.stringify(body) }),
  updateCollection: (id: string, body: Record<string, unknown>) =>
    request<Collection>(`/collections/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteCollection: (id: string) =>
    request<{ ok: boolean }>(`/collections/${id}`, { method: "DELETE" }),

  listDocuments: (collectionId: string) =>
    request<Document[]>(`/collections/${collectionId}/documents`),
  getDocument: (id: string) => request<Document>(`/documents/${id}`),
  uploadDocument: (collectionId: string, file: File, meta?: Record<string, unknown>) => {
    const form = new FormData();
    form.append("file", file);
    if (meta && Object.keys(meta).length) form.append("meta", JSON.stringify(meta));
    return request<UploadResult>(`/collections/${collectionId}/documents`, {
      method: "POST",
      body: form,
    });
  },
  documentChunks: (id: string, limit = 50, offset = 0) =>
    request<ChunkRow[]>(`/documents/${id}/chunks?limit=${limit}&offset=${offset}`),
  getChunk: (id: string) => request<ChunkDetail>(`/chunks/${id}`),
  documentVersions: (id: string) => request<DocumentVersion[]>(`/documents/${id}/versions`),
  reingestDocument: (id: string) =>
    request<{ ok: boolean }>(`/documents/${id}/reingest`, { method: "POST" }),
  summarizeDocument: (id: string) =>
    request<{ summary: string }>(`/documents/${id}/summarize`, { method: "POST" }),
  deleteDocument: (id: string) =>
    request<{ ok: boolean }>(`/documents/${id}`, { method: "DELETE" }),
  documentRawUrl: (id: string) => `${BASE}/documents/${id}/raw`,

  chat: (body: ChatRequestBody) =>
    request<ChatResponse>("/chat", { method: "POST", body: JSON.stringify(body) }),

  listConversations: () => request<Conversation[]>("/conversations"),
  getConversation: (id: string) => request<ConversationDetail>(`/conversations/${id}`),
  deleteConversation: (id: string) =>
    request<{ ok: boolean }>(`/conversations/${id}`, { method: "DELETE" }),
  exportConversationUrl: (id: string, format: "markdown" | "json") =>
    `${BASE}/conversations/${id}/export?format=${format}`,

  listTraces: (limit = 50) => request<TraceSummary[]>(`/retrieval/traces?limit=${limit}`),
  getTrace: (id: string) => request<TraceDetail>(`/retrieval/${id}`),
  retrievalStats: (days: 1 | 7 | 30 = 7) =>
    request<RetrievalStats>(`/retrieval/stats?days=${days}`),

  listDatasets: () => request<Dataset[]>("/evaluations/datasets"),
  uploadDataset: (name: string, description: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    form.append("name", name);
    form.append("description", description);
    return request<Dataset>("/evaluations/datasets", { method: "POST", body: form });
  },
  deleteDataset: (id: string) =>
    request<{ ok: boolean }>(`/evaluations/datasets/${id}`, { method: "DELETE" }),
  datasetQuestions: (id: string) => request<EvalQuestion[]>(`/evaluations/datasets/${id}/questions`),
  listRuns: (datasetId?: string) =>
    request<EvalRun[]>(
      datasetId ? `/evaluations/runs?dataset_id=${datasetId}` : "/evaluations/runs",
    ),
  createRun: (datasetId: string, body: Record<string, unknown>) =>
    request<EvalRun>(`/evaluations/datasets/${datasetId}/runs`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getRun: (id: string) => request<EvalRun>(`/evaluations/runs/${id}`),
  runResults: (id: string) => request<EvalResult[]>(`/evaluations/runs/${id}/results`),
  compareRuns: (ids: string[]) =>
    request<RunComparison>(`/evaluations/compare?run_ids=${ids.join(",")}`),
  exportRunUrl: (id: string, format: "csv" | "json") =>
    `${BASE}/evaluations/runs/${id}/export?format=${format}`,

  collectionGraph: (id: string) => request<GraphData>(`/graph/collections/${id}`),
  extractGraph: (documentId: string) =>
    request<{ ok: boolean }>(`/graph/documents/${documentId}/extract`, { method: "POST" }),
};

export interface StreamHandlers {
  onStatus?: (stage: string) => void;
  onStep?: (step: TraceStep) => void;
  onMeta?: (meta: { conversation_id: string }) => void;
  onToken: (text: string) => void;
  onFinal: (response: ChatResponse) => void;
  onError: (message: string) => void;
  onAbort?: () => void;
}

/** POST /chat/stream and dispatch SSE events. Returns an abort function. */
export function streamChat(body: ChatRequestBody, handlers: StreamHandlers): () => void {
  const controller = new AbortController();

  (async () => {
    let response: Response;
    try {
      response = await fetch(`${BASE}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
    } catch {
      if (controller.signal.aborted) {
        handlers.onAbort?.();
      } else {
        handlers.onError("Could not reach the server.");
      }
      return;
    }
    if (!response.ok || !response.body) {
      try {
        const err = await response.json();
        handlers.onError(err?.error?.message ?? `Request failed (${response.status})`);
      } catch {
        handlers.onError(`Request failed (${response.status})`);
      }
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let currentEvent = "";

    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (line.startsWith("event:")) {
            currentEvent = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            const payload = JSON.parse(line.slice(5).trim());
            switch (currentEvent) {
              case "status":
                handlers.onStatus?.(payload.stage);
                break;
              case "step":
                handlers.onStep?.(payload as TraceStep);
                break;
              case "meta":
                handlers.onMeta?.(payload);
                break;
              case "token":
                handlers.onToken(payload.text);
                break;
              case "final":
                handlers.onFinal(payload);
                break;
              case "error":
                handlers.onError(payload.message ?? "Chat failed.");
                break;
            }
          }
        }
      }
    } catch {
      if (controller.signal.aborted) {
        handlers.onAbort?.();
      } else {
        handlers.onError("Stream interrupted.");
      }
    }
  })();

  return () => controller.abort();
}
