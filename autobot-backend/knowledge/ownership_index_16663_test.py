# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A fact's ownership indexes follow its metadata, and only admins choose ownership (#16663).

The move tests drive the real ``KnowledgeOwnership`` against an in-memory set store, so
they check which index sets the fact ends up in rather than which calls were made.
"""

from __future__ import annotations

import json
from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.facts import FactsMixin
from knowledge.ownership import KnowledgeOwnership, VisibilityLevel
from knowledge.ownership_index import (
    drop_ownership_unless_admin,
    index_ownership,
    ownership_changed,
    reindex_ownership,
)

_SYSTEM_INDEX = "kb:system:facts"


class _SetStore:
    """The two Redis set commands KnowledgeOwnership's index writes use."""

    def __init__(self):
        self.sets: dict[str, set] = defaultdict(set)

    def sadd(self, key, *members):
        self.sets[key].update(members)

    def srem(self, key, *members):
        self.sets[key].difference_update(members)


def _owned(**extra):
    return {"owner_id": "u1", "source_type": "manual", **extra}


def test_only_a_changed_ownership_value_counts_as_an_ownership_change():
    stored = _owned(visibility="system", shared_with=["u2"])
    assert not ownership_changed(stored, {**stored, "title": "renamed", "preserve": True})
    assert not ownership_changed(stored, {**stored, "visibility": VisibilityLevel.SYSTEM})  # str enum == value
    assert ownership_changed(stored, {**stored, "visibility": "private"})
    assert ownership_changed(stored, {**stored, "owner_id": "u3"})
    assert ownership_changed(stored, {**stored, "shared_with": []})


def test_a_non_admin_cannot_choose_ownership_on_ingestion():
    sent = {"title": "t", "visibility": "system", "access_level": "general", "owner_id": "u2", "shared_with": ["x"]}
    assert drop_ownership_unless_admin(sent, "user") == {"title": "t"}
    assert drop_ownership_unless_admin(sent, None) == {"title": "t"}
    assert drop_ownership_unless_admin(None, "user") == {}


def test_an_admin_keeps_the_ownership_it_sent():
    sent = {"title": "t", "visibility": "system", "access_level": "general"}
    assert drop_ownership_unless_admin(sent, "admin") == sent


@pytest.mark.asyncio
async def test_indexing_forwards_org_group_and_access_level():
    manager = AsyncMock()
    metadata = _owned(visibility="group", organization_id="o1", group_ids=["g1"], access_level="general")
    assert await index_ownership(manager, "f1", metadata)
    kwargs = manager.set_owner.await_args.kwargs
    assert (kwargs["organization_id"], kwargs["group_ids"], kwargs["access_level"]) == ("o1", ["g1"], "general")


@pytest.mark.asyncio
async def test_a_fact_without_an_owner_is_not_indexed():
    manager = AsyncMock()
    assert not await index_ownership(manager, "f1", {"visibility": "system"})
    manager.set_owner.assert_not_awaited()


@pytest.mark.asyncio
async def test_demoting_a_system_fact_takes_it_out_of_the_system_index():
    store = _SetStore()
    manager = KnowledgeOwnership(store)
    old = _owned(visibility=VisibilityLevel.SYSTEM)
    await index_ownership(manager, "f1", old)
    assert "f1" in store.sets[_SYSTEM_INDEX]

    await reindex_ownership(manager, "f1", old, _owned(visibility=VisibilityLevel.PRIVATE))

    assert "f1" not in store.sets[_SYSTEM_INDEX]
    assert "f1" in store.sets["user:kb:facts:u1"]


@pytest.mark.asyncio
async def test_a_stale_system_entry_from_an_add_only_write_is_dropped():
    """Before #16663 a demotion rewrote the metadata and left the index entry behind."""
    store = _SetStore()
    store.sets[_SYSTEM_INDEX].add("f1")
    private = _owned(visibility=VisibilityLevel.PRIVATE)

    await reindex_ownership(KnowledgeOwnership(store), "f1", private, private)

    assert "f1" not in store.sets[_SYSTEM_INDEX]


