from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.config.model_catalog import get_embedding_catalog
from app.llm.ollama import OllamaProvider
from app.llm.registry import PROVIDERS, catalog_for_provider
from app.reranking import RERANKERS
from app.retrieval.registry import STRATEGY_NAMES
from app.schemas.providers import AppConfigOut, ModelOut, ProviderOut

router = APIRouter(tags=["providers"])

_LABELS = {
    "openai": "OpenAI",
    "groq": "Groq",
    "gemini": "Google Gemini",
    "ollama": "Ollama (local)",
    "mock": "Mock (offline)",
}


@router.get("/providers", response_model=list[ProviderOut])
async def list_providers() -> list[ProviderOut]:
    settings = get_settings()
    embedding_catalog = get_embedding_catalog()
    result: list[ProviderOut] = []

    for provider in PROVIDERS:
        configured = settings.provider_configured(provider)
        if provider == "mock" and not configured:
            continue  # hidden unless MOCK_PROVIDER=1
        models = [ModelOut(**m) for m in catalog_for_provider(provider)]
        note = ""

        if provider == "ollama" and configured:
            installed = await OllamaProvider(settings.ollama_default_model).list_local_models()
            if installed:
                catalog_names = {m.name for m in models}
                for model in models:
                    model.installed = any(i.split(":")[0] == model.name for i in installed)
                for name in installed:
                    base = name.split(":")[0]
                    if base not in catalog_names and name not in catalog_names:
                        models.append(ModelOut(name=name, label=f"{name} (installed)", installed=True))
            else:
                note = "Ollama server not reachable or no models pulled"

        if settings.local_mode and provider != "ollama":
            note = "Disabled by LOCAL_MODE"

        result.append(
            ProviderOut(
                name=provider,
                label=_LABELS[provider],
                configured=configured,
                default_model=settings.provider_default_model(provider),
                models=models,
                embedding_models=[
                    {"name": m.name, "dimension": m.dimension}
                    for m in embedding_catalog.get(provider, [])
                ],
                is_local=provider == "ollama",
                note=note,
            )
        )
    return result


@router.get("/models", response_model=dict[str, list[ModelOut]])
async def list_models() -> dict[str, list[ModelOut]]:
    return {p: [ModelOut(**m) for m in catalog_for_provider(p)] for p in PROVIDERS}


@router.get("/config", response_model=AppConfigOut)
async def app_config() -> AppConfigOut:
    settings = get_settings()
    from app.chunking import STRATEGIES as CHUNKING_STRATEGIES

    return AppConfigOut(
        default_provider=settings.default_llm_provider,
        default_embedding_provider=settings.default_embedding_provider,
        local_mode=settings.local_mode,
        retrieval_defaults={
            "strategy": settings.retrieval_strategy,
            "top_k": settings.top_k,
            "rerank_top_k": settings.rerank_top_k,
            "reranker": settings.reranker,
            "semantic_weight": settings.semantic_weight,
            "keyword_weight": settings.keyword_weight,
            "max_hops": settings.max_hops,
            "confidence_threshold": settings.abstain_threshold,
            "temperature": settings.temperature,
            "max_context_tokens": settings.max_context_tokens,
        },
        chunking_strategies=list(CHUNKING_STRATEGIES),
        retrieval_strategies=list(STRATEGY_NAMES),
        rerankers=list(RERANKERS),
        modes=["fast", "balanced", "adaptive", "deep", "research"],
        web_search_enabled=settings.web_search_provider not in ("", "none"),
    )
