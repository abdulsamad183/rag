from app.llm.base import LLMProvider
from app.reranking.base import NoopReranker, Reranker
from app.reranking.lexical import LexicalReranker
from app.reranking.llm import LLMReranker

RERANKERS = ("none", "lexical", "llm")


def get_reranker(name: str, llm: LLMProvider | None = None) -> Reranker:
    if name == "llm" and llm is not None:
        return LLMReranker(llm)
    if name == "llm":
        # No LLM available for reranking — degrade deterministically.
        return LexicalReranker()
    if name == "lexical":
        return LexicalReranker()
    return NoopReranker()


__all__ = ["RERANKERS", "LLMReranker", "LexicalReranker", "NoopReranker", "Reranker", "get_reranker"]
