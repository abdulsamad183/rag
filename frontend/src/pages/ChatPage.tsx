import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, api, streamChat } from "../api/client";
import type {
  ChatMode,
  ChatRequestBody,
  ChatResponse,
  ChatScope,
  Citation,
  Conversation,
  Evidence,
  Message,
  TraceStep,
} from "../api/types";
import { ConfidenceBadge } from "../components/Confidence";
import EmptyState from "../components/EmptyState";
import EvidencePanel from "../components/EvidencePanel";
import Markdown from "../components/Markdown";
import Modal from "../components/Modal";
import ProviderModelSelect from "../components/ProviderModelSelect";
import TraceSteps from "../components/TraceSteps";
import { useApp } from "../state/AppContext";

const MODE_HINT: Record<ChatMode, string> = {
  fast: "Vector retrieval, single LLM call",
  balanced: "Hybrid + rerank",
  adaptive: "Router picks the strategy",
  deep: "Multi-hop + verification",
  research: "Graph, contradictions, self-correction",
};

const STAGE_LABEL: Record<string, string> = {
  analyzing: "Understanding the question…",
  retrieving: "Retrieving evidence…",
  reranking: "Reranking candidates…",
  generating: "Writing an answer…",
  verifying: "Verifying claims…",
  correcting: "Retrieving more evidence…",
  searching_web: "Searching the web…",
};

interface ChatTurn {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  response?: ChatResponse;
  citations?: Citation[];
  traceId?: string | null;
  liveSteps?: TraceStep[];
}

function citationsToEvidence(citations: Citation[]): Evidence[] {
  return citations.map((c) => ({
    marker: c.marker,
    chunk_id: c.chunk_id,
    document_id: c.document_id,
    document_name: c.document_name,
    content: c.snippet,
    score: c.relevance_score,
    scores: {},
    source_type: c.source_type || (c.source_url?.startsWith("http") ? "web" : ""),
    page: c.page,
    section: c.section,
    trust: 0.6,
    url: c.source_url,
  }));
}

function messageToResponse(message: Message): ChatResponse | undefined {
  if (message.role !== "assistant") return undefined;
  const meta = message.meta ?? {};
  const citations = message.citations ?? [];
  return {
    conversation_id: "",
    message_id: message.id,
    trace_id: message.trace_id ?? "",
    answer: message.content,
    abstained: Boolean(meta.abstained),
    strategy: meta.strategy ?? "",
    mode: meta.mode ?? "",
    provider: meta.provider ?? "",
    model: meta.model ?? "",
    confidence: meta.confidence ?? { score: 0, level: "insufficient", signals: {}, weights: {} },
    citations,
    evidence: citationsToEvidence(citations),
    verification: meta.verification
      ? {
          claims: [],
          supported: meta.verification.supported,
          total: meta.verification.total,
          support_ratio:
            meta.verification.total > 0
              ? meta.verification.supported / meta.verification.total
              : 1,
          contradictions: [],
          error: "",
        }
      : null,
    queries_used: [],
    correction_rounds: meta.correction_rounds ?? 0,
    fallback_used: meta.fallback_used ?? "",
    usage: meta.usage ?? {},
    latency_ms: meta.latency_ms ?? 0,
  };
}

