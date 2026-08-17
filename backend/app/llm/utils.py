from __future__ import annotations

import asyncio
import json
import random
import re
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import httpx

from app.config import get_settings
from app.core.errors import ProviderAuthError, ProviderError
from app.core.logging import get_logger

logger = get_logger("llm")

T = TypeVar("T")

_JSON_BLOCK = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def extract_json(text: str) -> dict[str, Any] | None:
    """Robustly pull a JSON object out of model output (raw, fenced, or with
    surrounding prose)."""
    text = text.strip()
    candidates = [text]
    for match in _JSON_BLOCK.finditer(text):
        candidates.insert(0, match.group(1).strip())
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def raise_for_provider_status(provider: str, response: httpx.Response) -> None:
    if response.status_code in (401, 403):
        raise ProviderAuthError(
            f"{provider}: authentication failed — check the API key",
            details={"provider": provider, "status": response.status_code},
        )
    if response.status_code == 404:
        raise ProviderError(
            f"{provider}: model or endpoint not found",
            details={"provider": provider, "status": 404},
        )
    if response.status_code >= 400:
        snippet = response.text[:300]
        raise ProviderError(
            f"{provider}: request failed with status {response.status_code}",
            details={"provider": provider, "status": response.status_code, "body": snippet},
        )


async def with_retries(provider: str, fn: Callable[[], Awaitable[T]]) -> T:
    """Bounded retry with exponential backoff + jitter for transient failures
    (timeouts, connection errors, 429/5xx). Auth and 4xx errors never retry."""
    settings = get_settings()
    attempts = settings.llm_max_retries + 1
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return await fn()
        except ProviderAuthError:
            raise
        except ProviderError as exc:
            status = exc.details.get("status", 0)
            retryable = status in (429,) or status >= 500
            last_error = exc
            if not retryable or attempt == attempts - 1:
                raise
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
            reason = "timeout" if isinstance(exc, httpx.TimeoutException) else "connection failed"
            last_error = ProviderError(
                f"{provider}: {reason}",
                details={"provider": provider, "cause": type(exc).__name__},
            )
            if attempt == attempts - 1:
                raise last_error from exc
        backoff = settings.llm_retry_backoff_seconds * (2**attempt) * (1 + random.random() * 0.2)
        logger.warning("provider_retry", provider=provider, attempt=attempt + 1, backoff_s=round(backoff, 2))
        await asyncio.sleep(backoff)
    raise last_error or ProviderError(f"{provider}: request failed")
