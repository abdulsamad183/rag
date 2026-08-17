"""RAG pipeline orchestrator.

Execution graph (all steps observable, no hidden loops):

    query → contextualize → analyze → route → retrieve → rerank →
    evidence build → generate → claims → verify → (self-correct ≤ N) →
    contradictions → confidence → abstain-or-answer

Streaming: draft tokens stream out as generated; verification, citations and
confidence attach afterwards. Self-correction may replace the draft — the
final payload always carries the authoritative answer.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.config.profiles import Profile
from app.core.errors import ProviderAuthError, ProviderError, ProviderNotConfiguredError
from app.core.logging import get_logger
from app.embeddings.registry import CachingEmbedder
from app.llm.base import ChatMessage, GenerationParams, LLMProvider
from app.llm.registry import get_fallback_chain, get_llm, resolve_provider_model
from app.models import Collection, Message
from app.observability.tracing import TraceRecorder
from app.rag import prompts
from app.rag.claims import (
    VerificationReport,
    detect_contradictions,
    extract_claims,
    verify_claims,
)
from app.rag.confidence import ConfidenceReport, compute_confidence
from app.rag.evidence import EvidenceBuilder, EvidenceItem, render_evidence
from app.rag.memory import build_generation_context, contextualize_query
from app.rag.query_analysis import analyze_query
from app.reranking import get_reranker
from app.retrieval.base import Query, QueryFilters, RetrievalContext
from app.retrieval.fusion import deduplicate, reciprocal_rank_fusion
from app.retrieval.registry import get_strategy
from app.utils.text import term_coverage

logger = get_logger("pipeline")

_MARKER = re.compile(r"\[(\d{1,2})\]")
INSUFFICIENT_TOKEN = "INSUFFICIENT_EVIDENCE"
ABSTAIN_MESSAGE = (
    "I don't have enough evidence in the selected knowledge base to answer this reliably."
)

StreamCallback = Callable[[str], Awaitable[None]]


@dataclass
class PipelineParams:
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    max_context_tokens: int | None = None
    top_k: int | None = None
    rerank_top_k: int | None = None
    strategy: str | None = None          # explicit override; None → profile/router
    reranker: str | None = None          # none | lexical | llm
    max_hops: int | None = None
    confidence_threshold: float | None = None  # abstain below this
    allow_fallback: bool = False
    filters: QueryFilters = field(default_factory=QueryFilters)


@dataclass
class PipelineResult:
    answer: str
    abstained: bool
    strategy: str
    provider: str
    model: str
    analysis: dict[str, Any]
    evidence: list[EvidenceItem]
    citations: list[dict[str, Any]]
    verification: VerificationReport | None
    confidence: ConfidenceReport
    trace: TraceRecorder
    queries_used: list[str]
    correction_rounds: int = 0
    fallback_used: str = ""


class RAGPipeline:
    def __init__(
        self,
        session: AsyncSession,
        collections: list[Collection],
        profile: Profile,
        params: PipelineParams,
        embedder: CachingEmbedder,
        settings: Settings | None = None,
    ):
        self.session = session
        self.collections = collections
        self.profile = profile
        self.params = params
        self.embedder = embedder
        self.settings = settings or get_settings()
        self.trace = TraceRecorder()
        self.provider_name, self.model_name = resolve_provider_model(params.provider, params.model)
        self.llm: LLMProvider = get_llm(self.provider_name, self.model_name)
        self.fallback_used = ""

    # ------------------------------------------------------------------ run

    async def run(
        self,
        raw_query: str,
        history: list[Message] | None = None,
        summary: str = "",
        on_token: StreamCallback | None = None,
        on_status: StreamCallback | None = None,
    ) -> PipelineResult:
        history = history or []
        settings = self.settings

        async def status(stage: str) -> None:
            if on_status is not None:
                await on_status(stage)

        # 1. Conversation-aware query rewrite
        await status("analyzing")
        query_text = await contextualize_query(
            self.llm if self.profile.use_llm_query_analysis else None,
            raw_query, history, summary, self.trace,
        )

        # 2. Query understanding
        analysis = await analyze_query(
            query_text, self.llm, self.profile.use_llm_query_analysis, self.trace
        )

        # 3. Strategy selection + retrieval
        await status("retrieving")
        context = self._build_context(analysis)
        strategy_name = self.params.strategy or (
            "adaptive" if self.profile.default_strategy == "auto" else self.profile.default_strategy
        )
        graph_available = any(c.graph_enabled for c in self.collections)
        strategy = get_strategy(strategy_name, self.profile, graph_available)
        query = Query(text=query_text, filters=self._merge_filters(analysis), analysis=analysis)
        retrieval = await strategy.retrieve(query, context)

        # 4. Rerank
        top_k = self.params.rerank_top_k or settings.rerank_top_k
        candidates = retrieval.chunks
        rerank_ran = False
        if self.profile.use_reranker and candidates:
            await status("reranking")
            reranker_name = self.params.reranker or settings.reranker
            if reranker_name != "none":
                reranker = get_reranker(reranker_name, self.llm)
                with self.trace.step("rerank", reranker=reranker.name, pool=len(candidates)) as step:
                    candidates = await reranker.rerank(query_text, candidates, top_k)
                    step.payload["kept"] = len(candidates)
                rerank_ran = True
        else:
            candidates = candidates[: max(top_k, self.params.top_k or settings.top_k)]

        self.trace.set_retrieved([c.as_trace_dict() for c in retrieval.chunks[:30]])

        # 5. Evidence
        builder = EvidenceBuilder(
            max_context_tokens=self.params.max_context_tokens or settings.max_context_tokens
        )
        evidence = await builder.build(candidates, self.session, self.trace)

        if not evidence:
            return self._abstain_result(
                analysis, retrieval.strategy, retrieval.queries_used,
                reason="no relevant evidence retrieved",
            )

        # 6. Generate draft (streams when a callback is given)
        await status("generating")
        conversation_context = build_generation_context(history, summary)
        answer = await self._generate(query_text, evidence, conversation_context, on_token)

        # 7. Verification + self-correction
        verification: VerificationReport | None = None
        correction_rounds = 0
        if self.profile.verify_claims and not self._is_insufficient(answer):
            await status("verifying")
            verification = await self._verify(answer, evidence)
            max_rounds = min(self.profile.max_correction_rounds, settings.max_correction_rounds)
            while (
                verification is not None
                and verification.unsupported_critical
                and correction_rounds < max_rounds
            ):
                correction_rounds += 1
                await status("correcting")
                evidence, answer, verification = await self._self_correct(
                    query, evidence, verification, conversation_context, context
                )

        # 8. Contradiction analysis
        contradictions: list[dict[str, Any]] = []
        if self.profile.detect_contradictions and not self._is_insufficient(answer):
            contradictions = await detect_contradictions(self.llm, evidence, self.trace)
            if contradictions:
                self.trace.add_step("contradictions", count=len(contradictions), items=contradictions)
            if verification is not None:
                verification.contradictions = contradictions

        # 9. Confidence + abstention
        confidence = self._confidence(query_text, evidence, verification, rerank_ran, contradictions)
        abstain_threshold = (
            self.params.confidence_threshold
            if self.params.confidence_threshold is not None
            else settings.abstain_threshold
        )
        insufficient = self._is_insufficient(answer)
        abstained = insufficient or confidence.score < abstain_threshold
        if abstained:
            explanation = self._insufficient_explanation(answer) if insufficient else (
                f"Confidence {confidence.score:.2f} is below the abstention threshold "
                f"{abstain_threshold:.2f}."
            )
            answer = f"{ABSTAIN_MESSAGE} {explanation}".strip()
            self.trace.add_step(
                "abstention", triggered=True,
                reason="model_reported_insufficient" if insufficient else "low_confidence",
                confidence=confidence.score,
            )

        citations = [] if abstained else self._citations(answer, evidence)
        self.trace.add_step(
            "final", abstained=abstained, citations=len(citations),
            confidence=round(confidence.score, 3), level=confidence.level,
        )

        return PipelineResult(
            answer=answer,
            abstained=abstained,
            strategy=retrieval.strategy,
            provider=self.provider_name,
            model=self.model_name,
            analysis=analysis,
            evidence=evidence,
            citations=citations,
            verification=verification,
            confidence=confidence,
            trace=self.trace,
            queries_used=retrieval.queries_used,
            correction_rounds=correction_rounds,
            fallback_used=self.fallback_used,
        )

    # ------------------------------------------------------------- internals

    def _build_context(self, analysis: dict[str, Any]) -> RetrievalContext:
        settings = self.settings
        return RetrievalContext(
            session=self.session,
            collections=self.collections,
            trace=self.trace,
            top_k=self.params.top_k or settings.top_k,
            pool_size=settings.candidate_pool_size,
            semantic_weight=settings.semantic_weight,
            keyword_weight=settings.keyword_weight,
            llm=self.llm,
            embedder=self.embedder,
            max_hops=self.params.max_hops or settings.max_hops,
            multi_query_count=settings.multi_query_count,
        )

    def _merge_filters(self, analysis: dict[str, Any]) -> QueryFilters:
        """Deterministically merge user filters with analyzer-extracted ones."""
        filters = self.params.filters
        extracted = analysis.get("filters") or {}
        if not filters.author and extracted.get("author"):
            filters.author = str(extracted["author"])
        if not filters.section and extracted.get("section"):
            filters.section = str(extracted["section"])
        if not filters.source_types and extracted.get("source_type"):
            filters.source_types = [str(extracted["source_type"])]
        return filters

    async def _generate(
        self,
        query: str,
        evidence: list[EvidenceItem],
        conversation_context: str,
        on_token: StreamCallback | None,
    ) -> str:
        messages = [
            ChatMessage(role="system", content=prompts.ANSWER_GENERATOR_SYSTEM),
            ChatMessage(
                role="user",
                content=prompts.ANSWER_GENERATOR_USER.format(
                    conversation_context=conversation_context,
                    query=query,
                    evidence=render_evidence(evidence),
                ),
            ),
        ]
        params = GenerationParams(
            temperature=(
                self.params.temperature
                if self.params.temperature is not None
                else self.settings.temperature
            ),
            max_tokens=self.params.max_tokens or self.settings.max_tokens,
        )

        chain = [self.provider_name]
        if self.params.allow_fallback:
            chain = get_fallback_chain(self.provider_name)

        last_error: Exception | None = None
        for index, provider_name in enumerate(chain):
            llm = self.llm if provider_name == self.provider_name else self._fallback_llm(provider_name)
            if llm is None:
                continue
            try:
                with self.trace.step(
                    "generate", provider=provider_name, model=llm.model,
                    prompt_version=prompts.PROMPT_VERSIONS["answer_generator"],
                ) as step:
                    if on_token is not None and index == 0:
                        text_parts: list[str] = []
                        async for event in llm.stream(messages, params):
                            if event.kind == "delta":
                                text_parts.append(event.text)
                                await on_token(event.text)
                            elif event.kind == "done" and event.usage:
                                self.trace.add_llm_usage(
                                    provider_name, llm.model,
                                    event.usage.prompt_tokens, event.usage.completion_tokens,
                                )
                        answer = "".join(text_parts)
                    else:
                        result = await llm.generate(messages, params)
                        self.trace.add_llm_usage(
                            provider_name, llm.model,
                            result.usage.prompt_tokens, result.usage.completion_tokens,
                        )
                        answer = result.text
                    step.payload["answer_chars"] = len(answer)
                if index > 0:
                    self.fallback_used = provider_name
                    self.trace.add_step(
                        "provider_fallback", from_provider=chain[0], to_provider=provider_name
                    )
                return answer.strip()
            except (ProviderError, ProviderAuthError, ProviderNotConfiguredError) as exc:
                last_error = exc
                self.trace.usage["retries"] += 1
                logger.warning("generation_failed", provider=provider_name, error=str(exc)[:200])
                if not self.params.allow_fallback:
                    raise
        raise last_error or ProviderError("all providers failed")

    def _fallback_llm(self, provider_name: str) -> LLMProvider | None:
        try:
            return get_llm(provider_name, None)
        except Exception:  # noqa: BLE001
            return None

    async def _verify(
        self, answer: str, evidence: list[EvidenceItem]
    ) -> VerificationReport:
        with self.trace.step("verify_claims") as step:
            claims = await extract_claims(self.llm, answer, self.trace)
            step.payload["claims_extracted"] = len(claims)
            if not claims:
                return VerificationReport()
            report = await verify_claims(self.llm, claims, evidence, self.trace)
            step.payload["supported"] = report.supported
            step.payload["total"] = report.total
            step.payload["verdicts"] = [v.as_dict() for v in report.verdicts]
        return report

    async def _self_correct(
        self,
        query: Query,
        evidence: list[EvidenceItem],
        verification: VerificationReport,
        conversation_context: str,
        context: RetrievalContext,
    ) -> tuple[list[EvidenceItem], str, VerificationReport]:
        """One correction round: gap query → extra retrieval → merged evidence →
        regenerate → re-verify."""
        unsupported = "\n".join(f"- {v.claim}" for v in verification.unsupported_critical[:4])
        with self.trace.step("self_correction", unsupported=len(verification.unsupported_critical)):
            gap_query = query.text
            try:
                result = await self.llm.structured_output(
                    [
                        ChatMessage(role="system", content=prompts.GAP_QUERY_SYSTEM),
                        ChatMessage(
                            role="user",
                            content=prompts.GAP_QUERY_USER.format(query=query.text, claims=unsupported),
                        ),
                    ],
                    schema_hint=prompts.GAP_QUERY_SCHEMA,
                    params=GenerationParams(temperature=0.0, max_tokens=120),
                )
                usage = result.pop("_usage", None)
                if usage:
                    self.trace.add_llm_usage(
                        self.provider_name, self.model_name, usage["prompt"], usage["completion"]
                    )
                gap_query = str(result.get("query") or query.text)
            except Exception as exc:  # noqa: BLE001
                logger.warning("gap_query_failed", error=str(exc)[:150])

            extra = await get_strategy("hybrid", self.profile).retrieve(
                Query(text=gap_query, filters=query.filters, analysis=query.analysis), context
            )
            merged_chunks = deduplicate(
                reciprocal_rank_fusion([extra.chunks])
            )
            builder = EvidenceBuilder(
                max_context_tokens=self.params.max_context_tokens or self.settings.max_context_tokens
            )
            extra_items = await builder.build(
                merged_chunks[:6], self.session, self.trace, expand_parents=True
            )
            merged = self._merge_evidence(evidence, extra_items)

        answer = await self._generate(query.text, merged, conversation_context, on_token=None)
        new_report = await self._verify(answer, merged)
        return merged, answer, new_report

    @staticmethod
    def _merge_evidence(
        base: list[EvidenceItem], extra: list[EvidenceItem]
    ) -> list[EvidenceItem]:
        seen = {str(item.chunk_id) for item in base}
        merged = list(base)
        marker = max((item.marker for item in base), default=0) + 1
        for item in extra:
            if str(item.chunk_id) in seen:
                continue
            item.marker = marker
            merged.append(item)
            seen.add(str(item.chunk_id))
            marker += 1
        return merged

    def _confidence(
        self,
        query: str,
        evidence: list[EvidenceItem],
        verification: VerificationReport | None,
        rerank_ran: bool,
        contradictions: list[dict[str, Any]],
    ) -> ConfidenceReport:
        # Retrieval signal: prefer absolute per-source scores; RRF scores are
        # rank-based and not comparable, so fall back to a fixed mid value.
        vector_scores = [i.scores.get("vector") for i in evidence if i.scores.get("vector") is not None]
        fused_scores = [i.scores.get("fused") for i in evidence if i.scores.get("fused") is not None]
        if vector_scores:
            retrieval_signal = sum(vector_scores) / len(vector_scores)
        elif fused_scores:
            retrieval_signal = sum(fused_scores) / len(fused_scores)
        else:
            retrieval_signal = 0.5 if evidence else 0.0

        rerank_scores = [i.scores.get("rerank") for i in evidence if i.scores.get("rerank") is not None]
        rerank_signal = (sum(rerank_scores) / len(rerank_scores)) if (rerank_ran and rerank_scores) else None

        combined_evidence = " ".join(item.content for item in evidence)
        coverage_signal = term_coverage(query, combined_evidence)

        claim_signal = verification.support_ratio if verification and verification.total else None

        contradiction_count = len(contradictions)
        if verification is not None:
            contradiction_count += sum(1 for v in verification.verdicts if v.verdict == "CONTRADICTED")
        contradiction_signal = (
            max(0.0, 1.0 - 0.35 * contradiction_count)
            if (verification is not None or contradictions)
            else None
        )

        trust_signal = sum(item.trust for item in evidence) / len(evidence) if evidence else 0.0

        report = compute_confidence(
            {
                "retrieval": retrieval_signal,
                "rerank": rerank_signal,
                "coverage": coverage_signal,
                "claim_support": claim_signal,
                "contradiction": contradiction_signal,
                "source_trust": trust_signal,
            },
            self.settings,
        )
        self.trace.add_step("confidence", **report.as_dict())
        return report

    @staticmethod
    def _is_insufficient(answer: str) -> bool:
        return INSUFFICIENT_TOKEN in answer[:200]

    @staticmethod
    def _insufficient_explanation(answer: str) -> str:
        text = answer.replace(INSUFFICIENT_TOKEN, "").strip(" :.-\n")
        return text[:300] if text else ""

    def _citations(self, answer: str, evidence: list[EvidenceItem]) -> list[dict[str, Any]]:
        by_marker = {item.marker: item for item in evidence}
        cited: list[dict[str, Any]] = []
        seen: set[int] = set()
        for match in _MARKER.finditer(answer):
            marker = int(match.group(1))
            if marker in seen or marker not in by_marker:
                continue
            seen.add(marker)
            item = by_marker[marker]
            cited.append(
                {
                    "marker": marker,
                    "chunk_id": str(item.chunk_id),
                    "document_id": str(item.document_id),
                    "document_name": item.document_name,
                    "page": item.page,
                    "section": item.section,
                    "snippet": item.content[:400],
                    "source_url": item.meta.get("url", ""),
                    "relevance_score": round(item.score, 4),
                }
            )
        return cited

    def _abstain_result(
        self, analysis: dict[str, Any], strategy: str, queries: list[str], reason: str
    ) -> PipelineResult:
        self.trace.add_step("abstention", triggered=True, reason=reason)
        confidence = ConfidenceReport(score=0.0, level="insufficient", signals={}, weights={})
        return PipelineResult(
            answer=f"{ABSTAIN_MESSAGE} No relevant evidence was found in the selected collections.",
            abstained=True,
            strategy=strategy,
            provider=self.provider_name,
            model=self.model_name,
            analysis=analysis,
            evidence=[],
            citations=[],
            verification=None,
            confidence=confidence,
            trace=self.trace,
            queries_used=queries,
        )
