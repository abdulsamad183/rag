from collections.abc import Awaitable, Callable

from app.chunking.base import ChunkDraft, Chunker, ChunkingConfig
from app.chunking.fixed import FixedSizeChunker
from app.chunking.markdown import MarkdownAwareChunker
from app.chunking.paragraph import ParagraphChunker
from app.chunking.parent_child import ParentChildChunker
from app.chunking.recursive import RecursiveChunker
from app.chunking.semantic import SemanticChunker
from app.chunking.sentence import SentenceChunker

STRATEGIES = (
    "fixed",
    "sentence",
    "paragraph",
    "recursive",
    "markdown",
    "semantic",
    "parent_child",
    "hierarchical",  # alias: section-parent hierarchy via ParentChildChunker
)

EmbedFn = Callable[[list[str]], Awaitable[list[list[float]]]]


def get_chunker(strategy: str, embed_fn: EmbedFn | None = None) -> Chunker:
    match strategy:
        case "fixed":
            return FixedSizeChunker()
        case "sentence":
            return SentenceChunker()
        case "paragraph":
            return ParagraphChunker()
        case "markdown":
            return MarkdownAwareChunker()
        case "semantic":
            return SemanticChunker(embed_fn)
        case "parent_child" | "hierarchical":
            return ParentChildChunker()
        case _:
            return RecursiveChunker()


__all__ = [
    "STRATEGIES",
    "ChunkDraft",
    "Chunker",
    "ChunkingConfig",
    "get_chunker",
]
