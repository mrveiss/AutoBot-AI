# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The KB keeps the stored embedding model and says so when it differs (#19377)."""

from __future__ import annotations

import pytest

import knowledge.embedding_model_resolution as res
from autobot_shared.embedding_model import EmbeddingSpace


@pytest.fixture(autouse=True)
def _no_switched_space(monkeypatch):
    """The cases below are the pre-switch rules; a switched space is opted into per test."""
    monkeypatch.setattr(res, "active_embedding_space", lambda: None)


def test_nothing_stored_uses_the_active_model(monkeypatch):
    monkeypatch.setattr(res, "active_embedding_model", lambda: "nomic-embed-text:latest")
    assert res.resolve_kb_embedding_model(None) == "nomic-embed-text:latest"


def test_a_stored_model_that_differs_is_kept_and_reported(monkeypatch):
    monkeypatch.setattr(res, "active_embedding_model", lambda: "mxbai-embed-large:latest")
    warnings = []
    monkeypatch.setattr(res.logger, "warning", lambda msg, *a: warnings.append(msg % a))

    assert res.resolve_kb_embedding_model("nomic-embed-text:latest") == "nomic-embed-text:latest"
    assert len(warnings) == 1 and "keeps the stored embedding model" in warnings[0] and "#19379" in warnings[0]


def test_a_stored_model_equal_to_the_active_one_is_quiet(monkeypatch):
    monkeypatch.setattr(res, "active_embedding_model", lambda: "nomic-embed-text:latest")
    warnings = []
    monkeypatch.setattr(res.logger, "warning", lambda *a: warnings.append(a))

    assert res.resolve_kb_embedding_model("nomic-embed-text:latest") == "nomic-embed-text:latest"
    assert warnings == []


def test_a_switched_space_wins_over_the_stored_model(monkeypatch):
    """#19379: after cutover the old facts still carry the old model; the record decides."""
    monkeypatch.setattr(res, "active_embedding_space", lambda: EmbeddingSpace("bge-m3:latest", "kb_bge", 2))
    assert res.resolve_kb_embedding_model("nomic-embed-text:latest") == "bge-m3:latest"


def test_a_legacy_record_without_a_collection_keeps_the_stored_rule(monkeypatch):
    monkeypatch.setattr(res, "active_embedding_space", lambda: EmbeddingSpace("bge-m3:latest", None, 0))
    monkeypatch.setattr(res, "active_embedding_model", lambda: "bge-m3:latest")
    assert res.resolve_kb_embedding_model("nomic-embed-text:latest") == "nomic-embed-text:latest"
