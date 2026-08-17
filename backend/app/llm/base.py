"""Provider-agnostic LLM interface.

The RAG pipeline only ever sees this interface; swapping OpenAI for Ollama
(or any future provider) never touches retrieval, orchestration, or UI code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatMessage:
    role: str  # system | user | assistant
    content: str


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def add(self, other: Usage) -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens


@dataclass
class GenerationResult:
    text: str
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    finish_reason: str = ""
    latency_ms: int = 0


@dataclass
class StreamEvent:
    kind: str  # "delta" | "done"
    text: str = ""
    usage: Usage | None = None


@dataclass
class GenerationParams:
    temperature: float = 0.1
    max_tokens: int = 1024
    json_mode: bool = False
    stop: list[str] | None = None


class LLMProvider(ABC):
    """One instance is bound to (provider, model)."""

    name: str = ""

    def __init__(self, model: str):
        self.model = model

    @abstractmethod
    async def generate(
        self, messages: list[ChatMessage], params: GenerationParams | None = None
    ) -> GenerationResult: ...

    @abstractmethod
    def stream(
        self, messages: list[ChatMessage], params: GenerationParams | None = None
    ) -> AsyncIterator[StreamEvent]: ...

    async def structured_output(
        self,
        messages: list[ChatMessage],
        schema_hint: str,
        params: GenerationParams | None = None,
    ) -> dict[str, Any]:
        """Generate JSON conforming to ``schema_hint`` (a human-readable schema
        description embedded in the prompt). Providers with native JSON modes
        use them; the robust parser + one retry covers the rest."""
        from app.llm.utils import extract_json

        params = params or GenerationParams()
        params.json_mode = True
        prompt = list(messages)
        prompt[-1] = ChatMessage(
            role=prompt[-1].role,
            content=(
                f"{prompt[-1].content}\n\n"
                f"Respond with ONLY a valid JSON object matching this schema:\n{schema_hint}"
            ),
        )
        result = await self.generate(prompt, params)
        parsed = extract_json(result.text)
        if parsed is not None:
            parsed["_usage"] = {"prompt": result.usage.prompt_tokens,
                                "completion": result.usage.completion_tokens}
            return parsed

        retry_prompt = prompt + [
            ChatMessage(role="assistant", content=result.text[:2000]),
            ChatMessage(
                role="user",
                content="That was not valid JSON. Respond again with ONLY the JSON object, no prose.",
            ),
        ]
        retry = await self.generate(retry_prompt, params)
        parsed = extract_json(retry.text)
        if parsed is None:
            from app.core.errors import ProviderError

            raise ProviderError(f"{self.name} returned malformed JSON for structured output")
        parsed["_usage"] = {
            "prompt": result.usage.prompt_tokens + retry.usage.prompt_tokens,
            "completion": result.usage.completion_tokens + retry.usage.completion_tokens,
        }
        return parsed
