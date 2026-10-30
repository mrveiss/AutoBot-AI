# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Background vectorization writes through the KB's own path, and a failure stays pending (#20007).

It used to require kb.vector_index, which KB init never builds, so every pass failed every fact.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from background_vectorization import BackgroundVectorizer
from knowledge.facts import FactsMixin


def _kb(status: str):
    kb = MagicMock(spec=["vectorize_existing_fact", "redis"])
    kb.vectorize_existing_fact = AsyncMock(return_value={"status": status, "message": "m"})
    kb.redis.return_value = MagicMock(hset=AsyncMock(), srem=AsyncMock())
    return kb


@pytest.mark.asyncio
async def test_a_fact_is_written_and_marked_complete_with_no_vector_index():
    kb = _kb("success")
    result = await BackgroundVectorizer()._vectorize_single_fact(kb, "fact:f1", {"content": "c", "metadata": "{}"})
    assert result["success"] is True
    kb.vectorize_existing_fact.assert_awaited_once_with("f1")
    kb.redis.return_value.srem.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_failed_write_stays_pending():
    kb = _kb("error")
    result = await BackgroundVectorizer()._vectorize_single_fact(kb, "fact:f1", {"content": "c", "metadata": "{}"})
    assert result["success"] is False
    kb.redis.return_value.srem.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_embedding_that_failed_is_not_reported_as_success():
    kb = MagicMock()
    kb.ensure_initialized = MagicMock()
    kb.vector_store = MagicMock()
    kb._get_fact_for_vectorization = AsyncMock(return_value={"content": "c", "metadata": {}})
    kb._vectorize_fact_in_chromadb = AsyncMock(return_value=False)
    result = await FactsMixin.vectorize_existing_fact(kb, "f1")
    assert result["status"] == "error"
