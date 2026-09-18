# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""_store_and_vectorize_fact redacts credentials before persist_fact/Redis/ChromaDB
all see the content (#13708 review of #16895).

Every KB write converges here -- the 4 api/knowledge.py add-* routes, file
upload, audio transcription, and every connector's sync path (#16985) --
so this is the one place that closes #13708's "stored redacted, never
passed to the indexer in the clear" AC repo-wide, rather than each entry
point carrying its own copy.
"""

from unittest.mock import AsyncMock, patch

import pytest

from tests.helpers.fake_kb import FactsFakeKB

_SECRET = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"


@pytest.mark.asyncio
async def test_store_and_vectorize_fact_redacts_before_persist_fact():
    kb = FactsFakeKB()
    captured = {}

    async def _persist(fact_id, content, metadata):
        captured["persist_fact"] = content

    with (
        patch("knowledge.fact_store.persist_fact", new=AsyncMock(side_effect=_persist)),
        patch.object(type(kb), "_project_fact_to_redis", new=AsyncMock()),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock()),
    ):
        result = await kb._store_and_vectorize_fact("fact-1", f"your API key is {_SECRET}", {})

    assert result["status"] == "success"
    assert _SECRET not in captured["persist_fact"]
    assert "your API key is" in captured["persist_fact"]


@pytest.mark.asyncio
async def test_store_and_vectorize_fact_redacts_before_the_redis_projection():
    kb = FactsFakeKB()
    captured = {}

    async def _project(fact_id, content, metadata):
        captured["redis"] = content

    with (
        patch("knowledge.fact_store.persist_fact", new=AsyncMock()),
        patch.object(type(kb), "_project_fact_to_redis", new=AsyncMock(side_effect=_project)),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock()),
    ):
        await kb._store_and_vectorize_fact("fact-2", f"password is {_SECRET}", {})

    assert _SECRET not in captured["redis"]


@pytest.mark.asyncio
async def test_store_and_vectorize_fact_redacts_before_chromadb_vectorization():
    kb = FactsFakeKB()
    captured = {}

    async def _vectorize(fact_id, content, metadata):
        captured["chromadb"] = content

    with (
        patch("knowledge.fact_store.persist_fact", new=AsyncMock()),
        patch.object(type(kb), "_project_fact_to_redis", new=AsyncMock()),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock(side_effect=_vectorize)),
    ):
        await kb._store_and_vectorize_fact("fact-3", f"token: {_SECRET}", {})

    assert _SECRET not in captured["chromadb"]


@pytest.mark.asyncio
async def test_store_and_vectorize_fact_a_safe_body_is_unchanged():
    """Negative control: the redaction pass must not mangle ordinary content."""
    kb = FactsFakeKB()
    captured = {}

    async def _persist(fact_id, content, metadata):
        captured["persist_fact"] = content

    with (
        patch("knowledge.fact_store.persist_fact", new=AsyncMock(side_effect=_persist)),
        patch.object(type(kb), "_project_fact_to_redis", new=AsyncMock()),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock()),
    ):
        await kb._store_and_vectorize_fact("fact-4", "Redis listens on port 6379.", {})

    assert captured["persist_fact"] == "Redis listens on port 6379."
