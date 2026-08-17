import pytest

from app.chunking import get_chunker
from app.chunking.base import ChunkingConfig, pack_units, split_with_overlap
from app.chunking.recursive import RecursiveChunker
from app.parsers.base import ParsedBlock, ParsedDocument

LONG_TEXT = (
    "Aurora is a distributed vector database. " * 30
    + "It stores vectors in HNSW graphs for fast search. " * 30
)


def make_document(blocks: list[ParsedBlock]) -> ParsedDocument:
    return ParsedDocument(title="test-doc", source_type="txt", blocks=blocks)


def text_doc(text: str) -> ParsedDocument:
    return make_document([ParsedBlock(type="text", text=text)])


def test_split_with_overlap_respects_size():
    pieces = split_with_overlap("word " * 500, size=200, overlap=40)
    assert len(pieces) > 1
    assert all(len(p) <= 220 for p in pieces)  # word boundary slack


def test_split_with_overlap_has_overlap():
    pieces = split_with_overlap("alpha bravo charlie delta echo " * 40, size=200, overlap=60)
    tail = pieces[0][-40:]
    assert any(word in pieces[1] for word in tail.split()[:3])


def test_pack_units_merges_small():
    units = [f"sentence number {i}." for i in range(20)]
    chunks = pack_units(units, size=120)
    assert all(len(c) <= 140 for c in chunks)
    assert len(chunks) < 20


@pytest.mark.parametrize("strategy", ["fixed", "sentence", "paragraph", "recursive"])
async def test_basic_strategies_produce_bounded_chunks(strategy):
    chunker = get_chunker(strategy)
    config = ChunkingConfig(strategy=strategy, chunk_size=300, chunk_overlap=50)
    drafts = await chunker.chunk(text_doc(LONG_TEXT), config)
    assert len(drafts) >= 2
    assert all(d.content for d in drafts)
    assert all(len(d.content) <= 600 for d in drafts)


async def test_markdown_chunker_respects_sections():
    doc = make_document(
        [
            ParsedBlock(type="text", text="Intro paragraph about Aurora.",
                        heading="Overview", section_path="Overview"),
            ParsedBlock(type="text", text="Latency was 18 ms in 2024. " * 20,
                        heading="Benchmarks", section_path="Benchmarks"),
            ParsedBlock(type="text", text="Snapshots are kept 30 days.",
                        heading="Retention", section_path="Benchmarks > Retention"),
        ]
    )
    chunker = get_chunker("markdown")
    drafts = await chunker.chunk(doc, ChunkingConfig(chunk_size=300, chunk_overlap=40))
    assert drafts
    # no chunk mixes content from two different sections
    for draft in drafts:
        assert not ("Intro paragraph" in draft.content and "Latency" in draft.content)


async def test_parent_child_chunker_builds_hierarchy():
    chunker = get_chunker("parent_child")
    config = ChunkingConfig(chunk_size=200, chunk_overlap=30, parent_chunk_size=800)
    drafts = await chunker.chunk(text_doc(LONG_TEXT), config)
    parents = [d for d in drafts if d.level == "section"]
    children = [d for d in drafts if d.level == "chunk"]
    assert parents and children
    for child in children:
        assert child.parent_index is not None
        parent = drafts[child.parent_index]
        assert parent.level == "section"


async def test_semantic_chunker_falls_back_without_embedder():
    chunker = get_chunker("semantic")
    drafts = await chunker.chunk(
        text_doc(LONG_TEXT), ChunkingConfig(chunk_size=300, chunk_overlap=50)
    )
    assert drafts


async def test_semantic_chunker_splits_on_topic_shift():
    async def embed(texts: list[str]) -> list[list[float]]:
        # two artificial topics: vectors depend on which keyword appears
        return [[1.0, 0.0] if "cooking" in t.lower() else [0.0, 1.0] for t in texts]

    topic_a = "Cooking pasta requires salted water. " * 5
    topic_b = "Vector indexes use graph traversal. " * 5
    chunker = get_chunker("semantic", embed_fn=embed)
    drafts = await chunker.chunk(
        text_doc(topic_a + topic_b), ChunkingConfig(chunk_size=2000, chunk_overlap=0)
    )
    assert len(drafts) >= 2
    assert "cooking" in drafts[0].content.lower()
    assert "graph" in drafts[-1].content.lower()


def test_get_chunker_unknown_falls_back_to_recursive():
    assert isinstance(get_chunker("does_not_exist"), RecursiveChunker)
