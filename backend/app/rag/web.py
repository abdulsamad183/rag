"""Optional web retrieval tool.

No third-party search API keys: DuckDuckGo HTML is scraped with httpx +
BeautifulSoup, then each result page is fetched (SSRF-checked) for an excerpt.

Chat ``scope``:
  kb      — knowledge base only (default)
  kb_web  — KB + web, web rows labeled source_type=web
  web     — web only
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings
from app.core.errors import ValidationFailed
from app.core.logging import get_logger
from app.retrieval.base import RetrievedChunk
from app.utils.text import clean_text

logger = get_logger("web")

DDG_HTML = "https://html.duckduckgo.com/html/"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
MAX_PAGE_BYTES = 400_000
EXCERPT_CHARS = 900
FETCH_TIMEOUT = 12.0
SEARCH_TIMEOUT = 15.0
MAX_REDIRECTS = 3
WEB_TRUST = 0.4
_SKIP_TAGS = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "iframe"}


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
    """Web retrieval disabled."""

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
            or address.is_unspecified
        ):
            raise ValidationFailed(f"Blocked non-public address for host: {host}")


def unwrap_ddg_url(href: str, base: str = DDG_HTML) -> str:
    """Turn a DuckDuckGo result href (often /l/?uddg=...) into the real URL."""
    if not href:
        return ""
    absolute = urljoin(base, href)
    parsed = urlparse(absolute)
    query = parse_qs(parsed.query)
    if "uddg" in query:
        return unquote(query["uddg"][0])
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        return ""
    return absolute


def parse_ddg_html(html: str, max_results: int = 5) -> list[tuple[str, str, str]]:
    """Return (url, title, snippet) from DuckDuckGo HTML. No network."""
    soup = BeautifulSoup(html, "lxml")
    found: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for result in soup.select("div.result, div.web-result"):
        classes = result.get("class") or []
        if any("ad" in str(c).lower() for c in classes):
            continue
        anchor = result.select_one("a.result__a")
        if anchor is None:
            continue
        url = unwrap_ddg_url(str(anchor.get("href") or ""))
        if not url or url in seen:
            continue
        host = (urlparse(url).hostname or "").lower()
        if host.endswith("duckduckgo.com"):
            continue
        title = clean_text(anchor.get_text(" "))
        snippet_el = result.select_one(".result__snippet, .result__body")
        snippet = clean_text(snippet_el.get_text(" ")) if snippet_el else ""
        seen.add(url)
        found.append((url, title or host, snippet))
        if len(found) >= max_results:
            break
    return found


def extract_page_excerpt(html: str, fallback: str = "", limit: int = EXCERPT_CHARS) -> tuple[str, str]:
    """Return (title, excerpt) from an HTML page."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(_SKIP_TAGS):
        tag.decompose()
    title = clean_text(soup.title.get_text()) if soup.title else ""
    if not title:
        og = soup.find("meta", property="og:title")
        title = clean_text(str(og.get("content", ""))) if og else ""
    description = ""
    meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
    if meta:
        description = clean_text(str(meta.get("content", "")))
    paragraphs = [
        clean_text(p.get_text(" "))
        for p in soup.find_all("p")
        if len(clean_text(p.get_text(" "))) > 40
    ]
    body = " ".join(paragraphs[:8])
    excerpt = description
    if body:
        excerpt = f"{description} {body}".strip() if description else body
    if not excerpt:
        excerpt = fallback
    return title, excerpt[:limit]


def web_results_to_chunks(results: list[WebResult]) -> list[RetrievedChunk]:
    chunks: list[RetrievedChunk] = []
    for index, item in enumerate(results):
        stable = uuid.uuid5(uuid.NAMESPACE_URL, item.url)
        chunks.append(
            RetrievedChunk(
                chunk_id=stable,
                document_id=stable,
                content=item.excerpt or item.title,
                score=max(0.15, 0.7 - index * 0.08),
                scores={"web": 1.0},
                document_name=item.title or item.domain,
                source_type="web",
                heading=item.domain,
                section_path=item.domain,
                trust=WEB_TRUST,
                meta={
                    "url": item.url,
                    "domain": item.domain,
                    "retrieved_at": item.retrieved_at,
                    "origin": "web",
                },
            )
        )
    return chunks


