#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for RAGService._get_kb_synthesis_context() multi-collection path (#4659)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# =============================================================================
# Helpers
# =============================================================================


def _make_service():
    """Build a RAGService stub — no Redis or ChromaDB connections."""
    from services.rag_config import RAGConfig
    from services.rag_service import RAGService

    svc = RAGService.__new__(RAGService)
    svc._initialized = True
    svc._cache = {}
    svc._cache_lock = MagicMock()
    svc.config = RAGConfig()
    svc._mesh_retriever = None
    svc.optimizer = MagicMock()
    return svc


def _chroma_results(docs):
    """Build a ChromaDB-style results dict with the given document strings."""
    if not docs:
        return {"ids": [[]], "documents": [[]]}
    return {"ids": [list(range(len(docs)))], "documents": [list(docs)]}


def _mock_collection(docs):
    """Return an AsyncMock collection whose query() returns *docs*."""
    col = AsyncMock()
    col.query = AsyncMock(return_value=_chroma_results(docs))
    return col


def _mock_client(*collection_docs_pairs):
    """Return an AsyncMock ChromaDB client.

    *collection_docs_pairs* is a sequence of (collection_name, docs_list) tuples.
    ``get_or_create_collection`` uses the order of calls to return mocks.
    """
    client = AsyncMock()
    side_effects = [_mock_collection(docs) for _, docs in collection_docs_pairs]
    client.get_or_create_collection = AsyncMock(side_effect=side_effects)
    return client


# =============================================================================
# Tests
# =============================================================================


class TestGetKbSynthesisContext:
    @pytest.mark.asyncio
    async def test_returns_empty_string_when_chromadb_unavailable(self) -> None:
        """ChromaDB client raises → returns empty string without propagating."""
        svc = _make_service()

        with patch(
            "utils.chromadb_client.get_async_chromadb_client",
            new_callable=AsyncMock,
            side_effect=ConnectionError("chroma down"),
        ):
            result = await svc._get_kb_synthesis_context("any query")

        assert result == ""

    @pytest.mark.asyncio
    async def test_single_collection_query_returns_results(self) -> None:
        """Default kb_synthesis collection with 2 docs → prefixed joined string."""
        svc = _make_service()
        docs = ["Summary A", "Summary B"]
        client = _mock_client(("kb_synthesis", docs))

        with (
            patch(
                "utils.chromadb_client.get_async_chromadb_client",
                new_callable=AsyncMock,
                return_value=client,
            ),
            patch(
                "services.knowledge.synthesis_schema_loader.load_synthesis_schema",
                side_effect=FileNotFoundError("no schema"),
            ),
        ):
            result = await svc._get_kb_synthesis_context("test query")

        assert result.startswith("KB synthesis summaries:")
        assert "Summary A" in result
        assert "Summary B" in result

    @pytest.mark.asyncio
    async def test_multi_collection_from_schema(self) -> None:
        """Schema with 2 synthesis_targets → both collections queried, results merged."""
        from services.knowledge.synthesis_schema_loader import (
            CollectionConfig,
            SynthesisSchema,
        )

        svc = _make_service()

        schema = SynthesisSchema(
            collections=[
                CollectionConfig(
                    name="col1",
                    paths=["docs/"],
                    synthesis_target="kb_synthesis_extra",
                    prompt_template="tpl",
                ),
                CollectionConfig(
                    name="col2",
                    paths=["notes/"],
                    synthesis_target="kb_synthesis_notes",
                    prompt_template="tpl",
                ),
            ]
        )

        client = _mock_client(
            ("kb_synthesis", ["Default doc"]),
            ("kb_synthesis_extra", ["Extra doc"]),
            ("kb_synthesis_notes", ["Notes doc"]),
        )

        with (
            patch(
                "utils.chromadb_client.get_async_chromadb_client",
                new_callable=AsyncMock,
                return_value=client,
            ),
            patch(
                "services.knowledge.synthesis_schema_loader.load_synthesis_schema",
                return_value=schema,
            ),
        ):
            result = await svc._get_kb_synthesis_context("multi query")

        assert "Default doc" in result
        assert "Extra doc" in result
        assert "Notes doc" in result
        assert client.get_or_create_collection.call_count == 3

    @pytest.mark.asyncio
    async def test_per_collection_failure_swallowed(self) -> None:
        """First collection raises, second succeeds → partial result returned."""
        svc = _make_service()

        failing_col = AsyncMock()
        failing_col.query = AsyncMock(side_effect=RuntimeError("collection gone"))

        succeeding_col = _mock_collection(["Surviving doc"])

        client = AsyncMock()
        client.get_or_create_collection = AsyncMock(side_effect=[failing_col, succeeding_col])

        from services.knowledge.synthesis_schema_loader import (
            CollectionConfig,
            SynthesisSchema,
        )

        schema = SynthesisSchema(
            collections=[
                CollectionConfig(
                    name="col_ok",
                    paths=["docs/"],
                    synthesis_target="kb_synthesis_ok",
                    prompt_template="tpl",
                ),
            ]
        )

        with (
            patch(
                "utils.chromadb_client.get_async_chromadb_client",
                new_callable=AsyncMock,
                return_value=client,
            ),
            patch(
                "services.knowledge.synthesis_schema_loader.load_synthesis_schema",
                return_value=schema,
            ),
        ):
            result = await svc._get_kb_synthesis_context("query")

        # First collection failed but result from second collection must be present
        assert "Surviving doc" in result
        assert result != ""

    @pytest.mark.asyncio
    async def test_empty_results_returns_empty_string(self) -> None:
        """All collections return empty results → returns empty string."""
        svc = _make_service()

        # collection.query returns empty ids/documents
        empty_col = AsyncMock()
        empty_col.query = AsyncMock(return_value={"ids": [[]], "documents": [[]]})

        client = AsyncMock()
        client.get_or_create_collection = AsyncMock(return_value=empty_col)

        with (
            patch(
                "utils.chromadb_client.get_async_chromadb_client",
                new_callable=AsyncMock,
                return_value=client,
            ),
            patch(
                "services.knowledge.synthesis_schema_loader.load_synthesis_schema",
                side_effect=FileNotFoundError("no schema"),
            ),
        ):
            result = await svc._get_kb_synthesis_context("nothing here")

        assert result == ""
