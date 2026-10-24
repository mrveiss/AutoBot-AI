# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The KB keeps the stored embedding model and says so when it differs (#19377)."""

from __future__ import annotations

import knowledge.embedding_model_resolution as res


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