class DuckDuckGoSearch(WebSearchTool):
    """HTML scrape of DuckDuckGo + page excerpts. No API key."""

    name = "ddg"

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.8",
        }

    async def search(self, query: str, max_results: int = 5) -> list[WebResult]:
        query = query.strip()
        if not query:
            return []
        assert_public_url(DDG_HTML)
        html = await self._get(DDG_HTML, params={"q": query}, request_timeout=SEARCH_TIMEOUT)
        hits = parse_ddg_html(html, max_results=max_results)
        if not hits:
            logger.warning("ddg_no_results", query=query[:120])
            return []

        semaphore = asyncio.Semaphore(3)

        async def load(hit: tuple[str, str, str]) -> WebResult | None:
            url, title, snippet = hit
            async with semaphore:
                return await self._fetch_result(url, title, snippet)

        loaded = await asyncio.gather(*[load(hit) for hit in hits], return_exceptions=True)
        results: list[WebResult] = []
        for item in loaded:
            if isinstance(item, WebResult):
                results.append(item)
            elif isinstance(item, Exception):
                logger.info("web_fetch_skipped", error=str(item)[:160])
        return results

    async def _fetch_result(self, url: str, title: str, snippet: str) -> WebResult | None:
        try:
            assert_public_url(url)
        except ValidationFailed:
            return None
        final_url, html = await self._get_html_following_redirects(url)
        if html:
            page_title, excerpt = extract_page_excerpt(html, fallback=snippet)
            title = page_title or title
        else:
            excerpt = snippet
        if not excerpt and not title:
            return None
        parsed = urlparse(final_url)
        return WebResult(
            url=final_url,
            title=title or parsed.netloc,
            domain=parsed.netloc,
            excerpt=excerpt or snippet,
        )

    async def _client_ctx(self, request_timeout: float) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(request_timeout, connect=5.0),
            headers=self._headers(),
        )

    async def _get_html_following_redirects(self, url: str) -> tuple[str, str]:
        owns = self._client is None
        client = await self._client_ctx(FETCH_TIMEOUT)
        current = url
        try:
            for _ in range(MAX_REDIRECTS + 1):
                assert_public_url(current)
                try:
                    response = await client.get(current)
                except httpx.HTTPError:
                    return current, ""
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location", "")
                    if not location:
                        return current, ""
                    current = urljoin(current, location)
                    continue
                if response.status_code >= 400:
                    return current, ""
                content_type = response.headers.get("content-type", "")
                text = response.text
                if "html" not in content_type.lower() and not text.lstrip().lower().startswith("<"):
                    return current, ""
                body = response.content[:MAX_PAGE_BYTES]
                return str(response.url) if response.url else current, body.decode("utf-8", errors="replace")
        finally:
            if owns:
                await client.aclose()
        return current, ""

    async def _get(
        self,
        url: str,
        params: dict[str, str] | None = None,
        request_timeout: float = FETCH_TIMEOUT,
    ) -> str:
        owns = self._client is None
        client = await self._client_ctx(request_timeout)
        try:
            response = await client.get(url, params=params)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = urljoin(str(response.url), response.headers.get("location", ""))
                if location:
                    assert_public_url(location)
                    response = await client.get(location)
            response.raise_for_status()
            return response.text
        finally:
            if owns:
                await client.aclose()


def get_web_search() -> WebSearchTool:
    settings = get_settings()
    provider = (settings.web_search_provider or "none").lower()
    if provider in ("", "none"):
        return NullWebSearch()
    if provider in ("ddg", "duckduckgo", "html"):
        return DuckDuckGoSearch()
    logger.warning("unknown_web_search_provider", provider=provider)
    return NullWebSearch()
