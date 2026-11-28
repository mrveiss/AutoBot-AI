# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""An unpinned sentence model fails when the chunker is built, not silently in a load fallback (#19430)."""

from __future__ import annotations

import pytest

from utils.semantic_chunker import AutoBotSemanticChunker
from utils.semantic_chunker_base import SENTENCE_EMBEDDING_MODEL


def test_the_pinned_default_constructs_without_loading() -> None:
    chunker = AutoBotSemanticChunker()
    assert chunker.embedding_model_name == SENTENCE_EMBEDDING_MODEL
    assert chunker._embedding_model is None


def test_an_unpinned_name_is_refused_at_construction() -> None:
    # The short name resolves on the Hub, but it is not a pinned repo id: before #19430 a load
    # failure here fell back to downloading a different model with no error.
    with pytest.raises(KeyError):
        AutoBotSemanticChunker(embedding_model="all-MiniLM-L6-v2")


def test_a_digest_mismatch_raises_and_returns_no_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """The loader verifies after loading and before returning; a mismatch is fatal, not a warning."""
    import sentence_transformers

    from autobot_shared import pinned_model_registry
    from utils.semantic_chunker_base import load_sentence_transformer

    loaded: list[str] = []
    monkeypatch.setattr(
        sentence_transformers, "SentenceTransformer", lambda name, revision, **kw: loaded.append(revision) or object()
    )

    def mismatch(repo_id: str, **_: object) -> None:
        raise pinned_model_registry.ModelIntegrityError(f"{repo_id}: sha256 mismatch")

    monkeypatch.setattr(pinned_model_registry, "verify_cached_model", mismatch)
    with pytest.raises(pinned_model_registry.ModelIntegrityError):
        load_sentence_transformer(SENTENCE_EMBEDDING_MODEL)
    assert loaded == [pinned_model_registry.get_pinned_revision(SENTENCE_EMBEDDING_MODEL)]
