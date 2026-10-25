# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every KB read withholds research-quarantined facts unless it opts out, audited (#19163).

Each ``KB.search`` mode is fed a store that ignores any ``where`` and returns a quarantined fact
beside a normal one: the result-level check alone must hold. The basic mode also proves the
store-side ``where`` reaches the engine. ``get_all_facts`` and the returned-copy guarantee follow.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.ssot_config import config
from knowledge.facts import FactsMixin
from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER, with_quarantine, without_quarantine
from knowledge.search import SearchMixin
from knowledge.vector_search_engine import VectorSearchResult

_ENGINE = "knowledge.search_components.basic_vector_search.get_vector_search_engine"
_SEARCH_AUDIT = "knowledge.quarantine.audit_quarantine_read"
_FACTS_AUDIT = "knowledge.quarantine.audit_quarantine_read"
_RESEARCH = config.research_quarantine_collection

_METADATA = {
    "good": {"fact_id": "good"},
    "held": {"fact_id": "held", "collection": _RESEARCH},
}


def _hits():
    return [{"content": k, "score": 0.9, "metadata": dict(m), "node_id": k} for k, m in _METADATA.items()]


class _Store(SearchMixin):
    """A SearchMixin whose every retrieval leg returns both facts, ignoring any filter."""

    def __init__(self) -> None:
        super().__init__()
        self.vector_store = MagicMock()

    def ensure_initialized(self) -> None:
        """No-op: the real impl lives in KnowledgeBaseCore."""

    async def record_fact_access(self, fact_ids) -> None:
        """No-op: usage tracking is not under test."""

    async def _keyword_search(self, query, limit, category=None):
        return _hits()

    async def _hybrid_search(self, query, limit, category=None, board_filter=None):
        return _hits()


def _engine() -> MagicMock:
    engine = MagicMock()
    engine.search = AsyncMock(
        return_value=[VectorSearchResult(text=k, score=0.9, metadata=dict(m), source=k) for k, m in _METADATA.items()]
    )
    return engine


def _ids(results) -> list:
    return [r["metadata"]["fact_id"] for r in results]


@pytest.mark.asyncio
async def test_basic_mode_excludes_quarantined_and_sends_the_where_to_the_store():
    engine = _engine()
    with patch(_ENGINE, AsyncMock(return_value=engine)):
        results = await _Store().search("autobot", top_k=10, filters={"category": "docs"})

    assert _ids(results) == ["good"]
    sent = engine.search.call_args.kwargs["filters"]
    assert {"collection": {"$ne": _RESEARCH}} in sent["$and"] and {"category": "docs"} in sent["$and"]


@pytest.mark.asyncio
async def test_enhanced_mode_excludes_quarantined():
    with patch(_ENGINE, AsyncMock(return_value=_engine())):
        response = await _Store().search("autobot", limit=10, mode="keyword")

    assert _ids(response["results"]) == ["good"]
    assert response["total_count"] == 1


@pytest.mark.asyncio
async def test_advanced_mode_excludes_quarantined():
    with patch(_ENGINE, AsyncMock(return_value=_engine())):
        response = await _Store().search("autobot", limit=10, mode="keyword", session_id="s", track_analytics=False)

    assert _ids(response["results"]) == ["good"]
    assert response["total_count"] == 1


@pytest.mark.asyncio
async def test_include_unservable_still_withholds_quarantined_but_keeps_the_collection_where():
    engine = _engine()
    with patch(_ENGINE, AsyncMock(return_value=engine)):
        results = await _Store().search("autobot", top_k=10, include_unservable=True)

    assert _ids(results) == ["good"]
    assert engine.search.call_args.kwargs["filters"] == {"collection": {"$ne": _RESEARCH}}


@pytest.mark.asyncio
async def test_opt_out_returns_quarantined_in_every_mode_and_audits_each_use():
    store = _Store()
    with patch(_ENGINE, AsyncMock(return_value=_engine())), patch(_SEARCH_AUDIT, AsyncMock(return_value=True)) as audit:
        basic = await store.search("autobot", top_k=10, include_quarantined=True, audit_actor="admin")
        enhanced = await store.search(
            "autobot", limit=10, mode="keyword", include_quarantined=True, audit_actor="admin"
        )

    assert _ids(basic) == ["good", "held"]
    assert _ids(enhanced["results"]) == ["good", "held"]
    assert audit.await_count == 2
    assert audit.await_args.args == ("admin", "kb.search", ["held"])


@pytest.mark.asyncio
async def test_opt_out_without_an_actor_is_refused_and_reads_nothing():
    engine = _engine()
    with patch(_ENGINE, AsyncMock(return_value=engine)), pytest.raises(ValueError):
        await _Store().search("autobot", top_k=10, include_quarantined=True)
    engine.search.assert_not_awaited()


def test_with_quarantine_returns_a_copy_the_constant_survives():
    snapshot = json.dumps(RESEARCH_QUARANTINE_FILTER, sort_keys=True)
    mutated = with_quarantine()
    without_quarantine()["collection"]["$ne"] = "tampered"
    mutated["$and"][0]["collection"]["$ne"] = "tampered"
    mutated["$and"].append({"x": 1})

    assert json.dumps(RESEARCH_QUARANTINE_FILTER, sort_keys=True) == snapshot
    assert with_quarantine() == RESEARCH_QUARANTINE_FILTER


class _Facts(FactsMixin):
    """A FactsMixin over a stubbed Redis: two facts, one quarantined."""

    def __init__(self) -> None:
        self._rows = {
            "fact:good": {b"content": b"ok", b"metadata": json.dumps({"x": 1}).encode()},
            "fact:held": {b"content": b"held", b"metadata": json.dumps({"collection": _RESEARCH}).encode()},
        }

    def ensure_initialized(self) -> None:
        """No-op."""

    async def _scan_redis_keys_async(self, pattern):
        return list(self._rows)

    def redis(self):
        pipe = MagicMock()
        pipe.execute = AsyncMock(return_value=list(self._rows.values()))
        client = MagicMock()
        client.pipeline.return_value = pipe
        return client


@pytest.mark.asyncio
async def test_get_all_facts_excludes_quarantined_by_default():
    facts = await _Facts().get_all_facts()
    assert [f["fact_id"] for f in facts] == ["good"]


@pytest.mark.asyncio
async def test_get_all_facts_opt_out_returns_them_and_audits_who_count_ids():
    with patch(_FACTS_AUDIT, AsyncMock(return_value=True)) as audit:
        facts = await _Facts().get_all_facts(include_quarantined=True, audit_actor="admin")

    assert [f["fact_id"] for f in facts] == ["good", "held"]
    audit.assert_awaited_once_with("admin", "kb.get_all_facts", ["held"])


@pytest.mark.asyncio
async def test_get_all_facts_opt_out_without_actor_is_refused():
    with pytest.raises(ValueError):
        await _Facts().get_all_facts(include_quarantined=True)
