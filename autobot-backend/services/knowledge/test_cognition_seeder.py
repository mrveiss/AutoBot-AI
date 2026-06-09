# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for CognitionSeeder — Issue #4679

Tests cover:
- seed_from_directory: populates ChromaDB collection
- seed_from_manifest: reads YAML, calls seeder for each source
- get_seed_status: returns status for seeded collections
- SEED_PRIORITY_BOOST in AdvancedRAGOptimizer._apply_seed_priority_boost
- Cold-start recovery: priority boost lifts seeded docs above unseeded ones
"""

import textwrap
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from services.knowledge.cognition_seeder import (
    SEED_PRIORITY_BOOST,
    CognitionSeeder,
    _chunk_id,
    _chunk_text,
    _load_manifest,
)

# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_seeder(tmp_chromadb=None) -> CognitionSeeder:
    """Return an already-initialized CognitionSeeder with mocked dependencies."""
    seeder = CognitionSeeder()
    seeder._initialized = True

    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.get_or_create_collection.return_value = mock_collection
    mock_client.get_collection.return_value = mock_collection
    mock_client.list_collections.return_value = []
    seeder._client = mock_client

    mock_embed = MagicMock()
    mock_embed.get_text_embedding.return_value = [0.1] * 384
    seeder._embed_model = mock_embed

    return seeder


# ---------------------------------------------------------------------------
# _load_manifest
# ---------------------------------------------------------------------------


def test_load_manifest_parses_yaml(tmp_path) -> None:
    manifest = tmp_path / "seed.yaml"
    manifest.write_text(
        textwrap.dedent("""\
            collections:
              - name: cognition_store
                sources:
                  - path: docs/developer/
                    priority: high
                    refresh: on_change
                  - path: docs/api/
                    priority: medium
                    refresh: never
            """),
        encoding="utf-8",
    )
    result = _load_manifest(str(manifest))
    assert len(result.collections) == 1
    coll = result.collections[0]
    assert coll.name == "cognition_store"
    assert len(coll.sources) == 2
    assert coll.sources[0].priority == "high"
    assert coll.sources[1].path == "docs/api/"


def test_load_manifest_missing_raises(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        _load_manifest(str(tmp_path / "nonexistent.yaml"))


# ---------------------------------------------------------------------------
# _chunk_text
# ---------------------------------------------------------------------------


def test_chunk_text_splits_at_paragraphs() -> None:
    content = "Para one.\n\nPara two.\n\nPara three."
    chunks = _chunk_text(content, max_chars=15)
    assert len(chunks) > 1
    # Each chunk fits within max_chars (with some tolerance for joining)
    for c in chunks:
        assert len(c) <= 15 + 50  # generous tolerance


def test_chunk_text_single_paragraph() -> None:
    content = "Short content."
    chunks = _chunk_text(content, max_chars=1500)
    assert chunks == ["Short content."]


# ---------------------------------------------------------------------------
# _chunk_id
# ---------------------------------------------------------------------------


def test_chunk_id_deterministic() -> None:
    id1 = _chunk_id("cognition_store", "docs/api/foo.md", 0)
    id2 = _chunk_id("cognition_store", "docs/api/foo.md", 0)
    assert id1 == id2


def test_chunk_id_unique_per_index() -> None:
    id0 = _chunk_id("cognition_store", "docs/api/foo.md", 0)
    id1 = _chunk_id("cognition_store", "docs/api/foo.md", 1)
    assert id0 != id1


# ---------------------------------------------------------------------------
# seed_from_directory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_from_directory_indexes_markdown(tmp_path) -> None:
    # Create a small .md file
    (tmp_path / "guide.md").write_text("# Guide\n\nSome foundational knowledge.", encoding="utf-8")

    seeder = _make_seeder()
    seeder._root_dir = tmp_path

    count = await seeder.seed_from_directory(str(tmp_path), collection="cognition_store")
    assert count >= 1
    seeder._client.get_or_create_collection.assert_called()


@pytest.mark.asyncio
async def test_seed_from_directory_skips_missing() -> None:
    seeder = _make_seeder()
    count = await seeder.seed_from_directory("/nonexistent/path/abc123")
    assert count == 0


@pytest.mark.asyncio
async def test_seed_from_directory_skips_empty_file(tmp_path) -> None:
    (tmp_path / "empty.md").write_text("", encoding="utf-8")
    seeder = _make_seeder()
    seeder._root_dir = tmp_path
    count = await seeder.seed_from_directory(str(tmp_path))
    assert count == 0


# ---------------------------------------------------------------------------
# seed_from_manifest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_from_manifest_processes_sources(tmp_path) -> None:
    # Set up project structure
    docs_dir = tmp_path / "docs" / "developer"
    docs_dir.mkdir(parents=True)
    (docs_dir / "guide.md").write_text("# Dev Guide\n\nImportant docs.", encoding="utf-8")

    manifest = tmp_path / "cognition_seed.yaml"
    manifest.write_text(
        textwrap.dedent("""\
            collections:
              - name: cognition_store
                sources:
                  - path: docs/developer/
                    priority: high
                    refresh: on_change
            """),
        encoding="utf-8",
    )

    seeder = _make_seeder()
    seeder._root_dir = tmp_path

    count = await seeder.seed_from_manifest(str(manifest))
    assert count >= 1


@pytest.mark.asyncio
async def test_seed_from_manifest_missing_manifest() -> None:
    seeder = _make_seeder()
    count = await seeder.seed_from_manifest("/nonexistent/manifest.yaml")
    assert count == 0


# ---------------------------------------------------------------------------
# get_seed_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_seed_status_returns_seeded_collections() -> None:
    seeder = _make_seeder()

    # Mock a collection that has seeded documents
    mock_coll_meta = MagicMock()
    mock_coll_meta.name = "cognition_store"
    seeder._client.list_collections.return_value = [mock_coll_meta]

    now = "2026-04-15T10:00:00+00:00"
    seeder._client.get_collection.return_value.get.return_value = {
        "metadatas": [
            {
                "seeded": "true",
                "seed_priority": "high",
                "relative_path": "docs/developer/CLAUDE.md",
                "seeded_at": now,
            },
            {
                "seeded": "true",
                "seed_priority": "high",
                "relative_path": "docs/developer/CLAUDE.md",
                "seeded_at": now,
            },
        ]
    }

    statuses = await seeder.get_seed_status()
    assert len(statuses) == 1
    s = statuses[0]
    assert s.collection == "cognition_store"
    assert s.document_count == 2
    assert s.seeded_at == now
    assert "docs/developer/CLAUDE.md" in s.sources


@pytest.mark.asyncio
async def test_get_seed_status_empty_when_no_seeded_docs() -> None:
    seeder = _make_seeder()

    mock_coll_meta = MagicMock()
    mock_coll_meta.name = "autobot_docs"
    seeder._client.list_collections.return_value = [mock_coll_meta]
    seeder._client.get_collection.return_value.get.return_value = {"metadatas": []}

    statuses = await seeder.get_seed_status()
    assert statuses == []


# ---------------------------------------------------------------------------
# AdvancedRAGOptimizer seed priority boost
# ---------------------------------------------------------------------------


def _make_search_result(hybrid_score: float, seeded: bool = False, priority: str = "high"):
    """Build a minimal SearchResult-like object for boost tests."""
    from advanced_rag_optimizer import SearchResult

    metadata: Dict[str, Any] = {}
    if seeded:
        metadata["seeded"] = "true"
        metadata["seed_priority"] = priority

    return SearchResult(
        content="test content",
        metadata=metadata,
        semantic_score=hybrid_score,
        keyword_score=0.0,
        hybrid_score=hybrid_score,
        relevance_rank=1,
        source_path="docs/test.md",
    )


def test_seed_priority_boost_high() -> None:
    from advanced_rag_optimizer import AdvancedRAGOptimizer

    optimizer = AdvancedRAGOptimizer.__new__(AdvancedRAGOptimizer)
    result = _make_search_result(0.5, seeded=True, priority="high")
    boosted = optimizer._apply_seed_priority_boost(result)
    expected = min(1.0, 0.5 + SEED_PRIORITY_BOOST["high"])
    assert boosted == pytest.approx(expected, abs=1e-6)


def test_seed_priority_boost_medium() -> None:
    from advanced_rag_optimizer import AdvancedRAGOptimizer

    optimizer = AdvancedRAGOptimizer.__new__(AdvancedRAGOptimizer)
    result = _make_search_result(0.5, seeded=True, priority="medium")
    boosted = optimizer._apply_seed_priority_boost(result)
    expected = min(1.0, 0.5 + SEED_PRIORITY_BOOST["medium"])
    assert boosted == pytest.approx(expected, abs=1e-6)


def test_seed_priority_boost_not_applied_to_non_seeded() -> None:
    from advanced_rag_optimizer import AdvancedRAGOptimizer

    optimizer = AdvancedRAGOptimizer.__new__(AdvancedRAGOptimizer)
    result = _make_search_result(0.5, seeded=False)
    boosted = optimizer._apply_seed_priority_boost(result)
    assert boosted == pytest.approx(0.5, abs=1e-6)


def test_seed_priority_boost_capped_at_one() -> None:
    from advanced_rag_optimizer import AdvancedRAGOptimizer

    optimizer = AdvancedRAGOptimizer.__new__(AdvancedRAGOptimizer)
    result = _make_search_result(0.99, seeded=True, priority="high")
    boosted = optimizer._apply_seed_priority_boost(result)
    assert boosted <= 1.0


def test_cold_start_seeded_beats_unseeded() -> None:
    """Seeded high-priority result with lower raw score beats unseeded with higher raw score."""
    from advanced_rag_optimizer import AdvancedRAGOptimizer

    optimizer = AdvancedRAGOptimizer.__new__(AdvancedRAGOptimizer)

    seeded = _make_search_result(0.4, seeded=True, priority="high")
    unseeded = _make_search_result(0.45, seeded=False)

    boosted_seeded = optimizer._apply_seed_priority_boost(seeded)
    boosted_unseeded = optimizer._apply_seed_priority_boost(unseeded)

    # High-priority seed at 0.4 + 0.15 = 0.55 > unseeded 0.45
    assert boosted_seeded > boosted_unseeded
