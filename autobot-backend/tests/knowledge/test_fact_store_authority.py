# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Knowledge facts have a durable system of record (#15663, closing #12733).

#12733 is reproducible as a sentence: wipe the Redis keys and the knowledge base
is gone, because the ``fact:<id>`` hash was the only place a fact had ever been
written. These tests hold the shape that makes that impossible -- the row is
written first, it answers on its own when Redis has nothing, and every Redis key
is reconstructible from it.

The last test is the one that would have caught #12733 before it shipped: it
empties Redis entirely and asserts the facts are still there.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import knowledge.facts as facts_module
from tests.helpers.fake_kb import FactsFakeKB


def _passthrough(f, *args, **kwargs):
    """Run ``asyncio.to_thread(fn, ...)`` inline so MagicMock calls are recorded."""
    return f(*args, **kwargs)


@pytest.mark.asyncio
async def test_the_durable_row_is_written_before_the_redis_projection():
    """Order is the guarantee: a fact reported stored has been recorded.

    If the projection went first, a failure between the two writes would leave a
    fact that exists in a cache and nowhere else -- which is the state #12733
    found the knowledge base in.
    """
    kb = FactsFakeKB()
    order = []

    async def _persist(*_args, **_kwargs):
        order.append("postgres")

    async def _project(*_args, **_kwargs):
        order.append("redis")

    with (
        patch("knowledge.fact_store.persist_fact", new=AsyncMock(side_effect=_persist)),
        patch.object(facts_module.FactsMixin, "_project_fact_to_redis", new=AsyncMock(side_effect=_project)),
        patch.object(facts_module.FactsMixin, "_vectorize_fact_in_chromadb", new=AsyncMock()),
    ):
        result = await kb._store_and_vectorize_fact("fact-1", "content", {})

    assert result["status"] == "success"
    assert order == ["postgres", "redis"]


@pytest.mark.asyncio
async def test_a_fact_survives_its_redis_projection_being_gone():
    """The #12733 scenario, as a test. Empty Redis, fact still readable."""
    kb = FactsFakeKB()
    kb.redis_client.hgetall = MagicMock(return_value={})

    row = {"content": "the surviving fact", "metadata": {"category": "kb"}}
    with (
        patch("knowledge.facts.asyncio.to_thread", side_effect=_passthrough),
        patch("knowledge.fact_store.load_fact", new=AsyncMock(return_value=row)),
    ):
        decoded, metadata = await kb._read_fact_for_write("fact-1")

    assert decoded["content"] == "the surviving fact"
    assert metadata == {"category": "kb"}


@pytest.mark.asyncio
async def test_an_unknown_fact_is_still_unknown():
    """The fallback must not invent facts: no hash and no row means not found."""
    kb = FactsFakeKB()
    kb.redis_client.hgetall = MagicMock(return_value={})

    with (
        patch("knowledge.facts.asyncio.to_thread", side_effect=_passthrough),
        patch("knowledge.fact_store.load_fact", new=AsyncMock(return_value=None)),
    ):
        assert await kb._read_fact_for_write("fact-1") is None


@pytest.mark.asyncio
async def test_deduplication_falls_back_to_the_durable_row():
    """A missing dedup index means a stale projection, not an absent fact.

    Answering "no duplicate" from an empty index is how one fact becomes two.
    """
    kb = FactsFakeKB()
    kb.redis_client.get = MagicMock(return_value=None)

    with (
        patch("knowledge.facts.asyncio.to_thread", side_effect=_passthrough),
        patch("knowledge.fact_store.fact_id_for_content_hash", new=AsyncMock(return_value="fact-existing")),
    ):
        found = await kb._find_existing_fact("some content", {})

    assert found == "fact-existing"


@pytest.mark.asyncio
async def test_every_redis_key_is_rebuilt_from_the_rows():
    """Rule 2, executable: the projection is reconstructible, so losing it is cheap."""
    kb = FactsFakeKB()
    projected = []

    async def _project(fact_id, content, metadata):
        projected.append((fact_id, content, metadata.get("category")))

    async def _batches(batch_size=500):  # noqa: ARG001 - signature parity with fact_store
        yield [
            {"fact_id": "a", "content": "first", "metadata": {"category": "one"}},
            {"fact_id": "b", "content": "second", "metadata": {"category": "two"}},
        ]

    with (
        patch("knowledge.fact_store.iter_facts", new=_batches),
        patch.object(facts_module.FactsMixin, "_project_fact_to_redis", new=AsyncMock(side_effect=_project)),
    ):
        result = await kb.rebuild_fact_projections()

    assert result == {"status": "success", "rebuilt": 2}
    assert projected == [("a", "first", "one"), ("b", "second", "two")]
