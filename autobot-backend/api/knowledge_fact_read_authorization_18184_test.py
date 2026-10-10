# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The collaboration access-info route keeps its responses through the shared helper (#18184)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api import knowledge_collaboration as mod

USER = {"user_id": "alice", "username": "alice", "role": "user"}
META = {"owner_id": "alice", "visibility": "private"}


def _kb(metadata, allowed=True):
    kb = MagicMock()
    kb.ownership_manager.check_access = AsyncMock(return_value=allowed)
    kb.redis.return_value.hget = AsyncMock(return_value=None if metadata is None else json.dumps(metadata))
    return kb


async def _call(kb, user=USER):
    with patch.object(mod, "get_or_create_knowledge_base", AsyncMock(return_value=kb)):
        return await mod.get_knowledge_access_info(fact_id="f1", request=MagicMock(), current_user=user)


@pytest.mark.asyncio
async def test_missing_fact_is_404_fact_not_found():
    with pytest.raises(HTTPException) as exc:
        await _call(_kb(None))
    assert (exc.value.status_code, exc.value.detail) == (404, "Fact not found")


@pytest.mark.asyncio
async def test_denied_is_403_access_denied():
    with pytest.raises(HTTPException) as exc:
        await _call(_kb(META, allowed=False))
    assert (exc.value.status_code, exc.value.detail) == (403, "Access denied")


@pytest.mark.asyncio
async def test_allowed_body_and_check_access_arguments():
    kb = _kb(META)
    body = await _call(kb)
    assert body == mod._build_access_response("f1", META, "alice")
    assert kb.ownership_manager.check_access.await_args.kwargs == {
        "fact_id": "f1",
        "user_id": "alice",
        "fact_metadata": META,
        "user_org_id": None,
        "user_group_ids": [],
        "is_admin": False,
    }


@pytest.mark.asyncio
async def test_an_admin_reads_any_fact():
    kb = _kb(META)
    await _call(kb, {**USER, "role": "admin"})
    assert kb.ownership_manager.check_access.await_args.kwargs["is_admin"] is True


# --- knowledge_ownership._get_fact_with_ownership (admin-only routes, bare user id) ---


async def _owned(fact, allowed=True, manager=True):
    from api import knowledge_ownership as own

    kb = MagicMock()
    kb.get_fact = MagicMock(return_value=fact)
    kb.ownership_manager = MagicMock() if manager else None
    if manager:
        kb.ownership_manager.check_access = AsyncMock(return_value=allowed)
    return kb, await own._get_fact_with_ownership(kb, "f1", "admin-1")


@pytest.mark.asyncio
async def test_ownership_route_allowed_returns_fact_and_passes_admin_read_through():
    fact = {"metadata": META}
    kb, got = await _owned(fact)
    assert got == fact
    assert kb.ownership_manager.check_access.await_args.kwargs == {
        "fact_id": "f1",
        "user_id": "admin-1",
        "fact_metadata": META,
        "user_org_id": None,
        "user_group_ids": [],
        "is_admin": True,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fact", "allowed", "manager", "status", "detail"),
    [
        (None, True, True, 404, "Fact not found"),
        ({"metadata": META}, True, False, 503, "Ownership management not available"),
        ({"metadata": META}, False, True, 403, "You do not have access to this fact"),
    ],
)
async def test_ownership_route_errors_are_unchanged(fact, allowed, manager, status, detail):
    with pytest.raises(HTTPException) as exc:
        await _owned(fact, allowed, manager)
    assert (exc.value.status_code, exc.value.detail) == (status, detail)
