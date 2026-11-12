# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every product route that used to wipe the knowledge base now only proposes the wipe (#21048, #17038).

The admin route, ``POST /knowledge_base/clear_all`` and the MCP ``flush`` operation share one entry
(``services.kb_wipe_request``): the same principals may ask, the answer has the same shape, and no store is
touched. Fakes only; a store that is called at all fails the test.
"""

import inspect
import types
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api import admin_kb_wipe, knowledge, knowledge_mcp
from services import kb_wipe_action, kb_wipe_chroma, kb_wipe_redis
from services import kb_wipe_request as request_mod

APPROVAL = uuid.UUID("00000000-0000-4000-8000-000000000021")
ADMIN_ID = "00000000-0000-4000-8000-0000000000a1"
ADMIN = {"id": ADMIN_ID, "role": "admin"}
SHAPE = {"approval_id": str(APPROVAL), "status": "pending", "action": kb_wipe_action.ACTION}

#: Callers that must NOT be able to ask: an ordinary user, an operator, a service principal, an admin that is
#: not a user id, and an admin that names nobody.
REFUSED = {
    "ordinary_user": {"id": ADMIN_ID, "role": "user"},
    "operator": {"id": ADMIN_ID, "role": "operator"},
    "service": {"username": "svc", "service": True},
    "admin_without_a_user_id": {"id": "not-a-user-id", "role": "admin"},
    "admin_naming_nobody": {"role": "admin"},
}


@pytest.fixture
def world(monkeypatch):
    """Proposals are recorded; the knowledge base and the vectors database are mocks that must stay untouched."""
    proposals: list[str] = []

    async def plan():
        return {"total_keys": 3}

    async def propose(session, requested_by, plan_):
        proposals.append(requested_by)
        return types.SimpleNamespace(id=APPROVAL, status="pending")

    kb, vectors = MagicMock(name="knowledge_base"), MagicMock(name="vectors_redis")
    monkeypatch.setattr(request_mod, "plan_kb_wipe", plan)
    monkeypatch.setattr(request_mod, "propose_kb_wipe", propose)
    monkeypatch.setattr(knowledge, "get_or_create_knowledge_base", AsyncMock(return_value=kb))
    monkeypatch.setattr(knowledge_mcp, "get_knowledge_base", lambda: kb)
    monkeypatch.setattr(knowledge_mcp, "get_vectors_redis_client", lambda: vectors)
    return types.SimpleNamespace(proposals=proposals, kb=kb, vectors=vectors)


def _nothing_deleted(world) -> None:
    assert world.kb.method_calls == [] and world.vectors.method_calls == []
    world.vectors.flushdb.assert_not_called()


async def _clear_all(user):
    return await knowledge.clear_all_knowledge(
        admin_check=True, request=None, req=None, current_user=user, session=MagicMock()
    )


async def _flush(user):
    body = {"operation": "flush", "params": {"confirm": True}}
    return await knowledge_mcp.mcp_redis_vector_operations(request=body, current_user=user, session=MagicMock())


# -- an admin user: a proposal exists, nothing is deleted ------------------------------------------------------


@pytest.mark.asyncio
async def test_the_admin_route_clear_all_and_mcp_flush_each_create_one_proposal_and_delete_nothing(world):
    assert await admin_kb_wipe.propose_knowledge_wipe(current_user=ADMIN, session=MagicMock()) == SHAPE
    assert await _clear_all(ADMIN) == SHAPE
    flushed = await _flush(ADMIN)
    assert flushed == {"success": True, "operation": "flush", "message": "Wipe requested; awaiting approval", **SHAPE}
    assert world.proposals == [ADMIN_ID] * 3  # one proposal per route, each naming the admin who asked
    _nothing_deleted(world)


# -- everyone else: refused, nothing proposed, nothing deleted -------------------------------------------------


@pytest.mark.parametrize("who", sorted(REFUSED))
@pytest.mark.asyncio
async def test_the_admin_route_and_clear_all_refuse_a_caller_who_may_not_propose(world, who):
    with pytest.raises(HTTPException) as admin_route:
        await admin_kb_wipe.propose_knowledge_wipe(current_user=REFUSED[who], session=MagicMock())
    with pytest.raises(HTTPException) as clear_all:
        await _clear_all(REFUSED[who])
    assert admin_route.value.status_code == 403 and clear_all.value.status_code == 403
    assert world.proposals == []
    _nothing_deleted(world)


@pytest.mark.parametrize("who", sorted(REFUSED))
@pytest.mark.asyncio
async def test_mcp_flush_with_confirm_true_is_refused_for_a_caller_who_may_not_propose(world, who):
    refused = await _flush(REFUSED[who])
    assert refused["success"] is False and refused["operation"] == "flush" and "approval_id" not in refused
    assert world.proposals == []
    _nothing_deleted(world)


@pytest.mark.asyncio
async def test_mcp_flush_without_confirm_still_only_proposes_never_flushes(world):
    body = {"operation": "flush", "params": {}}
    flushed = await knowledge_mcp.mcp_redis_vector_operations(request=body, current_user=ADMIN, session=MagicMock())
    assert flushed["success"] is True and flushed["approval_id"] == str(APPROVAL)
    _nothing_deleted(world)


# -- the other vector operations are unchanged -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_other_vector_operations_still_dispatch_and_flush_is_not_among_them(world):
    reindex = {"operation": "reindex"}
    answer = await knowledge_mcp.mcp_redis_vector_operations(
        request=reindex, current_user=REFUSED["ordinary_user"], session=MagicMock()
    )
    assert answer["success"] is True and answer["operation"] == "reindex"
    assert "flush" not in knowledge_mcp._VECTOR_OPERATIONS
    assert world.proposals == []


# -- the old deletion paths are gone ---------------------------------------------------------------------------


def test_no_request_handler_module_can_reach_a_flush_or_the_old_clear_paths():
    for module in (knowledge, knowledge_mcp, admin_kb_wipe, request_mod, kb_wipe_action, kb_wipe_redis, kb_wipe_chroma):
        text = Path(inspect.getsourcefile(module)).read_text(encoding="utf-8").lower()
        assert "flushdb" not in text and "flushall" not in text, module.__name__
    assert not hasattr(knowledge, "_clear_kb_via_redis") and not hasattr(knowledge_mcp, "_vector_op_flush")
    source = inspect.getsource(knowledge.clear_all_knowledge)
    assert "get_or_create_knowledge_base" not in source and "redis" not in source.lower()