@pytest.mark.asyncio
async def test_moving_groups_leaves_the_old_group_index():
    store = _SetStore()
    manager = KnowledgeOwnership(store)
    old = _owned(visibility=VisibilityLevel.GROUP, group_ids=["g1"])
    await index_ownership(manager, "f1", old)

    await reindex_ownership(manager, "f1", old, _owned(visibility=VisibilityLevel.GROUP, group_ids=["g2"]))

    assert "f1" not in store.sets["group:kb:facts:g1"]
    assert "f1" in store.sets["group:kb:facts:g2"]


@pytest.fixture
def durable_row():
    """Stand in for the durable row update_fact writes first (#15663); no database here."""
    with patch("knowledge.fact_store.update_fact", new=AsyncMock(return_value=True)):
        yield


class _KB(FactsMixin):
    """A FactsMixin host holding one stored fact and an ownership manager."""

    def __init__(self, stored_metadata: dict, ownership_manager):
        self.ensure_initialized = MagicMock()
        self.redis_client = MagicMock()
        self.redis_client.exists.return_value = True
        self.redis_client.hgetall.return_value = {
            b"content": b"stored content",
            b"metadata": json.dumps(stored_metadata).encode("utf-8"),
            b"timestamp": b"2026-01-01T00:00:00+00:00",
        }
        self.vector_store = None
        self.ownership_manager = ownership_manager


@pytest.mark.asyncio
async def test_update_fact_takes_a_demoted_fact_out_of_the_system_index(durable_row):
    store = _SetStore()
    manager = KnowledgeOwnership(store)
    stored = _owned(visibility="system")
    await index_ownership(manager, "f1", stored)

    result = await _KB(stored, manager).update_fact("f1", metadata={"visibility": "private"})

    assert result["status"] == "success"
    assert "f1" not in store.sets[_SYSTEM_INDEX]
    assert "f1" in store.sets["user:kb:facts:u1"]


@pytest.mark.asyncio
async def test_update_fact_leaves_the_indexes_alone_when_ownership_is_untouched(durable_row):
    manager = AsyncMock()

    await _KB(_owned(visibility="system"), manager).update_fact("f1", metadata={"title": "renamed"})

    manager.cleanup_ownership_indexes.assert_not_awaited()
    manager.set_owner.assert_not_awaited()


@pytest.mark.asyncio
async def test_writing_back_the_whole_metadata_with_a_flag_does_not_reindex(durable_row):
    """chat-knowledge preserve writes the full fetched dict back; that is not an ownership change."""
    manager = AsyncMock()
    stored = _owned(visibility="system")

    await _KB(stored, manager).update_fact("f1", metadata={**stored, "preserve": True})

    manager.cleanup_ownership_indexes.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_reindex_that_fails_midway_fails_closed_and_a_retry_converges(durable_row):
    store = _SetStore()
    manager = KnowledgeOwnership(store)
    stored = _owned(visibility="system")
    await index_ownership(manager, "f1", stored)
    kb = _KB(stored, manager)

    with patch.object(manager, "set_owner", AsyncMock(side_effect=RuntimeError("redis blip"))):
        failed = await kb.update_fact("f1", metadata={"visibility": "private"})

    assert failed["status"] == "error"
    assert "f1" not in store.sets[_SYSTEM_INDEX]  # fewer indexes, never a stale grant

    retried = await kb.update_fact("f1", metadata={"visibility": "private"})

    assert retried["status"] == "success"
    assert "f1" in store.sets["user:kb:facts:u1"] and "f1" not in store.sets[_SYSTEM_INDEX]


@pytest.mark.asyncio
async def test_ingestion_files_the_fact_under_its_organization_and_group():
    store = _SetStore()
    metadata = _owned(visibility="group", organization_id="o1", group_ids=["g1"])

    await _KB({}, KnowledgeOwnership(store))._project_fact_to_redis("f1", "content", metadata)

    assert "f1" in store.sets["org:kb:facts:o1"]
    assert "f1" in store.sets["group:kb:facts:g1"]
