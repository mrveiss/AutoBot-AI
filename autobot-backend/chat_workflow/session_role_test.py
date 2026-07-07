# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-session governed role binding (GH#11186)."""

from unittest.mock import AsyncMock

import pytest

from chat_workflow.session_role import (
    SessionRoleService,
    apply_role,
    valid_roles,
)


class _FakeRedis:
    def __init__(self):
        self.store = {}

    async def set(self, key, value, ex=None):
        self.store[key] = value

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, key):
        self.store.pop(key, None)


def _svc_with_redis(redis):
    svc = SessionRoleService()
    svc._get_redis = AsyncMock(return_value=redis)
    return svc


# --- valid_roles / apply_role (pure) --------------------------------------


def test_valid_roles_are_default_profile_ids():
    roles = valid_roles()
    assert "research_agent" in roles and "system_agent" in roles


def test_apply_role_overrides_client_agent_id():
    # trusted server role wins over a client-supplied agent_id
    out = apply_role({"agent_id": "attacker_choice", "x": 1}, "research_agent")
    assert out["agent_id"] == "research_agent"
    assert out["x"] == 1


def test_apply_role_none_leaves_context_unchanged():
    ctx = {"agent_id": "self_restrict"}
    assert apply_role(ctx, None) is ctx
    assert apply_role(None, None) is None


# --- SessionRoleService ----------------------------------------------------


@pytest.mark.asyncio
async def test_set_get_clear_roundtrip():
    redis = _FakeRedis()
    svc = _svc_with_redis(redis)
    await svc.set_role("s1", "research_agent")
    assert await svc.get_role("s1") == "research_agent"
    await svc.clear_role("s1")
    assert await svc.get_role("s1") is None


@pytest.mark.asyncio
async def test_set_role_rejects_unknown_role():
    svc = _svc_with_redis(_FakeRedis())
    with pytest.raises(ValueError):
        await svc.set_role("s1", "not_a_real_agent")


@pytest.mark.asyncio
async def test_get_role_decodes_bytes():
    redis = _FakeRedis()
    redis.store["autobot:session:s2:role"] = b"documentation_agent"
    svc = _svc_with_redis(redis)
    assert await svc.get_role("s2") == "documentation_agent"


@pytest.mark.asyncio
async def test_get_role_swallows_redis_failure():
    svc = SessionRoleService()
    svc._get_redis = AsyncMock(side_effect=RuntimeError("redis down"))
    assert await svc.get_role("s3") is None  # must not raise into chat


# --- end-to-end: pinned role → forbidden tool blocked at the seam ----------


def test_pinned_role_blocks_forbidden_tool_end_to_end():
    """apply_role → build_governed_identity → _enforce_forbidden_work must block."""
    from types import SimpleNamespace

    from chat_workflow.models import build_governed_identity
    from chat_workflow.tool_handler import ToolHandlerMixin

    # A session pinned to research_agent (which forbids infra/shell tools).
    context = apply_role({"agent_id": "client_supplied_ignored"}, "research_agent")
    agent_context, _, _ = build_governed_identity(context, "sess-e2e")
    assert agent_context.agent_id == "research_agent"  # trusted role won

    mixin = ToolHandlerMixin.__new__(ToolHandlerMixin)
    ctx = SimpleNamespace(agent_context=agent_context, requires_approval_before=[], work_item_id=None)
    results: list[dict] = []
    msg = mixin._enforce_forbidden_work({"name": "bash"}, ctx, results)
    assert msg is not None and msg.metadata.get("forbidden_by_manifest") is True
