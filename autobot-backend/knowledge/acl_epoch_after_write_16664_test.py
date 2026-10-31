# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ACL epoch is bumped AFTER the ownership writes that revoke access (#16664).

A bump that lands before the write leaves a window in which a search reads the new epoch
with the old metadata and caches it; ownership reassignment did not bump at all.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import memory.ownership_reassign as mr
from auth_middleware import get_current_user
from knowledge.acl_epoch import ACL_EPOCH_DATABASE, ACL_EPOCH_KEY, AclEpochBumpError, bump_acl_epoch_async
from knowledge.ownership import KnowledgeOwnership


@pytest.mark.asyncio
async def test_the_async_bump_sets_a_fresh_token_and_fails_loudly():
    client = MagicMock(set=AsyncMock())
    token = await bump_acl_epoch_async(client)
    assert isinstance(token, str) and token != await bump_acl_epoch_async(client)
    client.set.assert_any_await(ACL_EPOCH_KEY, token)

    with pytest.raises(AclEpochBumpError):
        await bump_acl_epoch_async(MagicMock(set=AsyncMock(side_effect=ConnectionError("down"))))
    with pytest.raises(AclEpochBumpError):
        await bump_acl_epoch_async(None)


def _kb_with_one_owned_record(events: list) -> AsyncMock:
    async def _get(where, include):
        field = next(iter(where))
        return {"ids": ["f1"], "metadatas": [{field: "user-A"}]} if field == "owner_id" else {"ids": []}

    collection = MagicMock(get=AsyncMock(side_effect=_get))
    collection.update = AsyncMock(side_effect=lambda **_kw: events.append("write"))
    return AsyncMock(_async_chroma_collection=collection)


def _redis(events: list, incr_error: Exception | None = None) -> AsyncMock:
    async def _set(key, _value):
        if incr_error is not None:
            raise incr_error
        events.append(("bump", key))
        return True

    return AsyncMock(set=AsyncMock(side_effect=_set))


@pytest.mark.asyncio
async def test_a_kb_reassignment_bumps_the_epoch_after_rewriting_the_records():
    events: list = []
    redis = _redis(events)
    getter = AsyncMock(return_value=redis)
    with patch.object(mr, "get_knowledge_base_fn", AsyncMock(return_value=_kb_with_one_owned_record(events))):
        with patch.object(mr, "get_async_redis_client", getter):
            assert await mr._reassign_kb_facts("user-A", "user-B") == 1

    assert events == ["write", ("bump", ACL_EPOCH_KEY)]
    getter.assert_any_await(database=ACL_EPOCH_DATABASE)


@pytest.mark.asyncio
async def test_a_reassignment_that_rewrote_nothing_does_not_bump():
    events: list = []
    empty = AsyncMock(_async_chroma_collection=MagicMock(get=AsyncMock(return_value={"ids": []})))
    with patch.object(mr, "get_knowledge_base_fn", AsyncMock(return_value=empty)):
        with patch.object(mr, "get_async_redis_client", AsyncMock(return_value=_redis(events))):
            assert await mr._reassign_kb_facts("user-A", "user-B") == 0
    assert events == []


@pytest.mark.asyncio
async def test_a_failed_bump_makes_the_whole_reassignment_fail():
    """The other stores record 0 on error; a failed bump must instead abort (hard delete is fail-closed)."""
    events: list = []
    redis = _redis(events, incr_error=ConnectionError("redis down"))
    with patch.object(mr, "_bootstrap", lambda: None):
        with patch.object(mr, "get_knowledge_base_fn", AsyncMock(return_value=_kb_with_one_owned_record(events))):
            with patch.object(mr, "get_async_redis_client", AsyncMock(return_value=redis)):
                with patch.multiple(
                    mr,
                    _reassign_verbatim=AsyncMock(return_value=0),
                    _reassign_trajectory=AsyncMock(return_value=0),
                    _reassign_working_memory=AsyncMock(return_value=0),
                    _reassign_graph_entities=AsyncMock(return_value=0),
                ):
                    with pytest.raises(AclEpochBumpError):
                        await mr.reassign_user_memory("user-A", "user-B")
    assert events == ["write"]


def test_unsharing_bumps_the_epoch_again_after_the_metadata_write():
    from api import knowledge_collaboration as collab

    events: list = []
    redis = MagicMock()
    redis.set.side_effect = lambda _key, _value: events.append("bump")
    kb = MagicMock(ownership_manager=KnowledgeOwnership(redis_client=redis))
    kb.get_fact = MagicMock(
        return_value={"metadata": {"owner_id": "u1", "visibility": "shared", "shared_with": ["u2"]}}
    )
    kb.update_fact = AsyncMock(side_effect=lambda **_kw: events.append("write") or {"status": "success"})

    app = FastAPI()
    app.include_router(collab.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "u1", "role": "user"}
    with patch.object(collab, "get_or_create_knowledge_base", AsyncMock(return_value=kb)):
        response = TestClient(app).delete("/api/knowledge/collaboration/facts/f1/share/u2?entity_type=user")

    assert response.status_code == 200, response.text
    assert events == ["bump", "write", "bump"]
