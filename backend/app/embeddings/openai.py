from __future__ import annotations

import httpx

from app.config import get_settings
from app.core.errors import ProviderError
from app.embeddings.base import EmbeddingProvider, EmbeddingResult
from app.llm.utils import raise_for_provider_status, with_retries


class OpenAIEmbeddings(EmbeddingProvider):
    name = "openai"

    def __init__(self, model: str, transport: httpx.AsyncBaseTransport | None = None):
        super().__init__(model)
        settings = get_settings()
        self.api_key = settings.openai_api_key
        self.base_url = settings.openai_base_url.rstrip("/")
        self._transport = transport

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        async def call() -> EmbeddingResult:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=get_settings().llm_timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    "/embeddings", json={"model": self.model, "input": texts}
                )
                raise_for_provider_status("openai-embeddings", response)
                data = response.json()
            try:
                ordered = sorted(data["data"], key=lambda item: item["index"])
                vectors = [item["embedding"] for item in ordered]
                usage = data.get("usage") or {}
                return EmbeddingResult(
                    vectors=vectors,
                    model=self.model,
                    dimension=len(vectors[0]) if vectors else 0,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                )
            except (KeyError, IndexError, TypeError) as exc:
                raise ProviderError("openai-embeddings: malformed response") from exc

        return await with_retries("openai-embeddings", call)