function loadPref<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export default function ChatPage() {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const { config, providers, collections, toast, backendDown } = useApp();

  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState("");
  const [error, setError] = useState("");
  const [panel, setPanel] = useState<ChatResponse | null>(null);
  const [highlight, setHighlight] = useState<number | null>(null);
  const [source, setSource] = useState<Evidence | Citation | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const [collectionIds, setCollectionIds] = useState<string[]>(() => loadPref("rag.cols", []));
  const [mode, setMode] = useState<ChatMode>(() => loadPref("rag.mode", "adaptive"));
  const [scope, setScope] = useState<ChatScope>(() => loadPref("rag.scope", "kb"));
  const [provider, setProvider] = useState(() => loadPref("rag.provider", ""));
  const [model, setModel] = useState(() => loadPref("rag.model", ""));
  const [temperature, setTemperature] = useState(0.1);
  const [topK, setTopK] = useState(10);
  const [rerankTopK, setRerankTopK] = useState(8);
  const [strategy, setStrategy] = useState("");
  const [reranker, setReranker] = useState("");
  const [maxHops, setMaxHops] = useState(3);
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.35);
  const [allowFallback, setAllowFallback] = useState(false);
  const [debug, setDebug] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<(() => void) | null>(null);
  const convIdRef = useRef<string | undefined>(conversationId);

  convIdRef.current = conversationId;

  useEffect(() => {
    localStorage.setItem("rag.cols", JSON.stringify(collectionIds));
    localStorage.setItem("rag.mode", JSON.stringify(mode));
    localStorage.setItem("rag.provider", JSON.stringify(provider));
    localStorage.setItem("rag.model", JSON.stringify(model));
    localStorage.setItem("rag.scope", JSON.stringify(scope));
  }, [collectionIds, mode, provider, model, scope]);

  useEffect(() => {
    if (!provider && (config || providers.length)) {
      const name = config?.default_provider || providers.find((p) => p.configured)?.name || "";
      const match = providers.find((p) => p.name === name && p.configured) ?? providers.find((p) => p.configured);
      if (match) {
        setProvider(match.name);
        setModel(match.default_model || match.models[0]?.name || "");
      }
    }
  }, [config, providers, provider]);

  useEffect(() => {
    if (!collectionIds.length && collections.length) {
      setCollectionIds([collections[0].id]);
    }
  }, [collections, collectionIds.length]);

  useEffect(() => {
    if (!config?.web_search_enabled && scope !== "kb") {
      setScope("kb");
    }
  }, [config?.web_search_enabled, scope]);

  useEffect(() => {
    if (config?.retrieval_defaults) {
      const d = config.retrieval_defaults;
      if (typeof d.top_k === "number") setTopK(d.top_k);
      if (typeof d.rerank_top_k === "number") setRerankTopK(d.rerank_top_k);
      if (typeof d.temperature === "number") setTemperature(d.temperature);
      if (typeof d.max_hops === "number") setMaxHops(d.max_hops);
      if (typeof d.confidence_threshold === "number") setConfidenceThreshold(d.confidence_threshold);
    }
  }, [config]);

  const refreshConversations = useCallback(async () => {
    try {
      setConversations(await api.listConversations());
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    void refreshConversations();
  }, [refreshConversations]);

  useEffect(() => {
    if (!conversationId) {
      setTurns([]);
      setPanel(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const detail = await api.getConversation(conversationId);
        if (cancelled) return;
        setTurns(
          detail.messages.map((m) => ({
            id: m.id,
            role: m.role as "user" | "assistant",
            content: m.content,
            response: messageToResponse(m),
            citations: m.citations,
            traceId: m.trace_id,
          })),
        );
        if (detail.conversation.collection_ids.length) {
          setCollectionIds(detail.conversation.collection_ids);
        }
        const last = [...detail.messages].reverse().find((m) => m.role === "assistant");
        if (last) setPanel(messageToResponse(last) ?? null);
      } catch (err) {
        if (!cancelled) toast(err instanceof ApiError ? err.message : "Could not load conversation", "error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [conversationId, toast]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns, stage]);

  const selectedCollections = useMemo(
    () => collections.filter((c) => collectionIds.includes(c.id)),
    [collections, collectionIds],
  );

  function toggleCollection(id: string) {
    setCollectionIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  function onCite(marker: number) {
    setHighlight(marker);
    const found = panel?.evidence.find((e) => e.marker === marker);
    if (found) {
      document.getElementById(`evidence-${marker}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    const cite = panel?.citations.find((c) => c.marker === marker);
    if (cite) setSource(cite);
  }

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    if (scope !== "web" && !collectionIds.length) {
      toast("Select at least one collection.", "error");
      return;
    }
    setError("");
    setInput("");
    setBusy(true);
    setStage("analyzing");
    const userTurn: ChatTurn = { id: `u-${Date.now()}`, role: "user", content: text };
    const assistantId = `a-${Date.now()}`;
    setTurns((prev) => [...prev, userTurn, { id: assistantId, role: "assistant", content: "", streaming: true }]);

    const body: ChatRequestBody = {
      message: text,
      collection_ids: collectionIds,
      conversation_id: convIdRef.current ?? null,
      mode,
      provider: provider || null,
      model: model || null,
      scope,
      debug,
    };
    if (showAdvanced) {
      body.temperature = temperature;
      body.top_k = topK;
      body.rerank_top_k = rerankTopK;
      body.max_hops = maxHops;
      body.confidence_threshold = confidenceThreshold;
      body.allow_fallback = allowFallback;
      if (strategy) body.retrieval_strategy = strategy;
      if (reranker) body.reranker = reranker;
    }

    abortRef.current = streamChat(body, {
      onStatus: (s) => setStage(s),
      onStep: (step) => {
        setTurns((prev) =>
          prev.map((t) =>
            t.id === assistantId ? { ...t, liveSteps: [...(t.liveSteps ?? []), step] } : t,
          ),
        );
      },
      onMeta: ({ conversation_id }) => {
        if (!convIdRef.current) navigate(`/chat/${conversation_id}`, { replace: true });
      },
      onToken: (delta) => {
        setTurns((prev) =>
          prev.map((t) => (t.id === assistantId ? { ...t, content: t.content + delta } : t)),
        );
      },
      onFinal: (response) => {
        setTurns((prev) =>
          prev.map((t) =>
            t.id === assistantId
              ? {
                  id: response.message_id,
                  role: "assistant",
                  content: response.answer,
                  response,
                  citations: response.citations,
                  traceId: response.trace_id,
                  liveSteps: response.debug_steps ?? t.liveSteps,
                }
              : t,
          ),
        );
        setPanel(response);
        setBusy(false);
        setStage("");
        void refreshConversations();
      },
      onError: (message) => {
        setError(message);
        setBusy(false);
        setStage("");
        setTurns((prev) => prev.filter((t) => t.id !== assistantId && t.id !== userTurn.id));
        setInput(text);
      },
    });
  }

  function newChat() {
    abortRef.current?.();
    setTurns([]);
    setPanel(null);
    setError("");
    navigate("/chat");
  }

  async function removeConversation(id: string) {
    if (!confirm("Delete this conversation?")) return;
    await api.deleteConversation(id);
    await refreshConversations();
    if (conversationId === id) newChat();
  }

  const webEnabled = Boolean(config?.web_search_enabled);
  const composerDisabled = busy || backendDown || (scope !== "web" && !collectionIds.length);

  return (
    <div className="chat-layout">
      <aside className="conv-sidebar">
        <div className="row spread" style={{ padding: "4px 4px 10px" }}>
          <span className="faint" style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.06em" }}>
            CONVERSATIONS
          </span>
          <button className="btn ghost small" onClick={newChat}>
            New
          </button>
        </div>
        <div style={{ overflowY: "auto", flex: 1 }}>
          {conversations.map((c) => (
            <div
              key={c.id}
              className={`chat-history-item${c.id === conversationId ? " active" : ""}`}
              onClick={() => navigate(`/chat/${c.id}`)}
            >
              <div className="row spread">
                <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{c.title || "Untitled"}</span>
                <button
                  className="btn ghost small"
                  style={{ padding: "0 4px", opacity: 0.5 }}
                  onClick={(e) => {
                    e.stopPropagation();
                    void removeConversation(c.id);
                  }}
                >
                  ×
                </button>
              </div>
            </div>
          ))}
        </div>
      </aside>

      <div className="chat-main">
        <div className="chat-scroll" ref={scrollRef}>
          <div className="chat-column">
            {!turns.length && (
              <EmptyState icon="◈" title="Ask with evidence, not guesses">
                <p>
                  Select a collection, then ask a question. The engine retrieves, reranks, verifies
                  claims, and cites sources — or abstains when evidence is insufficient.
                </p>
              </EmptyState>
            )}
            {turns.map((turn) => (
              <div key={turn.id} className={`msg ${turn.role}`}>
                <div className="who">{turn.role === "user" ? "You" : "Assistant"}</div>
                {turn.role === "user" ? (
                  <div className="bubble">{turn.content}</div>
                ) : (
                  <div className="bubble">
                    {turn.response?.abstained && (
                      <div className="abstained-banner" style={{ marginBottom: 10 }}>
                        Insufficient evidence — the system declined to guess.
                      </div>
                    )}
                    {turn.content ? (
                      <Markdown text={turn.content} onCite={onCite} />
                    ) : (
                      <span className="dim">…</span>
                    )}
                    {(turn.streaming || (turn.liveSteps && turn.liveSteps.length > 0)) && (
                      <div className="live-trace">
                        <div className="live-trace-head">
                          <span>Pipeline</span>
                          {turn.streaming ? (
                            <span className="badge accent">live</span>
                          ) : (
                            <span className="faint">{turn.liveSteps?.length ?? 0} steps</span>
                          )}
                        </div>
                        <TraceSteps
                          steps={turn.liveSteps ?? []}
                          runningLabel={
                            turn.streaming ? (STAGE_LABEL[stage] ?? "Working…") : undefined
                          }
                          openLast={Boolean(turn.streaming)}
                        />
                      </div>
                    )}
                    {turn.response && (
                      <div className="meta-row">
                        <ConfidenceBadge confidence={turn.response.confidence} />
                        {turn.response.strategy && (
                          <span className="badge">{turn.response.strategy}</span>
                        )}
                        <span className="faint">
                          {turn.response.evidence.length} chunks
                          {turn.response.verification && turn.response.verification.total > 0
                            ? ` · claims ${turn.response.verification.supported}/${turn.response.verification.total}`
                            : ""}
                        </span>
                        <button className="btn ghost small" onClick={() => setPanel(turn.response ?? null)}>
                          Evidence
                        </button>
                        {turn.traceId && (
                          <Link className="btn ghost small" to={`/traces/${turn.traceId}`}>
                            Trace
                          </Link>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
            {error && <div className="abstained-banner" style={{ color: "var(--red)" }}>{error}</div>}
          </div>
        </div>

        <div className="composer-wrap">
          <div className="composer">
            <textarea
              rows={2}
              placeholder={
                scope === "web"
                  ? "Ask the public web…"
                  : selectedCollections.length
                    ? `Ask ${selectedCollections.map((c) => c.name).join(", ")}…`
                    : "Select a collection first"
              }
              value={input}
              disabled={busy}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
            />
            <div className="controls">
              <select
                className="mini-select"
                value={mode}
                title={MODE_HINT[mode]}
                onChange={(e) => setMode(e.target.value as ChatMode)}
              >
                {(config?.modes ?? ["fast", "balanced", "adaptive", "deep", "research"]).map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
              <select
                className="mini-select"
                value={scope}
                title={
                  webEnabled
                    ? "Where to search"
                    : "Set WEB_SEARCH_PROVIDER=ddg in .env, then restart the API"
                }
                onChange={(e) => setScope(e.target.value as ChatScope)}
              >
                <option value="kb">KB only</option>
                <option value="kb_web" disabled={!webEnabled}>
                  KB + Web
                </option>
                <option value="web" disabled={!webEnabled}>
                  Web only
                </option>
              </select>
              <ProviderModelSelect
                compact
                providers={providers}
                provider={provider}
                model={model}
                onProvider={setProvider}
                onModel={setModel}
              />
              <div className="chip-row">
                {collections.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    className={`chip${collectionIds.includes(c.id) ? " on" : ""}`}
                    onClick={() => toggleCollection(c.id)}
                  >
                    {c.name}
                  </button>
                ))}
              </div>
              <button className="btn ghost small" type="button" onClick={() => setShowAdvanced(!showAdvanced)}>
                {showAdvanced ? "Basic" : "Advanced"}
              </button>
              <button className="send-btn" disabled={composerDisabled || !input.trim()} onClick={() => void send()}>
                ↑
              </button>
            </div>
            {showAdvanced && (
              <div className="advanced-grid">
                <label>
                  Temperature
                  <input
                    className="input"
                    type="number"
                    min={0}
                    max={2}
                    step={0.1}
                    value={temperature}
                    onChange={(e) => setTemperature(Number(e.target.value))}
                  />
                </label>
                <label>
                  Top-k
                  <input
                    className="input"
                    type="number"
                    min={1}
                    max={50}
                    value={topK}
                    onChange={(e) => setTopK(Number(e.target.value))}
                  />
                </label>
                <label>
                  Rerank top-k
                  <input
                    className="input"
                    type="number"
                    min={1}
                    max={30}
                    value={rerankTopK}
                    onChange={(e) => setRerankTopK(Number(e.target.value))}
                  />
                </label>
                <label>
                  Max hops
                  <input
                    className="input"
                    type="number"
                    min={1}
                    max={5}
                    value={maxHops}
                    onChange={(e) => setMaxHops(Number(e.target.value))}
                  />
                </label>
                <label>
                  Strategy
                  <select className="select" value={strategy} onChange={(e) => setStrategy(e.target.value)}>
                    <option value="">Profile default</option>
                    {(config?.retrieval_strategies ?? []).map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Reranker
                  <select className="select" value={reranker} onChange={(e) => setReranker(e.target.value)}>
                    <option value="">Profile default</option>
                    {(config?.rerankers ?? ["none", "lexical", "llm"]).map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Abstain below
                  <input
                    className="input"
                    type="number"
                    min={0}
                    max={1}
                    step={0.05}
                    value={confidenceThreshold}
                    onChange={(e) => setConfidenceThreshold(Number(e.target.value))}
                  />
                </label>
                <label className="row" style={{ alignItems: "center", gap: 8, marginTop: 18 }}>
                  <input
                    type="checkbox"
                    checked={allowFallback}
                    onChange={(e) => setAllowFallback(e.target.checked)}
                  />
                  Provider fallback
                </label>
                <label className="row" style={{ alignItems: "center", gap: 8, marginTop: 18 }}>
                  <input type="checkbox" checked={debug} onChange={(e) => setDebug(e.target.checked)} />
                  Debug mode
                </label>
              </div>
            )}
            {conversationId && (
              <div className="row" style={{ justifyContent: "flex-end", gap: 8 }}>
                <a className="btn ghost small" href={api.exportConversationUrl(conversationId, "markdown")}>
                  Export MD
                </a>
                <a className="btn ghost small" href={api.exportConversationUrl(conversationId, "json")}>
                  Export JSON
                </a>
              </div>
            )}
          </div>
        </div>
      </div>

      {panel && (
        <EvidencePanel
          response={panel}
          highlightMarker={highlight}
        />
      )}

      {source && (
        <Modal title={source.document_name} onClose={() => setSource(null)}>
          <dl className="kv">
            <dt>Page</dt>
            <dd>{source.page ?? "—"}</dd>
            <dt>Section</dt>
            <dd>{source.section || "—"}</dd>
            {"relevance_score" in source && (
              <>
                <dt>Relevance</dt>
                <dd>{source.relevance_score.toFixed(3)}</dd>
              </>
            )}
            {("source_url" in source ? source.source_url : source.url) && (
              <>
                <dt>URL</dt>
                <dd>
                  <a
                    href={"source_url" in source ? source.source_url : source.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {"source_url" in source ? source.source_url : source.url}
                  </a>
                </dd>
              </>
            )}
          </dl>
          <div className="card" style={{ marginTop: 14, background: "var(--bg-inset)" }}>
            {"snippet" in source ? source.snippet : "content" in source ? source.content : ""}
          </div>
        </Modal>
      )}
    </div>
  );
}
