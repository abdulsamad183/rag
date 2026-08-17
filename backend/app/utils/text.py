"""Deterministic text utilities: tokens, sentences, normalization, similarity."""

from __future__ import annotations

import math
import re
import unicodedata

_WS = re.compile(r"\s+")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")
_WORD = re.compile(r"[A-Za-z0-9_'-]+")

# Rough heuristic (~4 chars/token for English) — avoids a heavyweight tokenizer
# dependency; used only for context budgeting, never billing.
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / CHARS_PER_TOKEN))


def normalize_whitespace(text: str) -> str:
    return _WS.sub(" ", text).strip()


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\x00", "")
    # collapse >2 consecutive newlines, strip trailing spaces per line
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_END.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def tokenize_words(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text)]


_STOPWORDS = frozenset(
    """a an and are as at be by for from has have in is it its of on or that the this to was
    were will with what which who whom how why when where does do did can could should would
    about between into through during before after above below over under again further then
    once here there all any both each few more most other some such no nor not only own same
    so than too very s t just don now""".split()
)


def content_words(text: str) -> list[str]:
    return [w for w in tokenize_words(text) if w not in _STOPWORDS and len(w) > 1]


def jaccard(a: str, b: str) -> float:
    sa, sb = set(content_words(a)), set(content_words(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def term_coverage(query: str, text: str) -> float:
    """Fraction of query content words present in text."""
    terms = set(content_words(query))
    if not terms:
        return 0.0
    body = set(content_words(text))
    return len(terms & body) / len(terms)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def truncate_tokens(text: str, max_tokens: int) -> str:
    limit = max_tokens * CHARS_PER_TOKEN
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + " …"


def extract_years(text: str) -> list[int]:
    return [int(y) for y in re.findall(r"\b(19[5-9]\d|20[0-4]\d)\b", text)]


def extract_quoted(text: str) -> list[str]:
    return re.findall(r"\"([^\"]{2,80})\"|'([^']{2,80})'", text) and [
        a or b for a, b in re.findall(r"\"([^\"]{2,80})\"|'([^']{2,80})'", text)
    ]


def extract_acronyms(text: str) -> list[str]:
    return re.findall(r"\b[A-Z][A-Z0-9]{1,9}\b", text)
