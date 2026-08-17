"""The mock provider must speak every pipeline dialect — these tests pin its
contract so integration tests stay meaningful."""

import json

from app.embeddings.mock import MockEmbeddings
from app.llm.base import ChatMessage
from app.llm.mock import MockLLMProvider
from app.rag import prompts
from app.utils.text import cosine


def user(content: str) -> list[ChatMessage]:
    return [ChatMessage(role="user", content=content)]


async def test_generation_quotes_evidence_with_citations():
    llm = MockLLMProvider()
    prompt = prompts.ANSWER_GENERATOR_USER.format(
        conversation_context="",
        query="What is the retention policy?",
        evidence='<evidence id=1 document="r.md">\nSnapshots are kept for 30 days.\n</evidence>',
    )
    result = await llm.generate(user(prompt))
    assert "[1]" in result.text
    assert "30 days" in result.text
    assert result.usage.total_tokens > 0


async def test_generation_abstains_without_evidence():
    llm = MockLLMProvider()
    prompt = prompts.ANSWER_GENERATOR_USER.format(
        conversation_context="", query="What is X?", evidence=""
    )
    result = await llm.generate(user(prompt))
    assert result.text.startswith("INSUFFICIENT_EVIDENCE")


async def test_query_analysis_returns_valid_json():
    llm = MockLLMProvider()
    result = await llm.structured_output(
        user(prompts.QUERY_ANALYZER_USER.format(query="Compare 2024 versus 2025 results")),
        schema_hint=prompts.QUERY_ANALYZER_SCHEMA,
    )
    assert result["query_type"] == "comparison"


async def test_claim_extraction_parses_answer():
    llm = MockLLMProvider()
    answer = "Aurora achieved 93 percent recall in 2025. The latency was 9 milliseconds. [1]"
    result = await llm.structured_output(
        user(prompts.CLAIM_EXTRACTOR_USER.format(answer=answer)),
        schema_hint=prompts.CLAIM_EXTRACTOR_SCHEMA,
    )
    assert len(result["claims"]) >= 1
    assert "93 percent" in result["claims"][0]["text"]


async def test_verification_supports_all_claims():
    llm = MockLLMProvider()
    result = await llm.structured_output(
        user(prompts.CLAIM_VERIFIER_USER.format(
            evidence="[1] Aurora keeps snapshots 30 days.",
            claims="1. Snapshots are kept 30 days.\n2. WAL is kept 7 days.",
        )),
        schema_hint=prompts.CLAIM_VERIFIER_SCHEMA,
    )
    assert len(result["verdicts"]) == 2
    assert all(v["verdict"] == "SUPPORTED" for v in result["verdicts"])


async def test_streaming_reassembles_to_full_text():
    llm = MockLLMProvider()
    messages = user("Just say something.")
    full = await llm.generate(messages)
    streamed = ""
    async for event in llm.stream(messages):
        if event.kind == "delta":
            streamed += event.text
        else:
            assert event.usage is not None
    assert streamed.strip() == full.text.strip()


async def test_rerank_scores_json():
    llm = MockLLMProvider()
    prompt = (
        "Query: q\n\nPassages:\n[0] first passage\n[1] second passage\n\n"
        "Score every passage 0-10 for how directly it helps answer the query."
    )
    result = await llm.generate(user(prompt))
    parsed = json.loads(result.text)
    assert {item["id"] for item in parsed["scores"]} == {0, 1}


async def test_mock_embeddings_similarity_makes_sense():
    embedder = MockEmbeddings()
    result = await embedder.embed([
        "aurora snapshot retention policy days",
        "retention policy for aurora snapshots",
        "recipe for chocolate cake with frosting",
    ])
    assert result.dimension == 64
    same_topic = cosine(result.vectors[0], result.vectors[1])
    different_topic = cosine(result.vectors[0], result.vectors[2])
    assert same_topic > different_topic


async def test_mock_embeddings_deterministic():
    embedder = MockEmbeddings()
    first = await embedder.embed(["stable text"])
    second = await embedder.embed(["stable text"])
    assert first.vectors == second.vectors
