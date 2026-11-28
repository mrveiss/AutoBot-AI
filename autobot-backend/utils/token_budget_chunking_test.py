# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14485: the extracted token-budget chunker is byte-identical to the pipeline's algorithm.

The reference below is the pipeline chunker's algorithm, verbatim (as pinned by the #17855
test), including its offset rule. The same corpus is also run through the live pipeline class
so the extraction is proven exact against what ships, not only against a copy.
"""

import asyncio
import re
import uuid

import pytest

from knowledge.pipeline.base import PipelineContext
from knowledge.pipeline.extractors.semantic_chunker import SemanticChunker
from utils.token_budget_chunking import TokenBudgetChunk, chunk_by_token_budget


def _reference_chunks(text: str, max_tokens: int, overlap: int) -> list[str]:
    """The chunker as it was before the extraction: `len(text.split())` as the token count."""
    segments = [s.strip() for s in re.split(r"\n\s*\n", text) if s.strip()]
    split: list[str] = []
    for segment in segments:
        if len(segment) > max_tokens * 4:
            split.extend(re.split(r"(?<=[.!?])\s+", segment))
        else:
            split.append(segment)
    chunks, current, current_tokens = [], [], 0
    for segment in split:
        n = len(segment.split())
        if current_tokens + n > max_tokens and current:
            chunks.append(" ".join(current))
            current = current[-overlap:] if overlap else []
            current_tokens = sum(len(s.split()) for s in current)
        current.append(segment)
        current_tokens += n
    if current:
        chunks.append(" ".join(current))
    return chunks


def _reference_offsets(full: str, chunk: str, idx: int, max_tokens: int) -> tuple[int, int]:
    start = full.find(chunk)
    if start == -1:
        start = idx * max_tokens * 4
    return start, start + len(chunk)


_ENGLISH = "The quick brown fox jumps over the lazy dog. Pack my box with five dozen liquor jugs! Why?"
_CJK = "日本語のテキストです。これは文章の例です。さらに続きます！本当ですか？"
_PARAS = "\n\n".join(f"Paragraph {i} has some words in it, about {i} things." for i in range(40))
_LONG = " ".join(f"Sentence number {i} is here." for i in range(60))
_CORPORA = {
    "empty": "",
    "blank only": "\n\n  \n\n",
    "one short": "Just one short paragraph.",
    "many paragraphs": _PARAS,
    "long paragraph": _LONG,
    "unicode": "\n\n".join([_CJK * 4, "Ünïcödé wörds — naïve café. " * 10, _ENGLISH]),
    "duplicates": "\n\n".join(["same words here"] * 30 + ["tail"]),
    "mixed": "\n\n".join([_ENGLISH * 3, _CJK * 4, _LONG, "short", "", _ENGLISH * 12]),
}
_VARIANTS = [(512, 50), (40, 0), (40, 2), (15, 1), (8, 0), (100, 3), (10, 500), (5, 1000)]


@pytest.mark.parametrize("name", sorted(_CORPORA))
@pytest.mark.parametrize(("max_tokens", "overlap"), _VARIANTS)
def test_matches_the_reference_algorithm(name: str, max_tokens: int, overlap: int) -> None:
    text = _CORPORA[name]
    got = chunk_by_token_budget(text, max_tokens=max_tokens, overlap=overlap)
    ref = _reference_chunks(text, max_tokens, overlap)
    assert [c.text for c in got] == ref
    assert [(c.start_offset, c.end_offset) for c in got] == [
        _reference_offsets(text, c, i, max_tokens) for i, c in enumerate(ref)
    ]


def _run_pipeline(text: str, max_tokens: int, overlap: int) -> list:
    chunker = SemanticChunker(max_tokens=max_tokens, overlap=overlap)
    ctx = PipelineContext()
    ctx.document_id = uuid.uuid4()

    async def collect() -> list:
        return [c async for c in chunker.process(text, ctx)]

    return asyncio.run(collect())


@pytest.mark.parametrize("name", sorted(_CORPORA))
@pytest.mark.parametrize(("max_tokens", "overlap"), _VARIANTS)
def test_matches_the_live_pipeline_class(name: str, max_tokens: int, overlap: int) -> None:
    text = _CORPORA[name]
    got = chunk_by_token_budget(text, max_tokens=max_tokens, overlap=overlap)
    live = _run_pipeline(text, max_tokens, overlap)
    assert [(c.text, c.start_offset, c.end_offset) for c in got] == [
        (p.content, p.start_offset, p.end_offset) for p in live
    ]


def test_the_corpus_exercises_more_than_one_chunking_shape() -> None:
    sizes = {len(chunk_by_token_budget(_CORPORA["mixed"], max_tokens=m, overlap=1)) for m in (8, 15, 40, 100)}
    assert len(sizes) > 1


def test_a_duplicate_chunk_is_located_at_its_first_occurrence() -> None:
    text = "x y z. x y z. x y z."
    got = chunk_by_token_budget(text, max_tokens=1, overlap=0)
    assert [(c.text, c.start_offset) for c in got] == [("x y z.", 0)] * 3


def test_a_chunk_absent_from_the_source_falls_back_to_the_index_offset() -> None:
    got = chunk_by_token_budget("a\n\nb\n\nc\n\nd", max_tokens=2, overlap=0)
    assert [c.text for c in got] == ["a b", "c d"]
    assert [c.start_offset for c in got] == [0, 8]


def test_defaults_and_return_type() -> None:
    got = chunk_by_token_budget("hello world")
    assert got == [TokenBudgetChunk(text="hello world", start_offset=0, end_offset=11)]
    assert chunk_by_token_budget("") == []
