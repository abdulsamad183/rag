// Mirrors backend Pydantic schemas (app/schemas/*).

export interface ModelInfo {
  name: string;
  label: string;
  context_window?: number;
  capabilities?: Record<string, boolean>;
  installed?: boolean | null;
}

export interface Provider {
  name: string;
  label: string;
  configured: boolean;
  default_model: string;
  models: ModelInfo[];
  embedding_models: { name: string; dimension: number }[];
  is_local: boolean;
  note: string;
}

export interface AppConfig {
  default_provider: string;
  default_embedding_provider: string;
  local_mode: boolean;
  retrieval_defaults: Record<string, number | string>;
  chunking_strategies: string[];
  retrieval_strategies: string[];
  rerankers: string[];
  modes: string[];
  web_search_enabled: boolean;
}

export interface Collection {
  id: string;
  name: string;
  description: string;
  embedding_provider: string;
  embedding_model: string;
  embedding_dimension: number;
  chunking_config: Record<string, unknown>;
  retrieval_config: Record<string, unknown>;
  graph_enabled: boolean;
  temporal_enabled: boolean;
  version: number;
  created_at: string;
  document_count: number;
  chunk_count: number;
}

export interface Document {
  id: string;
  collection_id: string;
  filename: string;
  title: string;
  source_type: string;
  status: string;
  progress: number;
  error: string;
  page_count: number;
  chunk_count: number;
  current_version: number;
  size_bytes: number;
  content_hash: string;
  meta: Record<string, unknown>;
  published_at: string | null;
  valid_from: string | null;
  valid_to: string | null;
  trust: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentVersion {
  id: string;
  version: number;
  content_hash: string;
  size_bytes: number;
  created_at: string;
}

export interface ChunkRow {
  id: string;
  document_id: string;
  chunk_index: number;
  content: string;
  heading: string;
  section_path: string;
  page_start: number | null;
  page_end: number | null;
  level: string;
  token_count: number;
  meta: Record<string, unknown>;
}

export interface ChunkDetail extends ChunkRow {
  collection_id: string;
  document_name: string;
  source_type: string;
}

export interface UploadResult {
  document: Document;
  is_new_content: boolean;
  message: string;
}

export interface Citation {
  marker: number;
  chunk_id: string;
  document_id: string;
  document_name: string;
  page: number | null;
  section: string;
  snippet: string;
  source_url: string;
  source_type?: string;
  relevance_score: number;
}

export interface Evidence {
  marker: number;
  chunk_id: string;
  document_id: string;
  document_name: string;
  content: string;
  score: number;
  scores: Record<string, number>;
  source_type: string;
  page: number | null;
  section: string;
  trust: number;
  url: string;
}

export interface Confidence {
  score: number;
  level: "high" | "medium" | "low" | "insufficient";
  signals: Record<string, number>;
  weights: Record<string, number>;
}

export interface Verification {
  claims: {
    text: string;
    verdict: string;
    evidence_ids: number[];
    note?: string;
  }[];
  supported: number;
  total: number;
  support_ratio: number;
  contradictions: Record<string, unknown>[];
  error: string;
}

export type ChatMode = "fast" | "balanced" | "adaptive" | "deep" | "research";
export type ChatScope = "kb" | "kb_web" | "web";

export interface ChatRequestBody {
  message: string;
  collection_ids: string[];
  conversation_id?: string | null;
  mode: ChatMode;
  provider?: string | null;
  model?: string | null;
  temperature?: number;
  max_tokens?: number;
  max_context_tokens?: number;
  top_k?: number;
  rerank_top_k?: number;
  retrieval_strategy?: string | null;
  reranker?: string | null;
  max_hops?: number;
  confidence_threshold?: number;
  allow_fallback?: boolean;
  scope?: ChatScope;
  debug?: boolean;
}

export interface Usage {
  prompt_tokens?: number;
  completion_tokens?: number;
  embedding_tokens?: number;
  llm_calls?: number;
  estimated_cost_usd?: number;
  retries?: number;
}

export interface ChatResponse {
  conversation_id: string;
  message_id: string;
  trace_id: string;
  answer: string;
  abstained: boolean;
  strategy: string;
  mode: string;
  provider: string;
  model: string;
  confidence: Confidence;
  citations: Citation[];
  evidence: Evidence[];
  verification: Verification | null;
  queries_used: string[];
  correction_rounds: number;
  fallback_used: string;
  usage: Usage;
  latency_ms: number;
  debug_steps?: TraceStep[] | null;
}

export interface Conversation {
  id: string;
  title: string;
  collection_ids: string[];
  summary: string;
  created_at: string;
  updated_at: string;
}

export interface MessageMeta {
  confidence?: Confidence;
  strategy?: string;
  mode?: string;
  provider?: string;
  model?: string;
  abstained?: boolean;
  latency_ms?: number;
  usage?: Usage;
  verification?: { supported: number; total: number; contradictions?: number };
  evidence_count?: number;
  correction_rounds?: number;
  fallback_used?: string;
}

export interface Message {
  id: string;
  role: string;
  content: string;
  trace_id: string | null;
  meta: MessageMeta;
  citations: Citation[];
  created_at: string;
}

export interface ConversationDetail {
  conversation: Conversation;
  messages: Message[];
}

export interface TraceStep {
  name: string;
  status: string;
  latency_ms: number;
  payload: Record<string, unknown>;
}

export interface TraceSummary {
  id: string;
  request_id: string;
  query: string;
  mode: string;
  strategy: string;
  provider: string;
  model: string;
  abstained: boolean;
  latency_ms: number;
  created_at: string;
  confidence: Partial<Confidence> | Record<string, unknown>;
}

export interface TraceDetail extends TraceSummary {
  conversation_id: string | null;
  query_analysis: Record<string, unknown>;
  steps: TraceStep[];
  retrieved: Record<string, unknown>[];
  verification: Record<string, unknown>;
  usage: Usage;
  collection_ids?: string[];
  answer: string;
  error: string;
}

export interface RetrievalStats {
  days: number;
  totals: {
    queries: number;
    abstain_rate: number;
    prompt_tokens: number;
    completion_tokens: number;
    estimated_cost_usd: number;
    latency_ms: { mean: number; p50: number; p95: number };
  };
  by_provider: {
    provider: string;
    queries: number;
    estimated_cost_usd: number;
    prompt_tokens: number;
    completion_tokens: number;
    latency_ms_p50: number;
    latency_ms_p95: number;
    abstain_rate: number;
  }[];
  by_collection: {
    collection_id: string;
    queries: number;
    estimated_cost_usd: number;
    latency_ms_p50: number;
    latency_ms_p95: number;
    abstain_rate: number;
  }[];
}

export interface Dataset {
  id: string;
  name: string;
  description: string;
  question_count: number;
  created_at: string;
}

export interface EvalQuestion {
  id: string;
  question: string;
  expected_answer: string;
  relevant_documents: string[];
  relevant_chunks: string[];
  question_type: string;
  answerable: boolean;
}

export interface EvalMetrics {
  ground_truth?: Record<string, number>;
  llm_judge?: Record<string, number>;
  by_question_type?: Record<string, Record<string, number>>;
  failures?: Record<string, number>;
  abstention_accuracy?: number | null;
  latency_ms?: { mean: number; p95: number };
  total_tokens?: number;
  estimated_cost_usd?: number;
  questions?: number;
  errors?: number;
}

export interface EvalRun {
  id: string;
  dataset_id: string;
  name: string;
  config: Record<string, unknown>;
  status: string;
  progress: number;
  metrics: EvalMetrics;
  error: string;
  created_at: string;
  completed_at: string | null;
}

export interface EvalResult {
  id: string;
  question_id: string;
  answer: string;
  abstained: boolean;
  retrieved: Record<string, unknown>[];
  citations: Record<string, unknown>[];
  metrics: Record<string, unknown>;
  failure_category: string;
  latency_ms: number;
  error: string;
  trace_id: string | null;
  question: string;
  expected_answer: string;
  question_type: string;
  answerable: boolean;
}

export interface RunComparison {
  runs: EvalRun[];
  metric_table: Record<string, Record<string, number | null>>;
}

export interface GraphData {
  nodes: { id: string; name: string; type: string; description: string }[];
  edges: { id: string; source: string; target: string; relation: string; weight: number }[];
}

export interface HealthReport {
  ready: boolean;
  checks: {
    database: { ok: boolean; error?: string };
    redis: { ok: boolean; note?: string };
    providers: Record<string, { configured: boolean }>;
    storage: { ok: boolean };
    local_mode?: boolean;
  };
}
