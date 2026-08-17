from __future__ import annotations

import httpx

from app.config import get_settings
from app.config.model_catalog import find_model, get_catalog
from app.core.errors import CapabilityError, ProviderNotConfiguredError
from app.llm.base import LLMProvider
from app.llm.gemini import GeminiProvider
from app.llm.mock import MockLLMProvider
from app.llm.ollama import OllamaProvider
from app.llm.openai_compat import GroqProvider, OpenAIProvider

PROVIDERS = ("openai", "groq", "gemini", "ollama", "mock")

_FACTORIES = {
    "openai": OpenAIProvider,
    "groq": GroqProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
    "mock": MockLLMProvider,
}


def resolve_provider_model(provider: str | None, model: str | None) -> tuple[str, str]:
    """Apply defaults: provider from settings, model from provider default."""
    settings = get_settings()
    resolved_provider = (provider or settings.default_llm_provider).lower()
    if resolved_provider not in PROVIDERS:
        raise ProviderNotConfiguredError(f"Unknown provider '{resolved_provider}'")
    resolved_model = model or settings.default_llm_model or settings.provider_default_model(
        resolved_provider
    )
    if not resolved_model:
        raise ProviderNotConfiguredError(f"No model configured for provider '{resolved_provider}'")
    return resolved_provider, resolved_model


def get_llm(
    provider: str | None = None,
    model: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> LLMProvider:
    settings = get_settings()
    resolved_provider, resolved_model = resolve_provider_model(provider, model)
    if settings.local_mode and resolved_provider not in ("ollama", "mock"):
        raise CapabilityError(
            "Local mode is enabled: only the Ollama provider is allowed. "
            "Disable LOCAL_MODE or switch to Ollama."
        )
    if not settings.provider_configured(resolved_provider):
        raise ProviderNotConfiguredError(
            f"Provider '{resolved_provider}' is not configured (missing API key or base URL)"
        )
    factory = _FACTORIES[resolved_provider]
    return factory(resolved_model, transport=transport)


def check_capability(provider: str, model: str, capability: str) -> bool:
    """Consult the catalog; unknown (e.g. arbitrary local) models are assumed
    to support streaming+JSON only, which the adapters can recover from."""
    info = find_model(provider, model)
    if info is None:
        return capability in ("streaming", "json_output")
    return bool(getattr(info.capabilities, capability, False))


def get_fallback_chain(primary: str) -> list[str]:
    """Provider fallback order: primary first, then other configured providers.
    The pipeline only fails over when explicitly asked to (fallback=True) and
    always records the switch in the trace."""
    settings = get_settings()
    chain = [primary]
    for candidate in PROVIDERS:
        if candidate != primary and settings.provider_configured(candidate):
            chain.append(candidate)
    return chain


def catalog_for_provider(provider: str) -> list[dict]:
    return [
        {
            "name": m.name,
            "label": m.label,
            "context_window": m.context_window,
            "capabilities": {
                "streaming": m.capabilities.streaming,
                "json_output": m.capabilities.json_output,
                "tools": m.capabilities.tools,
                "vision": m.capabilities.vision,
            },
        }
        for m in get_catalog().get(provider, [])
    ]
