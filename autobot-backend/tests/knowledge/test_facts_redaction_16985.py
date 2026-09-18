# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Both store_fact and update_fact redact credentials before persist/Redis/
ChromaDB all see the content (#13708 review of #16895).

sanitize_fact_content (knowledge/ingest_sanitize.py) is the shared chokepoint
both call -- store_fact for new facts, update_fact for a fact's content being
edited -- so this drives the real public methods end-to-end rather than the
internal _store_and_vectorize_fact helper: a review of the first version of
this fix found update_fact reaches persist/Redis/ChromaDB through a
completely separate path that never touched redaction at all.
"""

from unittest.mock import AsyncMock, patch

import pytest

import knowledge.facts as facts_module
from tests.helpers.fake_kb import FactsFakeKB

_SECRET = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"


def _passthrough(f, *args, **kwargs):
    return f(*args, **kwargs)


# ---------------------------------------------------------------------------
# store_fact -- new facts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_fact_redacts_before_persist_fact():
    kb = FactsFakeKB()
    captured = {}

    async def _persist(fact_id, content, metadata):
        captured["persist_fact"] = content

    with (
        patch("knowledge.fact_store.persist_fact", new=AsyncMock(side_effect=_persist)),
        patch.object(type(kb), "_project_fact_to_redis", new=AsyncMock()),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock()),
        patch.object(type(kb), "_check_for_duplicates", new=AsyncMock(return_value=None)),
    ):
        result = await kb.store_fact(f"your API key is {_SECRET}", {}, fact_id="fact-1")

    assert result["status"] == "success"
    assert _SECRET not in captured["persist_fact"]
    assert "your API key is" in captured["persist_fact"]


@pytest.mark.asyncio
async def test_store_fact_redacts_before_the_redis_projection():
    kb = FactsFakeKB()
    captured = {}

    async def _project(fact_id, content, metadata):
        captured["redis"] = content

    with (
        patch("knowledge.fact_store.persist_fact", new=AsyncMock()),
        patch.object(type(kb), "_project_fact_to_redis", new=AsyncMock(side_effect=_project)),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock()),
        patch.object(type(kb), "_check_for_duplicates", new=AsyncMock(return_value=None)),
    ):
        await kb.store_fact(f"password is {_SECRET}", {}, fact_id="fact-2")

    assert _SECRET not in captured["redis"]


@pytest.mark.asyncio
async def test_store_fact_redacts_before_chromadb_vectorization():
    kb = FactsFakeKB()
    captured = {}

    async def _vectorize(fact_id, content, metadata):
        captured["chromadb"] = content

    with (
        patch("knowledge.fact_store.persist_fact", new=AsyncMock()),
        patch.object(type(kb), "_project_fact_to_redis", new=AsyncMock()),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock(side_effect=_vectorize)),
        patch.object(type(kb), "_check_for_duplicates", new=AsyncMock(return_value=None)),
    ):
        await kb.store_fact(f"token: {_SECRET}", {}, fact_id="fact-3")

    assert _SECRET not in captured["chromadb"]


@pytest.mark.asyncio
async def test_store_fact_a_safe_body_is_unchanged():
    """Negative control: the redaction pass must not mangle ordinary content."""
    kb = FactsFakeKB()
    captured = {}

    async def _persist(fact_id, content, metadata):
        captured["persist_fact"] = content

    with (
        patch("knowledge.fact_store.persist_fact", new=AsyncMock(side_effect=_persist)),
        patch.object(type(kb), "_project_fact_to_redis", new=AsyncMock()),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock()),
        patch.object(type(kb), "_check_for_duplicates", new=AsyncMock(return_value=None)),
    ):
        await kb.store_fact("Redis listens on port 6379.", {}, fact_id="fact-4")

    assert captured["persist_fact"] == "Redis listens on port 6379."


# ---------------------------------------------------------------------------
# update_fact -- editing an existing fact's content (the gap the review found:
# this reaches persist/Redis/ChromaDB through a separate path from store_fact)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_fact_redacts_the_durable_store():
    kb = FactsFakeKB()
    kb.vector_store = None  # isolate to the durable write; no ChromaDB call to mock
    captured = {}

    async def _durable_update(fact_id, content, metadata):
        captured["durable"] = content
        return True

    with (
        patch("knowledge.fact_projection.asyncio.to_thread", side_effect=_passthrough),
        patch.object(
            facts_module.FactsMixin,
            "_read_fact_for_write",
            new=AsyncMock(return_value=({"content": "old body", "timestamp": ""}, {})),
        ),
        patch.object(type(kb), "_durable_update_or_adopt", new=AsyncMock(side_effect=_durable_update)),
    ):
        result = await kb.update_fact("fact-1", content=f"your API key is {_SECRET}")

    assert result["status"] == "success"
    assert _SECRET not in captured["durable"]
    assert "your API key is" in captured["durable"]


@pytest.mark.asyncio
async def test_update_fact_redacts_the_redis_hset():
    kb = FactsFakeKB()
    kb.vector_store = None
    hset_calls = []
    kb.redis_client.hset = lambda key, mapping: hset_calls.append(mapping)

    with (
        patch("knowledge.fact_projection.asyncio.to_thread", side_effect=_passthrough),
        patch.object(
            facts_module.FactsMixin,
            "_read_fact_for_write",
            new=AsyncMock(return_value=({"content": "old body", "timestamp": ""}, {})),
        ),
        patch.object(type(kb), "_durable_update_or_adopt", new=AsyncMock(return_value=True)),
    ):
        await kb.update_fact("fact-2", content=f"password is {_SECRET}")

    assert len(hset_calls) == 1
    assert _SECRET not in hset_calls[0]["content"]


@pytest.mark.asyncio
async def test_update_fact_redacts_the_chromadb_revectorize():
    kb = FactsFakeKB(vector_store=object())  # truthy: update_fact only revectorizes when set
    captured = {}

    async def _revectorize(fact_id, content, current_metadata):
        captured["chromadb"] = content

    with (
        patch("knowledge.fact_projection.asyncio.to_thread", side_effect=_passthrough),
        patch.object(
            facts_module.FactsMixin,
            "_read_fact_for_write",
            new=AsyncMock(return_value=({"content": "old body", "timestamp": ""}, {})),
        ),
        patch.object(type(kb), "_durable_update_or_adopt", new=AsyncMock(return_value=True)),
        patch.object(type(kb), "_revectorize_fact", new=AsyncMock(side_effect=_revectorize)),
    ):
        result = await kb.update_fact("fact-3", content=f"token: {_SECRET}")

    assert result["status"] == "success"
    assert _SECRET not in captured["chromadb"]


@pytest.mark.asyncio
async def test_resubmitting_the_same_secret_is_recognized_as_a_duplicate():
    """#17005: dedup used to be asymmetric -- the write-side hash indexed
    redacted content while the read-side duplicate check hashed raw content,
    so a resubmitted secret never matched its own earlier (redacted) copy.
    Moving redaction ahead of _check_for_duplicates (this fix) makes both
    sides hash the same text. Real store_fact calls, real Redis-hash dedup
    logic (an in-memory fake redis_client, not a mock of _find_existing_fact
    or _project_fact_to_redis themselves) -- only persist_fact (durable row)
    and the ChromaDB layer are mocked, since they're not what dedup reads."""
    kb = FactsFakeKB()
    store = {}
    kb.redis_client.get = lambda key: store.get(key)
    kb.redis_client.set = lambda key, value: store.__setitem__(key, value)
    kb.redis_client.hset = lambda key, mapping: store.__setitem__(key, mapping)

    with (
        patch("knowledge.fact_store.persist_fact", new=AsyncMock()),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock()),
    ):
        first = await kb.store_fact(f"your API key is {_SECRET}", {}, fact_id="fact-a")
        second = await kb.store_fact(f"your API key is {_SECRET}", {}, fact_id="fact-b")

    assert first["status"] == "success"
    assert second["status"] == "duplicate"
    assert second["fact_id"] == "fact-a"


@pytest.mark.asyncio
async def test_update_fact_a_safe_body_is_unchanged():
    """Negative control for the update_fact path."""
    kb = FactsFakeKB()
    kb.vector_store = None
    captured = {}

    async def _durable_update(fact_id, content, metadata):
        captured["durable"] = content
        return True

    with (
        patch("knowledge.fact_projection.asyncio.to_thread", side_effect=_passthrough),
        patch.object(
            facts_module.FactsMixin,
            "_read_fact_for_write",
            new=AsyncMock(return_value=({"content": "old body", "timestamp": ""}, {})),
        ),
        patch.object(type(kb), "_durable_update_or_adopt", new=AsyncMock(side_effect=_durable_update)),
    ):
        await kb.update_fact("fact-4", content="Redis listens on port 6379.")

    assert captured["durable"] == "Redis listens on port 6379."
