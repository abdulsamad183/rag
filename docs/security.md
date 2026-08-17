# Security

## Secrets

- API keys live in server env / `.env` (gitignored)
- The frontend never receives provider credentials
- Logs redact secrets; prompts are not dumped at info level

## Uploads

- Extension + MIME allow-list (PDF, TXT, MD, DOCX, HTML, CSV, JSON)
- Size cap (`MAX_UPLOAD_MB`)
- Filenames sanitized; storage paths are generated UUIDs (no user path traversal)
- Content hash dedupe avoids double indexing

## Prompt injection

Retrieved chunks are **untrusted data**. Prompts keep distinct blocks:

1. System / developer instructions
2. User query
3. Evidence (explicitly labeled as documents, not instructions)
4. Tool output

The generator is instructed to ignore instructions found inside evidence. Verification still has to catch residual leakage — abstention is preferred over following a hostile chunk.

## Web / SSRF

`assert_public_url` rejects loopback, link-local, private, and metadata IPs before any fetch. Web results are labeled `source_type=web` and are never mixed into a KB-only answer without the user selecting that scope.

## Runtime

- CORS allow-list
- Per-route rate limits (chat, uploads, evaluations)
- Auth is currently a single development user (`CurrentUser`) — replace with real identity before exposing the API
- `LOCAL_MODE` keeps bytes on-box (Ollama only)

## What this is not

v0.1 is not a multi-tenant enterprise control plane. Do not put untrusted users on a shared instance without adding authentication, authorization, and network isolation.
