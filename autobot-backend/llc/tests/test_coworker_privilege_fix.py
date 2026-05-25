# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for GH#8583 — CoWorkerSetRequest.caller_role privilege escalation fix.

Verifies:
1. CoWorkerSetRequest no longer accepts caller_role (schema-level guard).
2. resolve_actor_role looks up human membership and returns the correct role.
3. resolve_actor_role falls back to AgentOrgNode org_role for agent actors.
4. resolve_actor_role defaults to "member" when the actor is unknown.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from llc.services.work_item_service import resolve_actor_role

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _membership(role_value: str) -> MagicMock:
    m = MagicMock()
    m.role = MagicMock()
    m.role.value = role_value
    return m


def _agent_node(org_role_value: str) -> MagicMock:
    n = MagicMock()
    n.org_role = MagicMock()
    n.org_role.value = org_role_value
    return n


def _make_session(*results):
    """Return a mock AsyncSession that yields results[0], results[1], ... in order.

    When actor_id is a non-UUID string (agent key), the user-path UUID parse
    raises ValueError before calling execute, so the agent-path execute is the
    FIRST call (index 0).  Pass results in the order they will actually be
    called from the function under test.
    """
    session = AsyncMock()
    results_list = list(results)
    idx = [0]

    async def fake_execute(_stmt):
        result = MagicMock()
        val = results_list[idx[0]] if idx[0] < len(results_list) else None
        result.scalar_one_or_none.return_value = val
        idx[0] += 1
        return result

    session.execute = fake_execute
    return session


# ---------------------------------------------------------------------------
# Schema test: caller_role must not be a field on CoWorkerSetRequest
# ---------------------------------------------------------------------------


def test_coworker_set_request_has_no_caller_role_field():
    """GH#8583: caller_role must not appear in the CoWorkerSetRequest class definition."""
    import ast
    import pathlib

    src = (pathlib.Path(__file__).parent.parent / "api" / "work_items.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "CoWorkerSetRequest":
            field_names = [
                t.target.id for t in node.body if isinstance(t, ast.AnnAssign) and isinstance(t.target, ast.Name)
            ]
            assert (
                "caller_role" not in field_names
            ), "CoWorkerSetRequest still defines caller_role — GH#8583 fix not applied"
            return  # class found and checked

    raise AssertionError("CoWorkerSetRequest class not found in work_items.py")


# ---------------------------------------------------------------------------
# resolve_actor_role — unit tests (actor_id is a valid UUID → user path)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_returns_member_when_actor_id_none():
    role = await resolve_actor_role(AsyncMock(), None, str(uuid.uuid4()))
    assert role == "member"


@pytest.mark.asyncio
async def test_resolve_returns_owner_from_membership():
    # actor_id is a UUID → user execute is call 0
    session = _make_session(_membership("owner"))
    role = await resolve_actor_role(session, str(uuid.uuid4()), str(uuid.uuid4()))
    assert role == "owner"


@pytest.mark.asyncio
async def test_resolve_returns_admin_from_membership():
    session = _make_session(_membership("admin"))
    role = await resolve_actor_role(session, str(uuid.uuid4()), str(uuid.uuid4()))
    assert role == "admin"


@pytest.mark.asyncio
async def test_resolve_returns_member_from_membership():
    session = _make_session(_membership("member"))
    role = await resolve_actor_role(session, str(uuid.uuid4()), str(uuid.uuid4()))
    assert role == "member"


# ---------------------------------------------------------------------------
# resolve_actor_role — agent path (actor_id is a non-UUID string)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_agent_manager_maps_to_admin():
    """Non-UUID actor_id → UUID parse fails → agent execute is call 0."""
    session = _make_session(_agent_node("manager"))
    role = await resolve_actor_role(session, "agent-abc", str(uuid.uuid4()))
    assert role == "admin"


@pytest.mark.asyncio
async def test_resolve_agent_coordinator_maps_to_lead():
    session = _make_session(_agent_node("coordinator"))
    role = await resolve_actor_role(session, "agent-abc", str(uuid.uuid4()))
    assert role == "lead"


@pytest.mark.asyncio
async def test_resolve_agent_specialist_maps_to_member():
    session = _make_session(_agent_node("specialist"))
    role = await resolve_actor_role(session, "agent-abc", str(uuid.uuid4()))
    assert role == "member"


@pytest.mark.asyncio
async def test_resolve_agent_worker_maps_to_member():
    session = _make_session(_agent_node("worker"))
    role = await resolve_actor_role(session, "agent-abc", str(uuid.uuid4()))
    assert role == "member"


@pytest.mark.asyncio
async def test_resolve_defaults_to_member_when_agent_not_found():
    session = _make_session(None)
    role = await resolve_actor_role(session, "agent-abc", str(uuid.uuid4()))
    assert role == "member"


@pytest.mark.asyncio
async def test_resolve_uuid_actor_no_membership_no_agent_defaults_to_member():
    """UUID actor_id → user lookup returns None → agent lookup returns None → member."""
    session = _make_session(None, None)
    role = await resolve_actor_role(session, str(uuid.uuid4()), str(uuid.uuid4()))
    assert role == "member"
