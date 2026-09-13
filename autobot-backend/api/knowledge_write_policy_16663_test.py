# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Only admins make a fact platform-wide, and visibility writes go through update_fact (#16663).

``update_fact`` is the one write that reaches the durable row, the Redis projection,
ChromaDB and the ownership indexes together; a route that wrote the Redis hash
directly left the other three on the old visibility.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _collab_kb(stored_metadata: dict, write_status: str = "success"):
    kb = MagicMock()
    kb.ownership_manager = AsyncMock()
    redis = MagicMock()
    redis.hget = AsyncMock(return_value=json.dumps(stored_metadata))
    kb.redis.return_value = redis
    kb.update_fact = AsyncMock(return_value={"status": write_status})
    return kb


async def _set_permissions(kb, role: str, visibility: str):
    from api import knowledge_collaboration as collab

    with patch.object(collab, "get_or_create_knowledge_base", AsyncMock(return_value=kb)):
        return await collab.update_knowledge_permissions(
            fact_id="f1",
            permissions_request=SimpleNamespace(visibility=visibility, organization_id=None, group_ids=[]),
            request=MagicMock(),
            current_user={"user_id": "u1", "role": role},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("visibility", ["system", "public"])
async def test_a_non_admin_owner_cannot_make_a_fact_platform_wide(visibility):
    kb = _collab_kb({"owner_id": "u1", "visibility": "private"})

    with pytest.raises(HTTPException) as err:
        await _set_permissions(kb, "user", visibility)

    assert err.value.status_code == 403
    kb.update_fact.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("visibility", ["system", "public"])
async def test_an_admin_owner_can_make_a_fact_platform_wide(visibility):
    kb = _collab_kb({"owner_id": "u1", "visibility": "private"})

    response = await _set_permissions(kb, "admin", visibility)

    assert response["visibility"] == visibility
    assert kb.update_fact.await_args.kwargs["metadata"]["visibility"] == visibility


@pytest.mark.asyncio
async def test_a_permissions_change_is_written_through_update_fact_not_the_hash():
    kb = _collab_kb({"owner_id": "u1", "visibility": "system"})

    await _set_permissions(kb, "user", "private")

    kb.update_fact.assert_awaited_once()
    kb.redis.return_value.hset.assert_not_called()


@pytest.mark.asyncio
async def test_a_failed_permissions_write_is_not_reported_as_success():
    kb = _collab_kb({"owner_id": "u1", "visibility": "private"}, write_status="error")

    with pytest.raises(HTTPException) as err:
        await _set_permissions(kb, "user", "private")

    assert err.value.status_code == 500


async def _admin_sets_visibility(kb, visibility: str):
    from api import knowledge_ownership as ownership_api

    request = MagicMock()
    request.state.user = {"user_id": "u1"}
    with patch.object(ownership_api, "get_or_create_knowledge_base", AsyncMock(return_value=kb)):
        return await ownership_api.update_fact_visibility(
            fact_id="f1", request_body=SimpleNamespace(visibility=visibility), request=request, _={}
        )


def _ownership_kb(write_status: str = "success"):
    kb = MagicMock()
    kb.get_fact = MagicMock(return_value={"metadata": {"owner_id": "u1", "visibility": "system"}})  # sync (#16670)
    kb.ownership_manager = MagicMock()
    kb.ownership_manager.check_access = AsyncMock(return_value=True)
    kb.update_fact = AsyncMock(return_value={"status": write_status})
    return kb


@pytest.mark.asyncio
async def test_the_admin_visibility_route_writes_through_update_fact():
    kb = _ownership_kb()

    response = await _admin_sets_visibility(kb, "private")

    assert response["visibility"] == "private"
    assert kb.update_fact.await_args.kwargs["metadata"]["visibility"] == "private"


@pytest.mark.asyncio
async def test_a_failed_admin_visibility_write_is_not_reported_as_success():
    with pytest.raises(HTTPException) as err:
        await _admin_sets_visibility(_ownership_kb(write_status="error"), "private")

    assert err.value.status_code == 500
