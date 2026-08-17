"""Optional web retrieval tool.

Scope selection (knowledge base only / KB + web / web only) is part of the
chat API. The default deployment ships ``NullWebSearch`` (web disabled);
adding a real provider means implementing ``WebSearchTool`` and registering
it in ``get_web_search`` — the pipeline, labeling, and UI already handle
web-sourced evidence.

Security: any concrete implementation MUST call ``assert_public_url`` on
every URL it fetches (SSRF defense), and web results are always labeled
``source_type="web"`` so external content is never silently mixed into
local-KB answers.
"""

from __future__ import annotations

import ipaddress
import socket
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlparse

from app.config import get_settings
from app.core.errors import ValidationFailed


@dataclass
class WebResult:
    url: str
    title: str
    domain: str
    excerpt: str
    published_at: str = ""
    retrieved_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class WebSearchTool(ABC):
    name: str = ""

    @abstractmethod
    async def search(self, query: str, max_results: int = 5) -> list[WebResult]: ...


class NullWebSearch(WebSearchTool):
    """Web retrieval disabled (default, and forced in LOCAL_MODE)."""

    name = "none"

    async def search(self, query: str, max_results: int = 5) -> list[WebResult]:
        return []


def assert_public_url(url: str) -> None:
    """SSRF guard: https/http only, no credentials, no private/loopback/link-local
    targets. Must be called by every web tool before fetching."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValidationFailed(f"Blocked non-HTTP URL scheme: {parsed.scheme}")
    if parsed.username or parsed.password:
        raise ValidationFailed("Blocked URL with embedded credentials")
    host = parsed.hostname or ""
    if not host:
        raise ValidationFailed("Blocked URL without hostname")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValidationFailed(f"Cannot resolve host: {host}") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
        ):
            raise ValidationFailed(f"Blocked non-public address for host: {host}")


def get_web_search() -> WebSearchTool:
    settings = get_settings()
    if settings.local_mode or settings.web_search_provider in ("", "none"):
        return NullWebSearch()
    # Extension point: register concrete providers here, e.g.
    #   if settings.web_search_provider == "tavily": return TavilySearch(...)
    return NullWebSearch()
