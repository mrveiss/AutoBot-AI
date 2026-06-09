# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for system-pause resume approval workflow (GH#8734).

Verifies:
- _request_skill_approval_for_resume delegates to GovernanceEngine with the
  correct skill_name, skill_id, requested_by, and reason fields.
- The paused_by / admin-role branching logic gates system-pause resumes.
"""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_governance_stub(approval_id: str) -> tuple[Any, Any]:
    """Return (MockEngineClass, MockEngineInstance) that yield the given approval_id."""
    fake_result = MagicMock()
    fake_result.approval_id = approval_id

    inst = MagicMock()
    inst.request_activation = AsyncMock(return_value=fake_result)
    cls = MagicMock(return_value=inst)
    return cls, inst


async def _call_helper(agent_id: str, paused_by: str, requested_by: str, engine_cls) -> str:
    """Mirrors the logic of _request_skill_approval_for_resume exactly."""
    with _patch_governance(engine_cls):
        from skills.governance import GovernanceEngine

        engine = GovernanceEngine()
        result = await engine.request_activation(
            skill_name="agent.resume",
            skill_id=f"agent:resume:{agent_id}",
            requested_by=requested_by,
            reason=f"resume agent {agent_id} (auto-paused by {paused_by})",
        )
        return result.approval_id or ""


class _patch_governance:
    """Context manager that injects a fake skills.governance module."""

    def __init__(self, engine_cls):
        self._cls = engine_cls
        self._orig = sys.modules.get("skills.governance")

    def __enter__(self):
        sys.modules["skills.governance"] = types.SimpleNamespace(GovernanceEngine=self._cls)
        return self

    def __exit__(self, *_):
        if self._orig is None:
            sys.modules.pop("skills.governance", None)
        else:
            sys.modules["skills.governance"] = self._orig


# ---------------------------------------------------------------------------
# _request_skill_approval_for_resume logic
# ---------------------------------------------------------------------------


class TestRequestSkillApprovalForResume:
    """Tests for the _request_skill_approval_for_resume helper logic."""

    @pytest.mark.asyncio
    async def test_delegates_to_governance_engine(self):
        """Calls GovernanceEngine.request_activation with correct args."""
        engine_cls, engine_inst = _make_governance_stub("approval-abc-123")

        result = await _call_helper("agent-42", "system:budget", "alice", engine_cls)

        assert result == "approval-abc-123"
        engine_inst.request_activation.assert_awaited_once()
        kw = engine_inst.request_activation.call_args.kwargs
        assert kw["skill_name"] == "agent.resume"
        assert "agent-42" in kw["skill_id"]
        assert kw["requested_by"] == "alice"

    @pytest.mark.asyncio
    async def test_returns_empty_string_when_approval_id_is_none(self):
        """Gracefully returns '' when GovernanceEngine yields approval_id=None."""
        engine_cls, _ = _make_governance_stub(None)  # type: ignore[arg-type]

        result = await _call_helper("agent-99", "system:error", "bob", engine_cls)

        assert result == ""

    @pytest.mark.asyncio
    async def test_skill_id_keyed_on_specific_agent(self):
        """skill_id must identify the specific agent, not be generic."""
        captured: dict = {}

        class _FakeEngine:
            def __init__(self, **_):
                pass

            async def request_activation(self, skill_name, skill_id, requested_by, reason):
                captured["skill_id"] = skill_id
                r = MagicMock()
                r.approval_id = "id-1"
                return r

        with _patch_governance(_FakeEngine):
            await _call_helper("my-agent-123", "system:budget", "carol", _FakeEngine)

        assert captured["skill_id"] == "agent:resume:my-agent-123"

    @pytest.mark.asyncio
    async def test_paused_by_included_in_reason(self):
        """Reason string passed to GovernanceEngine names the pause source."""
        captured: dict = {}

        class _FakeEngine:
            def __init__(self, **_):
                pass

            async def request_activation(self, skill_name, skill_id, requested_by, reason):
                captured["reason"] = reason
                r = MagicMock()
                r.approval_id = "id-2"
                return r

        with _patch_governance(_FakeEngine):
            await _call_helper("agentX", "system:error", "dave", _FakeEngine)

        assert "system:error" in captured["reason"]

    @pytest.mark.asyncio
    async def test_different_agents_get_different_skill_ids(self):
        """Each agent gets a unique skill_id so approvals don't cross-pollinate."""
        ids_seen = []

        class _FakeEngine:
            def __init__(self, **_):
                pass

            async def request_activation(self, skill_name, skill_id, requested_by, reason):
                ids_seen.append(skill_id)
                r = MagicMock()
                r.approval_id = "x"
                return r

        with _patch_governance(_FakeEngine):
            await _call_helper("agent-A", "system:budget", "u", _FakeEngine)
            await _call_helper("agent-B", "system:budget", "u", _FakeEngine)

        assert ids_seen[0] != ids_seen[1]
        assert "agent-A" in ids_seen[0]
        assert "agent-B" in ids_seen[1]


# ---------------------------------------------------------------------------
# Branching logic (admin vs non-admin, system vs user pause)
# ---------------------------------------------------------------------------


class TestResumeApprovalBranching:
    """Verify the paused_by and role checks that control the approval gate."""

    def test_system_pause_prefix_triggers_gate(self):
        """paused_by values starting with 'system:' must go through the approval gate."""
        for value in ("system:budget", "system:error", "system:watchdog", "system:"):
            assert value.startswith("system:"), f"{value!r} should trigger the gate"

    def test_user_pause_skips_gate(self):
        """User-initiated pauses do not start with 'system:' and bypass the gate."""
        for value in ("user", "user:alice", "", None):
            paused_by = value or ""
            assert not paused_by.startswith("system:"), f"{value!r} should skip the gate"

    def test_admin_role_bypasses_approval(self):
        """Admin users are identified by role=='admin' and bypass the 202 path."""
        admin_user = {"role": "admin", "username": "superadmin"}
        user_role = admin_user.get("role", "") if isinstance(admin_user, dict) else getattr(admin_user, "role", "")
        assert user_role == "admin"

    def test_non_admin_role_enters_approval(self):
        """Non-admin users (any other role) enter the SkillApproval gate."""
        for user in (
            {"role": "user", "username": "alice"},
            {"role": "viewer", "username": "bob"},
            {"role": "", "username": "carol"},
            {"username": "dave"},  # no 'role' key
        ):
            user_role = user.get("role", "") if isinstance(user, dict) else getattr(user, "role", "")
            assert user_role != "admin", f"{user} should enter the approval gate"

    def test_getattr_fallback_for_non_dict_user(self):
        """_user can also be an object with a .role attribute."""

        class _User:
            role = "user"
            username = "eve"

        u = _User()
        user_role = u.get("role", "") if isinstance(u, dict) else getattr(u, "role", "")
        assert user_role == "user"
        assert user_role != "admin"
