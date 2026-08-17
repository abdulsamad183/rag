from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator

import httpx

from app.config import get_settings
from app.core.errors import ProviderError
from app.llm.base import (
    ChatMessage,
    GenerationParams,
    GenerationResult,
    LLMProvider,
    StreamEvent,
    Usage,
)
from app.llm.utils import raise_for_provider_status, with_retries
from app.llm.windows_bridge import ollama_transport


class OllamaProvider(LLMProvider):
    """First-class local provider. Handles daemon-down, model-not-pulled,
    timeouts, and models with uneven capabilities (JSON mode is requested via
    ``format`` but never assumed to succeed — the robust JSON parser covers
    models that ignore it)."""

    name = "ollama"

    def __init__(self, model: str, transport: httpx.AsyncBaseTransport | None = None):
        super().__init__(model)
        self.base_url = get_settings().ollama_base_url.rstrip("/")
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(get_settings().llm_timeout_seconds, connect=5.0),
            transport=ollama_transport(self._transport, self.base_url),
        )

    def _payload(self, messages: list[ChatMessage], params: GenerationParams, stream: bool) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": stream,
            "options": {"temperature": params.temperature, "num_predict": params.max_tokens},
        }
        if params.json_mode:
            payload["format"] = "json"
        if params.stop:
            payload["options"]["stop"] = params.stop
        return payload

    @staticmethod
    def _usage(data: dict) -> Usage:
        return Usage(
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
        )

    async def generate(
        self, messages: list[ChatMessage], params: GenerationParams | None = None
    ) -> GenerationResult:
        params = params or GenerationParams()

        async def call() -> GenerationResult:
            started = time.perf_counter()
            try:
                async with self._client() as client:
                    response = await client.post("/api/chat", json=self._payload(messages, params, False))
            except httpx.ConnectError as exc:
                raise ProviderError(
                    f"ollama: cannot reach the Ollama server at {self.base_url}. Is it running?",
                    details={"provider": "ollama"},
                ) from exc
            if response.status_code == 404:
                raise ProviderError(
                    f"ollama: model '{self.model}' is not available. Pull it with: "
                    f"ollama pull {self.model}",
                    details={"provider": "ollama", "status": 404},
                )
            raise_for_provider_status(self.name, response)
            try:
                data = response.json()
                return GenerationResult(
                    text=data["message"]["content"],
                    usage=self._usage(data),
                    model=data.get("model", self.model),
                    finish_reason=data.get("done_reason", ""),
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
            except (KeyError, TypeError, json.JSONDecodeError) as exc:
                raise ProviderError("ollama: malformed response") from exc

        return await with_retries(self.name, call)

    async def stream(
        self, messages: list[ChatMessage], params: GenerationParams | None = None
    ) -> AsyncIterator[StreamEvent]:
        params = params or GenerationParams()
        usage = Usage()
        try:
            async with self._client() as client:
                async with client.stream(
                    "POST", "/api/chat", json=self._payload(messages, params, True)
                ) as response:
                    if response.status_code >= 400:
                        await response.aread()
                        raise_for_provider_status(self.name, response)
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        content = (event.get("message") or {}).get("content", "")
                        if content:
                            yield StreamEvent(kind="delta", text=content)
                        if event.get("done"):
                            usage = self._usage(event)
        except httpx.ConnectError as exc:
            raise ProviderError(
                f"ollama: cannot reach the Ollama server at {self.base_url}",
                details={"provider": "ollama"},
            ) from exc
        yield StreamEvent(kind="done", usage=usage)

    async def list_local_models(self) -> list[str]:
        """Query the daemon for actually-pulled models (used by /providers)."""
        try:
            async with self._client() as client:
                response = await client.get("/api/tags")
                if response.status_code != 200:
                    return []
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
        except (httpx.HTTPError, KeyError, json.JSONDecodeError):
            return []
