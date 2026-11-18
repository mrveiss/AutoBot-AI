# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The NPU leg's CPU fallback re-enters ``knowledge_base.search`` once, on the CPU leg (#20940).

Sibling of the #15165 test: that closed ``_CPUBackend``; the NPU engine's two
fallbacks (vector store unavailable, search error) called an auto-dispatching
``search()``, which picks the NPU leg again. They now pin ``hardware_backend="cpu"``
so they keep ``KB.search``'s quarantine gate (#19144) and still reach a base case.
Drives the REAL ``SearchMixin.search`` -> REAL ``VectorSearchEngine`` -> REAL
``_NPUBackend`` -> REAL ``NPUSemanticSearch`` with a fake KB whose vector store is
unavailable; the entry counter is the evidence (capped so a regression fails fast).
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest

import knowledge.vector_search_engine as vse
from knowledge.search import SearchMixin
from npu_semantic_search import NPUSemanticSearch

_CAP = 3


class _FakeKB(SearchMixin):
    """Real search() chain; no vector index (NPU falls back); leaf returns one canned hit."""

    vector_store = object()  # present, so search() reaches dispatch; no vector_index, so NPU falls back
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


class _FailingNPU:
    """The NPU engine's ``search`` failing: its REAL error fallback answers, as ``search`` does on an exception."""

    def __init__(self, kb: _FakeKB) -> None:
        self._real = _engine_for(kb)

    async def search(self, query, similarity_top_k, filters, **_kwargs):
        return await self._real._handle_search_error(RuntimeError("npu down"), query, similarity_top_k, filters, 0.0)


@contextmanager
def _wired(kb: _FakeKB, npu: bool):
    """A fresh real engine whose NPU adapter and CPU leg both meet the fake KB."""
    engine = vse.VectorSearchEngine()
    engine._npu._engine = _FailingNPU(kb)
    with (
        patch.object(vse, "_npu_enabled", return_value=npu),
        patch.object(vse, "_gpu_available", return_value=False),
        patch(
            "knowledge.search_components.basic_vector_search.get_vector_search_engine", AsyncMock(return_value=engine)
        ),
        patch("knowledge.get_knowledge_base", AsyncMock(return_value=kb)),
    ):
        yield


@pytest.mark.asyncio
async def test_npu_fallback_enters_search_once_on_the_cpu_leg():
    kb = _FakeKB()
    with _wired(kb, npu=True):
        results, device = await _engine_for(kb)._perform_vector_search("*", 5, None)
    assert device == "cpu_fallback" and [r.content for r in results] == ["hit"]
    assert kb.entry_count == 1 and kb.leaf_calls == 1


@pytest.mark.asyncio
async def test_npu_error_fallback_enters_search_once_on_the_cpu_leg():
    kb = _FakeKB()
    with _wired(kb, npu=True):
        results, metrics = await _engine_for(kb)._handle_search_error(RuntimeError("x"), "*", 5, None, 0.0)
    assert metrics.device_used == "fallback" and len(results) == 1
    assert kb.entry_count == 1 and kb.leaf_calls == 1


@pytest.mark.asyncio
async def test_full_chain_reaches_the_leaf_with_a_bounded_search_count():
    for npu, entries in ((True, 2), (False, 1)):  # NPU: outer search + the fallback's one CPU-leg search
        kb = _FakeKB()
        with _wired(kb, npu):
            results = await kb.search("*", top_k=5, mode="vector")
        assert kb.entry_count == entries, f"npu={npu}: search() entered {kb.entry_count}x (#20940)"
        assert kb.leaf_calls == 1 and [r["content"] for r in results] == ["hit"]
