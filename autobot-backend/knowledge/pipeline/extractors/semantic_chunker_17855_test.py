# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
"""#17855: the chunker counts through the shared estimator and its output is unchanged.

`max_tokens` was tuned in whitespace words, so the chunker asks the shared authority for the
``words`` method. The reference below is the pre-de-fork algorithm, verbatim, so the equality
test proves chunk boundaries did not move.
"""

import re

import pytest

from autobot_shared.token_count import estimate
from knowledge.pipeline.extractors.semantic_chunker import SemanticChunker


def _reference_chunks(text: str, max_tokens: int, overlap: int) -> list[str]:
    """The chunker as it was before #17855: `len(text.split())` as the token count."""
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


_ENGLISH = "The quick brown fox jumps over the lazy dog. Pack my box with five dozen liquor jugs! Why?"
_CJK = "日本語のテキストです。これは文章の例です。さらに続きます！本当ですか？"
_CORPUS = "\n\n".join(
    ([_ENGLISH * 3, _CJK * 4, _ENGLISH, "Mixed 日本語 and English words together. " * 12] * 6)
    + ["short", "", _ENGLISH * 12]
)


@pytest.mark.parametrize(("max_tokens", "overlap"), [(512, 50), (40, 0), (40, 2), (15, 1), (8, 0), (100, 3)])
def test_chunk_boundaries_are_identical_to_the_pre_defork_chunker(max_tokens: int, overlap: int) -> None:
    chunker = SemanticChunker(max_tokens=max_tokens, overlap=overlap)
    got = chunker._chunk_text(_CORPUS)
    assert got == _reference_chunks(_CORPUS, max_tokens, overlap)
    assert len(got) > 1 or max_tokens == 512


def test_the_corpus_exercises_more_than_one_chunking_shape() -> None:
    sizes = {len(SemanticChunker(max_tokens=m, overlap=1)._chunk_text(_CORPUS)) for m in (8, 15, 40, 100)}
    assert len(sizes) > 1


def test_estimate_is_the_shared_authority() -> None:
    chunker = SemanticChunker()
    for text in ("hello world " * 20, "日本語のテキスト" * 20, ""):
        assert chunker._estimate_tokens(text) == estimate(text, method="words") == len(text.split())


def test_an_unknown_method_is_refused() -> None:
    with pytest.raises(ValueError):
        estimate("x", method="bytes")
