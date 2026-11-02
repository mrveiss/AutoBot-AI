# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#19726: every stored fact started its own full read of the KB; now writes share one, and no write means no read."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from knowledge.search_components import keyword_search
from knowledge.search_components.keyword_search import KeywordSearcher


def _searcher() -> KeywordSearcher:
    searcher = KeywordSearcher(MagicMock())
    searcher.recompute_corpus_stats = AsyncMock()
    return searcher


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_a_run_of_writes_shares_one_recompute_and_the_last_is_not_lost(monkeypatch) -> None:
    monkeypatch.setattr(keyword_search, "BM25_REFRESH_MIN_INTERVAL_S", 0.05)
    searcher = _searcher()
    for _ in range(200):
        searcher.request_refresh()
    await _settle()
    assert searcher.recompute_corpus_stats.await_count == 1
    for _ in range(200):
        searcher.request_refresh()
    await _settle()
    assert searcher.recompute_corpus_stats.await_count == 1, "the interval holds the next one back"
    await asyncio.wait_for(searcher._refresh_task, 1)
    assert searcher.recompute_corpus_stats.await_count == 2, "writes after a recompute still get one"


@pytest.mark.asyncio
async def test_no_write_means_no_sweep() -> None:
    searcher = _searcher()
    await _settle()
    assert searcher.recompute_corpus_stats.await_count == 0
    assert searcher._refresh_task is None


@pytest.mark.asyncio
async def test_a_process_exiting_doesnt_lose_the_waiting_recompute(monkeypatch) -> None:
    monkeypatch.setattr(keyword_search, "BM25_REFRESH_MIN_INTERVAL_S", 3600.0)
    searcher = _searcher()
    searcher.request_refresh()
    await _settle()
    searcher.request_refresh()
    await searcher.flush_refresh()
    assert searcher.recompute_corpus_stats.await_count == 2


@pytest.mark.asyncio
async def test_keyword_search_stops_at_the_configured_cap(monkeypatch) -> None:
    monkeypatch.setattr(keyword_search, "KEYWORD_SEARCH_MAX_SCAN", 100)
    redis = MagicMock()
    redis.scan = AsyncMock(return_value=(b"7", [f"fact:{n}" for n in range(100)]))
    redis.exists = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    pipeline = MagicMock()
    pipeline.execute = AsyncMock(return_value=[{}] * 100)
    redis.pipeline.return_value = pipeline
    assert await KeywordSearcher(redis).search("word", 5) == []
    assert redis.scan.await_count == 1
