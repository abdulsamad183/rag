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


def _to_gemini_payload(messages: list[ChatMessage], params: GenerationParams) -> dict:
    system_parts = [m.content for m in messages if m.role == "system"]
    contents = []
    for message in messages:
        if message.role == "system":
            continue
        contents.append(
            {
                "role": "model" if message.role == "assistant" else "user",
                "parts": [{"text": message.content}],
            }
        )
    payload: dict = {
        "contents": contents,
        "generationConfig": {
            "temperature": params.temperature,
            "maxOutputTokens": params.max_tokens,
        },
    }
    if system_parts:
        payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
    if params.json_mode:
        payload["generationConfig"]["responseMimeType"] = "application/json"
    if params.stop:
        payload["generationConfig"]["stopSequences"] = params.stop
    return payload


def _parse_usage(data: dict) -> Usage:
    meta = data.get("usageMetadata") or {}
    return Usage(
        prompt_tokens=meta.get("promptTokenCount", 0),
        completion_tokens=meta.get("candidatesTokenCount", 0),
    )


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, model: str, transport: httpx.AsyncBaseTransport | None = None):
        super().__init__(model)
        settings = get_settings()
        self.api_key = settings.gemini_api_key
        self.base_url = settings.gemini_base_url.rstrip("/")
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers={"x-goog-api-key": self.api_key},
            timeout=get_settings().llm_timeout_seconds,
            transport=self._transport,
        )

    async def generate(
        self, messages: list[ChatMessage], params: GenerationParams | None = None
    ) -> GenerationResult:
        params = params or GenerationParams()

        async def call() -> GenerationResult:
            started = time.perf_counter()
            async with self._client() as client:
                response = await client.post(
                    f"/models/{self.model}:generateContent",
                    json=_to_gemini_payload(messages, params),
                )
                raise_for_provider_status(self.name, response)
                data = response.json()
            try:
                candidates = data.get("candidates") or []
                if not candidates:
                    block = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
                    raise ProviderError(f"gemini: empty response ({block})")
                parts = candidates[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts)
                return GenerationResult(
                    text=text,
                    usage=_parse_usage(data),
                    model=self.model,
                    finish_reason=candidates[0].get("finishReason", ""),
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
            except (KeyError, IndexError, TypeError) as exc:
                raise ProviderError("gemini: malformed response") from exc

        return await with_retries(self.name, call)

    async def stream(
        self, messages: list[ChatMessage], params: GenerationParams | None = None
    ) -> AsyncIterator[StreamEvent]:
        params = params or GenerationParams()
        usage = Usage()
        async with self._client() as client:
            async with client.stream(
                "POST",
                f"/models/{self.model}:streamGenerateContent?alt=sse",
                json=_to_gemini_payload(messages, params),
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise_for_provider_status(self.name, response)
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    if event.get("usageMetadata"):
                        usage = _parse_usage(event)
                    for candidate in event.get("candidates") or []:
                        for part in candidate.get("content", {}).get("parts", []):
                            if part.get("text"):
                                yield StreamEvent(kind="delta", text=part["text"])
        yield StreamEvent(kind="done", usage=usage)
