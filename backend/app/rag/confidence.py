"""Confidence engine: deterministic weighted aggregation of pipeline signals.

Signals (each 0..1):
  retrieval    — mean first-stage score of the selected evidence
  rerank       — mean reranker score (when reranking ran)
  coverage     — fraction of query terms present in the evidence set
  claim_support— verified-claim support ratio (when verification ran)
  contradiction— 1.0 if none detected, scaled down per conflict
  source_trust — mean document trust of cited evidence

Weights are configuration, missing signals are excluded and weights
renormalized, and every component is returned for inspection — the score is
never an opaque LLM opinion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import Settings

WEIGHTS = {
    "retrieval": 0.22,
    "rerank": 0.13,
    "coverage": 0.15,
    "claim_support": 0.30,
    "contradiction": 0.10,
    "source_trust": 0.10,
}

LEVELS = ("high", "medium", "low", "insufficient")


@dataclass
class ConfidenceReport:
    score: float
    level: str
    signals: dict[str, float]
    weights: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 3),
            "level": self.level,
            "signals": {k: round(v, 3) for k, v in self.signals.items()},
            "weights": self.weights,
        }


def compute_confidence(signals: dict[str, float | None], settings: Settings) -> ConfidenceReport:
    available = {k: v for k, v in signals.items() if v is not None and k in WEIGHTS}
    if not available:
        return ConfidenceReport(0.0, "insufficient", {}, {})

    total_weight = sum(WEIGHTS[k] for k in available)
    score = sum(WEIGHTS[k] * max(0.0, min(1.0, v)) for k, v in available.items()) / total_weight

    if score >= settings.confidence_high:
        level = "high"
    elif score >= settings.confidence_medium:
        level = "medium"
    elif score >= settings.confidence_low:
        level = "low"
    else:
        level = "insufficient"

    used_weights = {k: round(WEIGHTS[k] / total_weight, 3) for k in available}
    return ConfidenceReport(score=score, level=level, signals=dict(available), weights=used_weights)
