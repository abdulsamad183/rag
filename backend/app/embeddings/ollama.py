from __future__ import annotations

import httpx

from app.config import get_settings
from app.core.errors import ProviderError
from app.embeddings.base import EmbeddingProvider, EmbeddingResult
from app.llm.utils import raise_for_provider_status, with_retries
from app.llm.windows_bridge import ollama_transport
from app.utils.text import estimate_tokens


class OllamaEmbeddings(EmbeddingProvider):
    name = "ollama"

    def __init__(self, model: str, transport: httpx.AsyncBaseTransport | None = None):
        super().__init__(model)
        self.base_url = get_settings().ollama_base_url.rstrip("/")
        self._transport = transport

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        async def call() -> EmbeddingResult:
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=httpx.Timeout(get_settings().llm_timeout_seconds, connect=5.0),
                    transport=ollama_transport(self._transport, self.base_url),
                ) as client:
                    response = await client.post(
                        "/api/embed", json={"model": self.model, "input": texts}
                    )
            except httpx.ConnectError as exc:
                raise ProviderError(
                    f"ollama-embeddings: cannot reach Ollama at {self.base_url}",
                    details={"provider": "ollama"},
                ) from exc
            if response.status_code == 404:
                raise ProviderError(
                    f"ollama-embeddings: model '{self.model}' not pulled. "
                    f"Run: ollama pull {self.model}",
                    details={"provider": "ollama", "status": 404},
                )
            raise_for_provider_status("ollama-embeddings", response)
            try:
                data = response.json()
                vectors = data["embeddings"]
                return EmbeddingResult(
                    vectors=vectors,
                    model=self.model,
                    dimension=len(vectors[0]) if vectors else 0,
                    prompt_tokens=data.get("prompt_eval_count", 0)
                    or sum(estimate_tokens(t) for t in texts),
                )
            except (KeyError, IndexError, TypeError) as exc:
                raise ProviderError("ollama-embeddings: malformed response") from exc

        return await with_retries("ollama-embeddings", call)
