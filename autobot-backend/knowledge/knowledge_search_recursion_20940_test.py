# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The NPU leg's CPU fallback must not re-enter ``knowledge_base.search`` (#20940).

Sibling of the #15165 test: that closed ``_CPUBackend``; the NPU engine's two
fallbacks (vector store unavailable, search error) still called ``search()``.
Drives the REAL ``SearchMixin.search`` -> REAL ``VectorSearchEngine`` -> REAL
``_NPUBackend`` -> REAL ``NPUSemanticSearch`` with a fake KB whose vector store is
unavailable; the entry counter is the evidence (capped so a regression fails fast).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import knowledge.vector_search_engine as vse
from knowledge.search import SearchMixin
from npu_semantic_search import NPUSemanticSearch

_CAP = 3


class _FakeKB(SearchMixin):
    """Real search() chain; vector store unavailable; leaf returns one canned hit."""

    vector_store = None
    vector_index = None

    def __init__(self) -> None:
        super().__init__()
        self.entry_count = 0
        self.leaf_calls = 0

    def ensure_initialized(self) -> None:
        """No-op: irrelevant to this path."""

    async def basic_vector_search(self, query, top_k, filters=None):
        self.leaf_calls += 1
        return [{"content": "hit", "metadata": {"fact_id": "f1"}, "score": 0.9}]

    async def search(self, *args, **kwargs):
        self.entry_count += 1
        if self.entry_count > _CAP:
            return []
        return await super().search(*args, **kwargs)


def _engine_for(kb: _FakeKB) -> NPUSemanticSearch:
    engine = NPUSemanticSearch.__new__(NPUSemanticSearch)
    engine.knowledge_base = kb
    return engine


async def _drive(kb: _FakeKB, npu: bool):
    """One real ``kb.search`` through a fresh real engine; the NPU adapter is wired to the fake KB."""
    engine = vse.VectorSearchEngine()
    engine._npu._engine = _engine_for(kb)
    with (
        patch.object(vse, "_npu_enabled", return_value=npu),
        patch.object(vse, "_gpu_available", return_value=False),
        patch(
            "knowledge.search_components.basic_vector_search.get_vector_search_engine", AsyncMock(return_value=engine)
        ),
        patch("knowledge.get_knowledge_base", AsyncMock(return_value=kb)),
    ):
        return await kb.search("*", top_k=5, mode="vector")


@pytest.mark.asyncio
async def test_npu_fallback_never_reenters_search():
    kb = _FakeKB()
    engine = _engine_for(kb)
    results, device = await engine._perform_vector_search("*", 5, None)
    assert device == "cpu_fallback" and [r.content for r in results] == ["hit"]
    assert kb.entry_count == 0 and kb.leaf_calls == 1


@pytest.mark.asyncio
async def test_npu_error_fallback_never_reenters_search():
    kb = _FakeKB()
    results, metrics = await _engine_for(kb)._handle_search_error(RuntimeError("x"), "*", 5, None, 0.0)
    assert metrics.device_used == "fallback" and len(results) == 1
    assert kb.entry_count == 0 and kb.leaf_calls == 1


@pytest.mark.asyncio
async def test_cpu_path_still_works_and_enters_search_once():
    for npu in (True, False):
        kb = _FakeKB()
        await _drive(kb, npu)
        assert kb.entry_count == 1, f"npu={npu}: search() entered {kb.entry_count}x (#20940)"
