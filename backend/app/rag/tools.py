"""Generic tool system.

Tools wrap deterministic capabilities (search, document lookup, claim checks)
behind a uniform contract: name, description, JSON input/output schemas,
timeout, and error containment. Research features consume them directly;
they are also the substrate for future agentic workflows (docs/roadmap).

Authorization: a ToolRegistry is built per-request with an allow-list —
callers can only invoke tools the registry exposes.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger

logger = get_logger("tools")


@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    error: str = ""


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    handler: Callable[..., Awaitable[Any]]
    timeout_seconds: float = 20.0

    async def run(self, **kwargs: Any) -> ToolResult:
        try:
            data = await asyncio.wait_for(self.handler(**kwargs), timeout=self.timeout_seconds)
            return ToolResult(ok=True, data=data)
        except TimeoutError:
            logger.warning("tool_timeout", tool=self.name)
            return ToolResult(ok=False, error=f"tool '{self.name}' timed out")
        except Exception as exc:  # noqa: BLE001 — tools must contain failures
            logger.warning("tool_failed", tool=self.name, error=str(exc)[:200])
            return ToolResult(ok=False, error=str(exc)[:300])


@dataclass
class ToolRegistry:
    tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self.tools.get(name)

    async def invoke(self, name: str, **kwargs: Any) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult(ok=False, error=f"tool '{name}' is not authorized in this context")
        return await tool.run(**kwargs)

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
                "output_schema": t.output_schema,
            }
            for t in self.tools.values()
        ]


def build_retrieval_tools(context) -> ToolRegistry:  # context: RetrievalContext
    """Standard tool set bound to a retrieval context."""
    from app.repositories import chunks as chunk_repo
    from app.retrieval.base import Query
    from app.retrieval.registry import build_strategies

    strategies = build_strategies()
    registry = ToolRegistry()

    def _search_handler(strategy_name: str):
        async def handler(query: str, top_k: int = 8) -> list[dict[str, Any]]:
            result = await strategies[strategy_name].retrieve(Query(text=query), context)
            return [c.as_trace_dict() for c in result.chunks[:top_k]]

        return handler

    for name, description in (
        ("search_vector", "Semantic vector search over the selected collections"),
        ("search_keyword", "Exact keyword/full-text search (names, IDs, codes)"),
        ("search_hybrid", "Hybrid vector+keyword search with fusion"),
        ("search_graph", "Knowledge-graph entity search with neighbor expansion"),
    ):
        strategy_key = name.replace("search_", "")
        if strategy_key in strategies:
            registry.register(
                Tool(
                    name=name,
                    description=description,
                    input_schema={"query": "string", "top_k": "int (default 8)"},
                    output_schema={"chunks": "list of scored chunk previews"},
                    handler=_search_handler(strategy_key),
                )
            )

    async def get_document_chunks(document_id: str, limit: int = 5) -> list[dict[str, Any]]:
        import uuid as uuid_module

        chunks = await chunk_repo.sibling_chunks_by_document(
            context.session, uuid_module.UUID(document_id), limit=limit
        )
        return [c.as_trace_dict() for c in chunks]

    registry.register(
        Tool(
            name="get_document",
            description="Fetch the leading chunks of a specific document",
            input_schema={"document_id": "uuid", "limit": "int (default 5)"},
            output_schema={"chunks": "list of chunk previews"},
            handler=get_document_chunks,
        )
    )
    return registry
