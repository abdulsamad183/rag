"""Claim extraction, verification, and contradiction detection.

After generation the answer is decomposed into atomic claims; each claim is
checked against the evidence set and classified SUPPORTED /
PARTIALLY_SUPPORTED / UNSUPPORTED / CONTRADICTED. Verification is a single
batched LLM call; a deterministic lexical pre-check marks trivially grounded
claims to reduce LLM disagreement noise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger
from app.llm.base import ChatMessage, GenerationParams, LLMProvider
from app.observability.tracing import TraceRecorder
from app.rag import prompts
from app.rag.evidence import EvidenceItem, render_evidence
from app.utils.text import term_coverage

logger = get_logger("claims")

VERDICTS = ("SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "CONTRADICTED")


@dataclass
class ClaimVerdict:
    claim: str
    critical: bool
    verdict: str
    evidence_ids: list[int] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "critical": self.critical,
            "verdict": self.verdict,
            "evidence_ids": self.evidence_ids,
            "note": self.note,
        }


@dataclass
class VerificationReport:
    verdicts: list[ClaimVerdict] = field(default_factory=list)
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""

    @property
    def total(self) -> int:
        return len(self.verdicts)

    @property
    def supported(self) -> int:
        return sum(1 for v in self.verdicts if v.verdict == "SUPPORTED")

    @property
    def support_ratio(self) -> float:
        if not self.verdicts:
            return 1.0
        score = 0.0
        for verdict in self.verdicts:
            if verdict.verdict == "SUPPORTED":
                score += 1.0
            elif verdict.verdict == "PARTIALLY_SUPPORTED":
                score += 0.5
        return score / len(self.verdicts)

    @property
    def has_contradiction(self) -> bool:
        return bool(self.contradictions) or any(v.verdict == "CONTRADICTED" for v in self.verdicts)

    @property
    def unsupported_critical(self) -> list[ClaimVerdict]:
        return [
            v for v in self.verdicts
            if v.critical and v.verdict in ("UNSUPPORTED", "CONTRADICTED")
        ]

    def as_dict(self) -> dict[str, Any]:
        return {
            "claims": [v.as_dict() for v in self.verdicts],
            "supported": self.supported,
            "total": self.total,
            "support_ratio": round(self.support_ratio, 3),
            "contradictions": self.contradictions,
            "error": self.error,
        }


async def extract_claims(
    llm: LLMProvider, answer: str, trace: TraceRecorder
) -> list[dict[str, Any]]:
    try:
        result = await llm.structured_output(
            [
                ChatMessage(role="system", content=prompts.CLAIM_EXTRACTOR_SYSTEM),
                ChatMessage(role="user", content=prompts.CLAIM_EXTRACTOR_USER.format(answer=answer)),
            ],
            schema_hint=prompts.CLAIM_EXTRACTOR_SCHEMA,
            params=GenerationParams(temperature=0.0, max_tokens=600),
        )
        usage = result.pop("_usage", None)
        if usage:
            trace.add_llm_usage(llm.name, llm.model, usage["prompt"], usage["completion"])
        claims = [
            {"text": str(c.get("text", "")).strip(), "critical": bool(c.get("critical", True))}
            for c in result.get("claims", [])
            if isinstance(c, dict) and str(c.get("text", "")).strip()
        ]
        return claims[:8]
    except Exception as exc:  # noqa: BLE001
        logger.warning("claim_extraction_failed", error=str(exc)[:200])
        return []


async def verify_claims(
    llm: LLMProvider,
    claims: list[dict[str, Any]],
    evidence: list[EvidenceItem],
    trace: TraceRecorder,
) -> VerificationReport:
    if not claims:
        return VerificationReport()

    # Deterministic pre-check: claims lexically covered ≥85% by one evidence
    # block are trivially grounded.
    pre_verified: dict[int, ClaimVerdict] = {}
    for index, claim in enumerate(claims):
        for item in evidence:
            if term_coverage(claim["text"], item.content) >= 0.85:
                pre_verified[index] = ClaimVerdict(
                    claim=claim["text"],
                    critical=claim["critical"],
                    verdict="SUPPORTED",
                    evidence_ids=[item.marker],
                    note="lexical match",
                )
                break

    remaining = {i: c for i, c in enumerate(claims) if i not in pre_verified}
    verdicts: dict[int, ClaimVerdict] = dict(pre_verified)

    if remaining:
        claim_list = "\n".join(f"{i}. {c['text']}" for i, c in remaining.items())
        try:
            result = await llm.structured_output(
                [
                    ChatMessage(role="system", content=prompts.CLAIM_VERIFIER_SYSTEM),
                    ChatMessage(
                        role="user",
                        content=prompts.CLAIM_VERIFIER_USER.format(
                            evidence=render_evidence(evidence), claims=claim_list
                        ),
                    ),
                ],
                schema_hint=prompts.CLAIM_VERIFIER_SCHEMA,
                params=GenerationParams(temperature=0.0, max_tokens=900),
            )
            usage = result.pop("_usage", None)
            if usage:
                trace.add_llm_usage(llm.name, llm.model, usage["prompt"], usage["completion"])
            for verdict_data in result.get("verdicts", []):
                index = int(verdict_data.get("claim_index", -1))
                if index not in remaining:
                    continue
                verdict = str(verdict_data.get("verdict", "UNSUPPORTED")).upper()
                if verdict not in VERDICTS:
                    verdict = "UNSUPPORTED"
                verdicts[index] = ClaimVerdict(
                    claim=remaining[index]["text"],
                    critical=remaining[index]["critical"],
                    verdict=verdict,
                    evidence_ids=[
                        int(e) for e in verdict_data.get("evidence_ids", []) if str(e).isdigit()
                    ],
                    note=str(verdict_data.get("note", ""))[:300],
                )
            # Model may omit claims — mark them unverified rather than assuming support.
            for index, claim in remaining.items():
                if index not in verdicts:
                    verdicts[index] = ClaimVerdict(
                        claim=claim["text"], critical=claim["critical"],
                        verdict="UNSUPPORTED", note="not addressed by verifier",
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("claim_verification_failed", error=str(exc)[:200])
            report = VerificationReport(
                verdicts=[v for _, v in sorted(verdicts.items())],
                error=f"verification unavailable: {str(exc)[:120]}",
            )
            return report

    return VerificationReport(verdicts=[v for _, v in sorted(verdicts.items())])


async def detect_contradictions(
    llm: LLMProvider, evidence: list[EvidenceItem], trace: TraceRecorder
) -> list[dict[str, Any]]:
    """Cross-source conflict analysis (deep/research profiles). Only runs when
    at least two distinct documents are present."""
    if len({str(item.document_id) for item in evidence}) < 2:
        return []
    try:
        result = await llm.structured_output(
            [
                ChatMessage(role="system", content=prompts.CONTRADICTION_SYSTEM),
                ChatMessage(
                    role="user",
                    content=prompts.CONTRADICTION_USER.format(evidence=render_evidence(evidence)),
                ),
            ],
            schema_hint=prompts.CONTRADICTION_SCHEMA,
            params=GenerationParams(temperature=0.0, max_tokens=600),
        )
        usage = result.pop("_usage", None)
        if usage:
            trace.add_llm_usage(llm.name, llm.model, usage["prompt"], usage["completion"])
        contradictions = [
            {
                "evidence_ids": [int(e) for e in c.get("evidence_ids", []) if str(e).isdigit()],
                "topic": str(c.get("topic", ""))[:200],
                "description": str(c.get("description", ""))[:500],
                "likely_reason": str(c.get("likely_reason", ""))[:300],
            }
            for c in result.get("contradictions", [])
            if isinstance(c, dict)
        ]
        return contradictions[:5]
    except Exception as exc:  # noqa: BLE001
        logger.warning("contradiction_detection_failed", error=str(exc)[:200])
        return []
