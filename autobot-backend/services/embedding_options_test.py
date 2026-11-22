# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The embedding-model options offer only embedding models and mark the active one (#19378)."""

from __future__ import annotations

from pathlib import Path

import pytest

from services import embedding_options
from services.embedding_options import build_embedding_options

_BACKEND = Path(__file__).resolve().parents[1]


def _listing(*names: str, errored: tuple[str, ...] = ()) -> dict:
    return {
        "models": [{"name": n, "provider": "ollama", "available": True} for n in names],
        "providers_errored": list(errored),
    }


def test_a_chat_model_never_appears() -> None:
    """AC1: #18834's phi3:mini, and the other chat models a provider lists, are not choices."""
    listing = _listing("phi3:mini", "llama3.2:3b", "mistral:7b", "nomic-embed-text:latest", "bge-reranker-base")
    names = [m["name"] for m in build_embedding_options(listing, "nomic-embed-text:latest")["models"]]
    assert names == ["nomic-embed-text:latest"]


def test_the_active_model_is_marked_across_the_implied_tag() -> None:
    """AC2: the override may be stored untagged while Ollama lists ``:latest``."""
    data = build_embedding_options(_listing("nomic-embed-text:latest", "mxbai-embed-large:latest"), "nomic-embed-text")
    assert [(m["name"], m["active"]) for m in data["models"]] == [
        ("nomic-embed-text:latest", True),
        ("mxbai-embed-large:latest", False),
    ]
    assert data["active"] == "nomic-embed-text"


def test_a_different_tag_is_a_different_model() -> None:
    data = build_embedding_options(_listing("nomic-embed-text:v1.5"), "nomic-embed-text:latest")
    assert [m["active"] for m in data["models"]] == [True, False]  # the active one is added, unlisted


def test_an_active_model_no_provider_reports_is_still_shown_as_unavailable() -> None:
    data = build_embedding_options(_listing("mxbai-embed-large:latest", errored=("ollama",)), "nomic-embed-text:latest")
    assert data["models"][0] == {
        "name": "nomic-embed-text:latest",
        "provider": None,
        "available": False,
        "active": True,
        "dimension": None,
    }
    assert data["total_count"] == 2 and data["providers_errored"] == ["ollama"]


def test_a_namespaced_id_is_offered() -> None:
    data = build_embedding_options(_listing("BAAI/bge-small-en-v1.5"), "nomic-embed-text:latest")
    assert "BAAI/bge-small-en-v1.5" in [m["name"] for m in data["models"]]


@pytest.mark.asyncio
async def test_the_service_reads_the_providers_and_the_resolver(monkeypatch) -> None:
    async def listing():
        return _listing("phi3:mini", "all-minilm:l6-v2")

    monkeypatch.setattr(embedding_options, "get_available_models", listing)
    monkeypatch.setattr(embedding_options, "active_embedding_model", lambda: "all-minilm:l6-v2")
    data = await embedding_options.embedding_model_options()
    assert [(m["name"], m["active"]) for m in data["models"]] == [("all-minilm:l6-v2", True)]


def test_the_older_listings_are_consolidated() -> None:
    """AC3: ``/api/llm/embedding/models`` redirects; ``/api/embeddings/models`` serves the options."""
    llm = (_BACKEND / "api" / "llm.py").read_text(encoding="utf-8")
    assert 'RedirectResponse("/api/embeddings/models", status_code=308)' in llm
    assert "EMBEDDING_MODEL_PATTERNS" not in llm
    embeddings = (_BACKEND / "api" / "embeddings.py").read_text(encoding="utf-8")
    assert "EmbeddingModelsData(**await embedding_model_options())" in embeddings
