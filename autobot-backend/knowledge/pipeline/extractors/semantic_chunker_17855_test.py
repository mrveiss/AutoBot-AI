# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
"""#17855: the chunker counts tokens with the shared estimator, not ``split()``."""

from autobot_shared.token_count import estimate_fast
from knowledge.pipeline.extractors.semantic_chunker import SemanticChunker


def test_estimate_is_the_shared_authority():
    chunker = SemanticChunker()
    for text in ("hello world " * 20, "日本語のテキスト" * 20, '{"a":1,"b":2}' * 10):
        assert chunker._estimate_tokens(text) == estimate_fast(text)


def test_cjk_text_is_split_by_max_tokens():
    """``len(text.split())`` counted each CJK segment as 1 token, so max_tokens never bound."""
    chunker = SemanticChunker(max_tokens=50, overlap=0)
    paragraph = "日本語のテキストです。" * 20
    text = "\n\n".join([paragraph] * 6)

    chunks = chunker._chunk_text(text)

    assert len(chunks) > 1
