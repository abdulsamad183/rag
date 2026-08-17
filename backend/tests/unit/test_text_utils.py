from app.utils.text import (
    clean_text,
    content_words,
    cosine,
    estimate_tokens,
    extract_acronyms,
    extract_quoted,
    extract_years,
    jaccard,
    split_paragraphs,
    split_sentences,
    term_coverage,
    truncate_tokens,
)


def test_estimate_tokens_scales_with_length():
    assert estimate_tokens("") <= 1  # floor of 1 keeps budget math safe
    assert estimate_tokens("word " * 100) > estimate_tokens("word " * 10)


def test_clean_text_strips_control_chars_and_normalizes():
    assert clean_text("a\x00b\r\nc") == "a b c" or "\x00" not in clean_text("a\x00b\r\nc")


def test_split_sentences():
    text = "First sentence. Second one! Third? Done."
    sentences = split_sentences(text)
    assert len(sentences) == 4
    assert sentences[0].startswith("First")


def test_split_paragraphs():
    parts = split_paragraphs("para one\n\npara two\n\n\npara three")
    assert len(parts) == 3


def test_jaccard_identical_and_disjoint():
    assert jaccard("the quick brown fox", "the quick brown fox") == 1.0
    assert jaccard("alpha beta gamma", "delta epsilon zeta") == 0.0


def test_term_coverage():
    coverage = term_coverage("aurora retention policy", "the retention policy of aurora is 30 days")
    assert coverage == 1.0
    assert term_coverage("quantum entanglement", "aurora vector database") == 0.0


def test_cosine():
    assert abs(cosine([1, 0], [1, 0]) - 1.0) < 1e-9
    assert abs(cosine([1, 0], [0, 1])) < 1e-9


def test_truncate_tokens_bounds_length():
    text = "word " * 1000
    truncated = truncate_tokens(text, 50)
    assert estimate_tokens(truncated) <= 60  # small tolerance for boundary handling
    assert truncated


def test_extract_years():
    assert extract_years("results between 2019 and 2024") == [2019, 2024]
    assert extract_years("no years here") == []
    assert extract_years("call 555-1234-5678") == []


def test_extract_quoted():
    assert extract_quoted('find "exact phrase" here') == ["exact phrase"]


def test_extract_acronyms():
    acronyms = extract_acronyms("How does HNSW compare to IVF in RAG systems?")
    assert "HNSW" in acronyms and "IVF" in acronyms and "RAG" in acronyms


def test_content_words_removes_stopwords():
    words = content_words("what is the capital of France")
    assert "the" not in words and "of" not in words
    assert "capital" in words
