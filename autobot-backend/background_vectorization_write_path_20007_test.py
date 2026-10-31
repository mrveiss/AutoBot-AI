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


def _vectorizer(monkeypatch, facts: int, backend_up: bool) -> BackgroundVectorizer:
    vectorizer = BackgroundVectorizer()
    monkeypatch.setattr(vectorizer, "_get_vectorization_status", AsyncMock(return_value=[]))
    monkeypatch.setattr(vectorizer, "_filter_pending_facts", lambda batch, _v: (batch, 0, []), raising=False)
    monkeypatch.setattr(vectorizer, "_sync_pending_set", AsyncMock())
    monkeypatch.setattr(
        vectorizer, "_fetch_fact_data", AsyncMock(return_value=[{"content": "c", "metadata": "{}"}] * facts)
    )
    monkeypatch.setattr(vectorizer, "_embedding_backend_answers", AsyncMock(return_value=backend_up))
    return vectorizer


@pytest.mark.asyncio
async def test_a_downed_backend_stops_the_pass_at_the_first_failure(monkeypatch):
    kb = _kb("error")
    stats = await _vectorizer(monkeypatch, 5, False)._process_batch(kb, [f"fact:f{i}" for i in range(5)])
    assert stats["failed"] == 1 and stats["stopped"] is True
    assert kb.vectorize_existing_fact.await_count == 1
    kb.redis.return_value.srem.assert_not_awaited()


@pytest.mark.asyncio
async def test_facts_that_fail_alone_do_not_starve_those_behind_them(monkeypatch):
    """Five permanent failures at the head of the queue must not end the pass."""
    kb = _kb("error")
    outcomes = [{"status": "error", "message": "m"}] * 5 + [{"status": "success", "message": "m"}]
    kb.vectorize_existing_fact = AsyncMock(side_effect=outcomes)
    stats = await _vectorizer(monkeypatch, 6, True)._process_batch(kb, [f"fact:f{i}" for i in range(6)])
    assert stats["failed"] == 5 and stats["success"] == 1 and "stopped" not in stats


@pytest.mark.asyncio
async def test_a_stopped_batch_ends_the_pass_across_batches(monkeypatch):
    vectorizer = _vectorizer(monkeypatch, 1, False)
    vectorizer.batch_size = 1
    process = AsyncMock(
        return_value={"success": 0, "skipped": 0, "failed": 1, "tokens": 0, "processing_time": 0.0, "stopped": True}
    )
    monkeypatch.setattr(vectorizer, "_process_batch", process)
    monkeypatch.setattr(vectorizer, "_scan_pending_set", AsyncMock(return_value=["fact:a", "fact:b", "fact:c"]))
    vectorizer._cycle_count = 1  # not a full-scan cycle
    await vectorizer.vectorize_pending_facts(_kb("error"))
    assert process.await_count == 1
