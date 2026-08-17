"""In-process pipeline tracing.

Every RAG execution builds a ``TraceRecorder``: ordered, structured step
events with latencies, safe payloads (scores, decisions, counts — never
private chain-of-thought), token usage, and cost. The recorder is persisted
as a ``RetrievalTrace`` row and rendered in the frontend trace viewer.

The step API is deliberately OpenTelemetry-shaped (named spans with
start/end and attributes) so an OTEL exporter can be added without
restructuring the pipeline.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from app.config.model_catalog import estimate_cost
from app.core.logging import get_logger

logger = get_logger("trace")


@dataclass
class TraceStep:
    name: str
    status: str = "ok"  # ok | error | skipped
    latency_ms: int = 0
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "payload": _json_safe(self.payload),
        }


@dataclass
class TraceRecorder:
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    steps: list[TraceStep] = field(default_factory=list)
    usage: dict[str, Any] = field(
        default_factory=lambda: {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "embedding_tokens": 0,
            "llm_calls": 0,
            "estimated_cost_usd": 0.0,
            "retries": 0,
        }
    )
    retrieved: list[dict[str, Any]] = field(default_factory=list)
    on_emit: Callable[[TraceStep], None] | None = field(default=None, repr=False, compare=False)
    _started: float = field(default_factory=time.perf_counter)

    @contextmanager
    def step(self, name: str, **payload: Any):
        started = time.perf_counter()
        record = TraceStep(name=name, payload=dict(payload))
        try:
            yield record
            record.status = "ok" if record.status == "ok" else record.status
        except Exception as exc:
            record.status = "error"
            record.payload["error"] = str(exc)[:500]
            raise
        finally:
            record.latency_ms = int((time.perf_counter() - started) * 1000)
            self.steps.append(record)
            self._publish(record)

    def add_step(self, name: str, status: str = "ok", **payload: Any) -> None:
        record = TraceStep(name=name, status=status, payload=dict(payload))
        self.steps.append(record)
        self._publish(record)

    def _publish(self, record: TraceStep) -> None:
        logger.info(
            "pipeline_step",
            request_id=self.request_id,
            step=record.name,
            status=record.status,
            latency_ms=record.latency_ms,
        )
        if self.on_emit is None:
            return
        try:
            self.on_emit(record)
        except Exception:  # noqa: BLE001 — live UI must not fail the pipeline
            logger.warning("trace_emit_failed", step=record.name)

    def add_llm_usage(
        self, provider: str, model: str, prompt_tokens: int, completion_tokens: int
    ) -> None:
        self.usage["prompt_tokens"] += prompt_tokens
        self.usage["completion_tokens"] += completion_tokens
        self.usage["llm_calls"] += 1
        self.usage["estimated_cost_usd"] = round(
            self.usage["estimated_cost_usd"]
            + estimate_cost(provider, model, prompt_tokens, completion_tokens),
            8,
        )

    def add_embedding_usage(self, tokens: int) -> None:
        self.usage["embedding_tokens"] += tokens

    def set_retrieved(self, candidates: list[dict[str, Any]]) -> None:
        self.retrieved = candidates

    @property
    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self._started) * 1000)

    def steps_as_dicts(self) -> list[dict[str, Any]]:
        return [s.as_dict() for s in self.steps]


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return json.loads(json.dumps(value, default=str))
