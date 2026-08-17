"""Adapter for OpenAI-compatible chat APIs (OpenAI itself, Groq, and any
gateway speaking the same protocol)."""

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


class OpenAICompatProvider(LLMProvider):
    name = "openai_compat"

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        super().__init__(model)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=get_settings().llm_timeout_seconds,
            transport=self._transport,
        )

    def _payload(self, messages: list[ChatMessage], params: GenerationParams) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": params.temperature,
            "max_tokens": params.max_tokens,
        }
        if params.json_mode:
            payload["response_format"] = {"type": "json_object"}
        if params.stop:
            payload["stop"] = params.stop
        return payload

    async def generate(
        self, messages: list[ChatMessage], params: GenerationParams | None = None
    ) -> GenerationResult:
        params = params or GenerationParams()

        async def call() -> GenerationResult:
            started = time.perf_counter()
            async with self._client() as client:
                response = await client.post("/chat/completions", json=self._payload(messages, params))
                raise_for_provider_status(self.name, response)
                data = response.json()
            try:
                choice = data["choices"][0]
                usage = data.get("usage") or {}
                return GenerationResult(
                    text=choice["message"].get("content") or "",
                    usage=Usage(
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                    ),
                    model=data.get("model", self.model),
                    finish_reason=choice.get("finish_reason", ""),
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
            except (KeyError, IndexError, TypeError) as exc:
                raise ProviderError(f"{self.name}: malformed response") from exc

        return await with_retries(self.name, call)

    async def stream(
        self, messages: list[ChatMessage], params: GenerationParams | None = None
    ) -> AsyncIterator[StreamEvent]:
        params = params or GenerationParams()
        payload = self._payload(messages, params)
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}
        usage = Usage()

        async with self._client() as client:
            async with client.stream("POST", "/chat/completions", json=payload) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise_for_provider_status(self.name, response)
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if event.get("usage"):
                        usage = Usage(
                            prompt_tokens=event["usage"].get("prompt_tokens", 0),
                            completion_tokens=event["usage"].get("completion_tokens", 0),
                        )
                    choices = event.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content")
                        if content:
                            yield StreamEvent(kind="delta", text=content)
        yield StreamEvent(kind="done", usage=usage)


class OpenAIProvider(OpenAICompatProvider):
    name = "openai"

    def __init__(self, model: str, transport: httpx.AsyncBaseTransport | None = None):
        settings = get_settings()
        super().__init__(model, settings.openai_api_key, settings.openai_base_url, transport)


class GroqProvider(OpenAICompatProvider):
    name = "groq"

    def __init__(self, model: str, transport: httpx.AsyncBaseTransport | None = None):
        settings = get_settings()
        super().__init__(model, settings.groq_api_key, settings.groq_base_url, transport)
