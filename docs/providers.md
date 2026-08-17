# Providers

The RAG pipeline calls `llm.generate()` / `llm.stream()` / `llm.structured_output()`. It does not import OpenAI, Groq, Gemini, or Ollama SDKs outside `app/llm/`.

## LLM adapters

| Provider | Module | Default model (dev) |
| --- | --- | --- |
| OpenAI | `openai_compat.py` (`OpenAIProvider`) | `gpt-4o-mini` |
| Groq | same file (`GroqProvider`) | `llama-3.1-8b-instant` |
| Gemini | `gemini.py` | `gemini-2.0-flash` |
| Ollama | `ollama.py` | `llama3.2` |
| Mock | `mock.py` | `mock-small` (tests / offline) |

OpenAI and Groq share the OpenAI-compatible HTTP adapter; only base URL, auth header, and error mapping differ.

Embeddings are a **separate** registry (`app/embeddings/`). Groq is generation-only; collections using Groq for chat still need OpenAI, Gemini, or Ollama embeddings.

## Configuration

Set keys in `.env` (never in the frontend):

```
OPENAI_API_KEY=
GROQ_API_KEY=
GEMINI_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434
```

`GET /api/v1/providers` reports which providers are configured and which catalog models exist. The UI dropdowns bind to that response. When a provider is missing credentials, it stays visible but disabled.

## Model catalog

`app/config/model_catalog.py` lists models with:

- `supports_streaming`
- `supports_json`
- `supports_tools`
- `supports_embeddings`
- `supports_vision`
- token pricing (for cost estimates)

Unknown Ollama tags are assumed to support streaming + JSON only. If structured output fails, adapters fall back to parsing fenced JSON rather than crashing the pipeline.

## Adding a model

Add a row to the catalog. Do not scatter model names through retrieval or UI code. Provider defaults:

```
OPENAI_DEFAULT_MODEL=gpt-4o-mini
GROQ_DEFAULT_MODEL=llama-3.1-8b-instant
GEMINI_DEFAULT_MODEL=gemini-2.0-flash
OLLAMA_DEFAULT_MODEL=llama3.2
```

## Failures and fallback

Adapters retry with timeout + exponential backoff (`LLM_MAX_RETRIES`). Auth errors are not retried. Optional provider fallback (`allow_fallback` on the chat request) walks `get_fallback_chain()` and **records the switch in the trace**. It never happens silently.

## Local / privacy mode

`LOCAL_MODE=true` forces Ollama for generation and embeddings and disables web tools. The UI shows a LOCAL MODE badge.
