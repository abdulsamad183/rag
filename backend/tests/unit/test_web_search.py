import uuid

import httpx
import pytest
from pydantic import ValidationError

from app.core.errors import ValidationFailed
from app.rag.web import (
    DDG_HTML,
    DuckDuckGoSearch,
    WebResult,
    assert_public_url,
    extract_page_excerpt,
    get_web_search,
    parse_ddg_html,
    unwrap_ddg_url,
    web_results_to_chunks,
)
from app.schemas.chat import ChatRequest

DDG_FIXTURE = """
<html><body>
<div class="result results_links web-result">
  <a class="result__a" href="/l/?uddg=https%3A%2F%2Fen.wikipedia.org%2Fwiki%2FAurora">
    Aurora (encyclopedia)
  </a>
  <div class="result__snippet">Aurora is a polar light in the night sky.</div>
</div>
<div class="result result--ad">
  <a class="result__a" href="/l/?uddg=https%3A%2F%2Fads.example.com%2Fbuy">Buy now</a>
  <div class="result__snippet">Sponsored listing you should skip.</div>
</div>
<div class="result web-result">
  <a class="result__a" href="https://example.com/aurora-guide">Aurora Guide</a>
  <div class="result__snippet">A practical guide to the aurora borealis.</div>
</div>
<div class="result web-result">
  <a class="result__a" href="/l/?uddg=https%3A%2F%2Fduckduckgo.com%2Fabout">About DDG</a>
  <div class="result__snippet">Should be skipped because it is duckduckgo.com.</div>
</div>
</body></html>
"""

PAGE_HTML = """
<html>
<head>
  <title>Aurora Guide</title>
  <meta name="description" content="Lights in the polar sky.">
</head>
<body>
  <script>ignore this</script>
  <p>The aurora borealis is a natural light display in Earth's sky,
     predominantly seen in high-latitude regions.</p>
  <p>It is caused by disturbances in the magnetosphere caused by the solar wind.</p>
</body>
</html>
"""


def test_unwrap_ddg_redirect():
    href = "/l/?uddg=https%3A%2F%2Fen.wikipedia.org%2Fwiki%2FAurora&rut=abc"
    assert unwrap_ddg_url(href) == "https://en.wikipedia.org/wiki/Aurora"


def test_unwrap_ddg_passthrough_absolute():
    assert unwrap_ddg_url("https://example.com/page") == "https://example.com/page"


def test_parse_ddg_html_skips_ads_and_ddg_hosts():
    hits = parse_ddg_html(DDG_FIXTURE, max_results=10)
    urls = [url for url, _, _ in hits]
    assert urls == [
        "https://en.wikipedia.org/wiki/Aurora",
        "https://example.com/aurora-guide",
    ]
    assert hits[0][1] == "Aurora (encyclopedia)"
    assert "polar light" in hits[0][2]


def test_extract_page_excerpt():
    title, excerpt = extract_page_excerpt(PAGE_HTML, fallback="fallback")
    assert title == "Aurora Guide"
    assert "Lights in the polar sky" in excerpt
    assert "magnetosphere" in excerpt
    assert "ignore this" not in excerpt


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/x",
        "http://127.0.0.1/secret",
        "http://localhost/admin",
        "http://10.0.0.8/internal",
        "http://192.168.1.10/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://0.0.0.0/",
        "http://user:pass@example.com/",
    ],
)
def test_assert_public_url_blocks_private_targets(url: str):
    with pytest.raises(ValidationFailed):
        assert_public_url(url)


def test_web_results_to_chunks_are_synthetic_and_stable():
    result = WebResult(
        url="https://example.com/aurora",
        title="Aurora",
        domain="example.com",
        excerpt="Polar lights.",
    )
    chunks = web_results_to_chunks([result])
    assert len(chunks) == 1
    assert chunks[0].source_type == "web"
    assert chunks[0].meta["url"] == result.url
    assert chunks[0].chunk_id == uuid.uuid5(uuid.NAMESPACE_URL, result.url)
    assert chunks[0].trust == 0.4


def test_get_web_search_defaults_to_none_in_tests():
    assert get_web_search().name == "none"


def test_get_web_search_ddg(monkeypatch):
    monkeypatch.setattr(
        "app.rag.web.get_settings",
        lambda: type("S", (), {"web_search_provider": "ddg"})(),
    )
    assert get_web_search().name == "ddg"


async def test_ddg_search_with_mock_transport(monkeypatch):
    monkeypatch.setattr("app.rag.web.assert_public_url", lambda url: None)

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host or ""
        if "duckduckgo.com" in host:
            assert request.url.params.get("q") == "aurora"
            return httpx.Response(200, text=DDG_FIXTURE, headers={"content-type": "text/html"})
        if host == "en.wikipedia.org":
            return httpx.Response(200, text=PAGE_HTML, headers={"content-type": "text/html"})
        if host == "example.com":
            return httpx.Response(200, text=PAGE_HTML, headers={"content-type": "text/html"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
        tool = DuckDuckGoSearch(client=client)
        results = await tool.search("aurora", max_results=5)
    assert [item.url for item in results] == [
        "https://en.wikipedia.org/wiki/Aurora",
        "https://example.com/aurora-guide",
    ]
    assert results[0].title == "Aurora Guide"
    assert "magnetosphere" in results[0].excerpt


def test_chat_request_web_allows_empty_collections():
    req = ChatRequest(message="hello", collection_ids=[], scope="web")
    assert req.scope == "web"
    assert req.collection_ids == []


def test_chat_request_kb_requires_collections():
    with pytest.raises(ValidationError):
        ChatRequest(message="hello", collection_ids=[], scope="kb")


def test_chat_request_kb_web_requires_collections():
    with pytest.raises(ValidationError):
        ChatRequest(message="hello", collection_ids=[], scope="kb_web")


def test_ddg_html_constant_is_public_https():
    assert DDG_HTML.startswith("https://")
