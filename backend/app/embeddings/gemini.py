from __future__ import annotations

import httpx

from app.config import get_settings
from app.core.errors import ProviderError
from app.embeddings.base import EmbeddingProvider, EmbeddingResult
from app.llm.utils import raise_for_provider_status, with_retries
from app.utils.text import estimate_tokens


class GeminiEmbeddings(EmbeddingProvider):
    name = "gemini"

    def __init__(self, model: str, transport: httpx.AsyncBaseTransport | None = None):
        super().__init__(model)
        settings = get_settings()
        self.api_key = settings.gemini_api_key
        self.base_url = settings.gemini_base_url.rstrip("/")
        self._transport = transport

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        async def call() -> EmbeddingResult:
            payload = {
                "requests": [
                    {"model": f"models/{self.model}", "content": {"parts": [{"text": t}]}}
                    for t in texts
                ]
            }
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers={"x-goog-api-key": self.api_key},
                timeout=get_settings().llm_timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    f"/models/{self.model}:batchEmbedContents", json=payload
                )
                raise_for_provider_status("gemini-embeddings", response)
                data = response.json()
            try:
                vectors = [item["values"] for item in data["embeddings"]]
                return EmbeddingResult(
                    vectors=vectors,
                    model=self.model,
                    dimension=len(vectors[0]) if vectors else 0,
                    prompt_tokens=sum(estimate_tokens(t) for t in texts),
                )
            except (KeyError, IndexError, TypeError) as exc:
                raise ProviderError("gemini-embeddings: malformed response") from exc

        return await with_retries("gemini-embeddings", call)
