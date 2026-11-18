# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Token-budget text chunking, the one home of the ingest pipeline's algorithm (#14485).

The knowledge pipeline's ``chunk_text`` extractor carried its own chunker beside the
``SemanticChunkerBase`` family in ``utils/semantic_chunker*.py``. The two answer different
questions (embedding-similarity boundaries vs. a word budget), so this is a *named strategy*
of the canonical chunker family rather than a second chunker class: a pure function, no
state, plain data out. The pipeline class becomes a thin adapter over it once #17855 lands.

It lives in its own module because ``semantic_chunker_base.py`` is a 400-line class and the
strategy shares nothing with it but the concept.

Behaviour is the pre-existing pipeline algorithm, byte for byte: a word count as the token
estimate (``len(text.split())``; #17855 routes the pipeline through
``autobot_shared.token_count.estimate(method="words")``, which is the same number), segments
joined with a space, and overlap measured in whole *segments*, not tokens.
"""

import re
from dataclasses import dataclass
from typing import List

#: Characters-per-token factor behind both the long-segment threshold and the offset fallback.
_CHARS_PER_TOKEN = 4

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class TokenBudgetChunk:
    """A chunk and where it sits in the source text."""

    text: str
    start_offset: int
    end_offset: int


def _word_count(text: str) -> int:
    """Token estimate: whitespace-delimited words."""
    return len(text.split())


def split_into_segments(text: str, max_tokens: int) -> List[str]:
    """Blank-line paragraphs; a paragraph over ``max_tokens * 4`` chars splits on sentence ends."""
    paragraphs = [p.strip() for p in _PARAGRAPH_BREAK.split(text) if p.strip()]
    result: List[str] = []
    for paragraph in paragraphs:
        if len(paragraph) > max_tokens * _CHARS_PER_TOKEN:
            result.extend(_SENTENCE_END.split(paragraph))
        else:
            result.append(paragraph)
    return result


def _accumulate(segments: List[str], max_tokens: int, overlap: int) -> List[str]:
    """Fill chunks up to ``max_tokens`` words, carrying the last ``overlap`` segments forward."""
    chunks: List[str] = []
    current: List[str] = []
    current_tokens = 0
    for segment in segments:
        segment_tokens = _word_count(segment)
        if current_tokens + segment_tokens > max_tokens and current:
            chunks.append(" ".join(current))
            current = current[-overlap:] if overlap else []
            current_tokens = sum(_word_count(s) for s in current)
        current.append(segment)
        current_tokens += segment_tokens
    if current:
        chunks.append(" ".join(current))
    return chunks


def chunk_offsets(full_text: str, chunk: str, index: int, max_tokens: int) -> tuple[int, int]:
    """First occurrence of ``chunk`` in ``full_text``; ``index * max_tokens * 4`` when absent."""
    start = full_text.find(chunk)
    if start == -1:
        start = index * max_tokens * _CHARS_PER_TOKEN
    return start, start + len(chunk)


def chunk_by_token_budget(text: str, *, max_tokens: int = 512, overlap: int = 50) -> List[TokenBudgetChunk]:
    """Chunk ``text`` to a word budget, with segment overlap, and locate each chunk."""
    texts = _accumulate(split_into_segments(text, max_tokens), max_tokens, overlap)
    chunks = []
    for index, chunk in enumerate(texts):
        start, end = chunk_offsets(text, chunk, index, max_tokens)
        chunks.append(TokenBudgetChunk(text=chunk, start_offset=start, end_offset=end))
    return chunks
