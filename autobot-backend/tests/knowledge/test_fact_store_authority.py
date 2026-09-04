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

``test_a_fact_survives_its_redis_projection_being_gone`` is the one that would
have caught #12733 before it shipped: it empties Redis and asserts the fact is
still there. ``test_a_redis_only_fact_is_adopted_into_the_durable_store`` covers
the window before that is true of a given fact — the table is created empty, so
until a fact is adopted it is still Redis-only.
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
        patch("knowledge.fact_projection.asyncio.to_thread", side_effect=_passthrough),
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
        patch("knowledge.fact_projection.asyncio.to_thread", side_effect=_passthrough),
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
        patch("knowledge.fact_projection.asyncio.to_thread", side_effect=_passthrough),
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


@pytest.mark.asyncio
async def test_a_redis_only_fact_is_adopted_into_the_durable_store():
    """The migration creates the table empty, so legacy facts must be adopted.

    Without this, every fact that existed before #15663 stays Redis-only and the
    "durable system of record" is a promise about future writes only — the ones
    already at risk stay at risk.
    """
    kb = FactsFakeKB()
    kb._scan_redis_keys_async = AsyncMock(return_value=["fact:legacy-1", "fact:already-2"])
    persisted = []

    async def _load(fact_id):
        return {"content": "c", "metadata": {}} if fact_id == "already-2" else None

    async def _persist(fact_id, content, metadata):
        persisted.append(fact_id)

    with (
        patch("knowledge.fact_store.load_fact", new=AsyncMock(side_effect=_load)),
        patch("knowledge.fact_store.persist_fact", new=AsyncMock(side_effect=_persist)),
        patch.object(
            facts_module.FactsMixin,
            "_read_fact_for_write",
            new=AsyncMock(return_value=({"content": "legacy body"}, {"category": "old"})),
        ),
    ):
        result = await kb.adopt_legacy_facts()

    assert result == {"status": "success", "adopted": 1, "already_durable": 1}
    assert persisted == ["legacy-1"]


@pytest.mark.asyncio
async def test_a_concurrent_delete_is_not_counted_twice():
    """Neither store removed anything, so another caller already did the delete.

    Proceeding would decrement total_facts and total_vectors a second time for
    one fact, which is how a counter drifts away from the data it describes.
    """
    kb = FactsFakeKB()
    kb.redis_client.delete = MagicMock(return_value=0)
    kb._decrement_stat = AsyncMock()

    with (
        patch("knowledge.fact_projection.asyncio.to_thread", side_effect=_passthrough),
        patch("knowledge.fact_store.delete_fact", new=AsyncMock(return_value=False)),
        patch.object(
            facts_module.FactsMixin,
            "_read_fact_for_write",
            new=AsyncMock(return_value=({"content": "gone"}, {})),
        ),
    ):
        result = await kb.delete_fact("fact-1")

    assert result["status"] == "error"
    kb._decrement_stat.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_update_does_not_resurrect_a_concurrently_deleted_fact():
    """No durable row and no Redis key means the delete won; do not rewrite it.

    The mirror case — no row but the key still present — is a fact created
    before #15663, and that one is adopted rather than refused.
    """
    kb = FactsFakeKB()
    kb.redis_client.exists = MagicMock(return_value=0)

    with (
        patch("knowledge.fact_projection.asyncio.to_thread", side_effect=_passthrough),
        patch("knowledge.fact_store.update_fact", new=AsyncMock(return_value=False)),
        patch("knowledge.fact_store.persist_fact", new=AsyncMock()) as persist,
        patch.object(
            facts_module.FactsMixin,
            "_read_fact_for_write",
            new=AsyncMock(return_value=({"content": "gone", "timestamp": ""}, {})),
        ),
    ):
        result = await kb.update_fact("fact-1", content="new body")

    assert result["status"] == "error"
    persist.assert_not_awaited()
