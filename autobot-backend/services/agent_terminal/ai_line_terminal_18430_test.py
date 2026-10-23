# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The agent terminal resolves its command's AI line at the single enforcement point (#18430, #17463).

The role policy ``needs_approval`` (``auto_approve_safe`` / ``auto_approve_moderate``) had no caller
(#17463). It is now an INPUT to the point that can only tighten: a role that needs approval for a risk
can never be line 1, and a role that does not still needs a company to have set line 1 AND the
administrator to have relaxed the category -- the role flag alone never lets a command run.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.ai_lines import AiLine
from autobot_shared.status_enums import CommandRisk
from autobot_shared.tool_catalogue import valid_approval_categories
from chat_workflow import approval_baseline as baseline
from services import ai_line_enforcement as enforcement
from services.agent_terminal.models import AgentTerminalSession
from services.agent_terminal.service import AgentTerminalService
from services.command_approval_manager import AgentPermissions, AgentRole, CommandApprovalManager

pytestmark = pytest.mark.asyncio

ALL_RELAXED = sorted(valid_approval_categories())
TENANT = "00000000-0000-0000-0000-000000018430"


def _service(permissions=None):
    svc = AgentTerminalService.__new__(AgentTerminalService)
    manager = CommandApprovalManager(permissions)
    svc.approval_handler = MagicMock()
    svc.approval_handler.needs_approval = lambda role, risk: CommandApprovalManager.needs_approval(
        role, risk, manager.agent_permissions
    )
    svc.approval_handler.check_agent_permission = lambda role, risk: (True, "ok")
    svc.get_session = AsyncMock(return_value=_session())
    svc._validate_session_for_execution = lambda session, sid: None
    svc._drain_peer_messages = lambda session: None
    svc._assess_command = lambda command: (None, svc.risk, [], False, [])
    svc.risk = CommandRisk.SAFE
    svc.approval_handler.check_auto_approve_rules = AsyncMock(return_value=False)
    svc._queue_command_for_approval = AsyncMock(return_value={"status": "pending_approval"})
    svc._execute_auto_approved_command = AsyncMock(return_value={"status": "success"})
    return svc


def _session(role=AgentRole.CHAT_AGENT):
    return AgentTerminalSession(
        session_id="s", agent_id="agent-1", agent_role=role, conversation_id=None, tenant_id=TENANT
    )


def _world(stored=None, relaxed=None):
    return (
        patch.object(baseline, "fetch_slm_policy_json", AsyncMock(return_value=relaxed)),
        patch.object(enforcement, "_stored", AsyncMock(return_value=(stored, False))),
        patch.object(enforcement, "audit_log", AsyncMock(return_value=True)),
    )


async def _run(svc, stored=None, relaxed=None):
    a, b, c = _world(stored, relaxed)
    with a, b, c:
        return await svc.execute_command("s", "ls -la")


async def test_line_three_refuses_the_command_before_the_queue_and_before_running():
    svc = _service()
    result = await _run(svc, stored=AiLine.NEVER, relaxed=ALL_RELAXED)
    assert result["status"] == "error" and "never touches" in result["error"]
    svc._queue_command_for_approval.assert_not_awaited()
    svc._execute_auto_approved_command.assert_not_awaited()


async def test_an_unset_line_is_line_two_the_command_waits_in_the_queue():
    svc = _service()
    result = await _run(svc, stored=None, relaxed=ALL_RELAXED)
    assert result == {"status": "pending_approval"}
    svc._queue_command_for_approval.assert_awaited_once()
    svc._execute_auto_approved_command.assert_not_awaited()


async def test_line_one_runs_the_command_without_queuing_it():
    svc = _service()
    result = await _run(svc, stored=AiLine.AUTONOMOUS, relaxed=ALL_RELAXED)
    assert result == {"status": "success"}
    svc._queue_command_for_approval.assert_not_awaited()


async def test_line_one_is_not_enough_while_the_baseline_gates_the_category():
    svc = _service()
    result = await _run(svc, stored=AiLine.AUTONOMOUS, relaxed=None)
    assert result == {"status": "pending_approval"}
    svc._execute_auto_approved_command.assert_not_awaited()


async def test_a_role_with_auto_approve_safe_false_does_not_auto_approve_a_safe_command():
    """The #17463 acceptance test: same SAFE command, same line 1, only the role flag differs."""
    loose = _service()
    strict = _service({AgentRole.CHAT_AGENT: AgentPermissions(max_risk=CommandRisk.MODERATE, auto_approve_safe=False)})
    assert (await _run(loose, AiLine.AUTONOMOUS, ALL_RELAXED)) == {"status": "success"}
    assert (await _run(strict, AiLine.AUTONOMOUS, ALL_RELAXED)) == {"status": "pending_approval"}
    strict._execute_auto_approved_command.assert_not_awaited()


async def test_the_role_flags_cover_moderate_commands_too():
    svc = _service()
    svc.risk = CommandRisk.MODERATE  # CHAT_AGENT defaults: auto_approve_moderate=False
    assert (await _run(svc, AiLine.AUTONOMOUS, ALL_RELAXED)) == {"status": "pending_approval"}
    permissive = _service(
        {AgentRole.CHAT_AGENT: AgentPermissions(max_risk=CommandRisk.MODERATE, auto_approve_moderate=True)}
    )
    permissive.risk = CommandRisk.MODERATE
    assert (await _run(permissive, AiLine.AUTONOMOUS, ALL_RELAXED)) == {"status": "success"}


async def test_the_role_flag_alone_never_lets_a_command_run():
    """A permissive role with no line set is still line 2: the role policy only tightens."""
    svc = _service({AgentRole.CHAT_AGENT: AgentPermissions(max_risk=CommandRisk.MODERATE, auto_approve_safe=True)})
    assert (await _run(svc, None, ALL_RELAXED)) == {"status": "pending_approval"}


async def test_a_session_with_no_verified_company_is_refused_even_on_line_one():
    svc = _service()
    session = _session()
    session.tenant_id = None
    svc.get_session = AsyncMock(return_value=session)
    result = await _run(svc, stored=AiLine.AUTONOMOUS, relaxed=ALL_RELAXED)
    assert result["status"] == "error" and "verified company" in result["error"]
    svc._execute_auto_approved_command.assert_not_awaited()


async def test_a_user_with_no_company_gets_line_two_for_their_terminal_commands():
    """No tenant: the owner's personal scope applies. Unset is line 2 (queued); a personal line 1 runs it."""
    session = _session()
    session.tenant_id = None
    session.owner = "alice"
    queued, ran = _service(), _service()
    for svc in (queued, ran):
        svc.get_session = AsyncMock(return_value=session)
    with patch("services.agent_terminal.ai_line_gate._owner_user_id", AsyncMock(return_value=str(uuid.UUID(int=7)))):
        assert await _run(queued, stored=None, relaxed=ALL_RELAXED) == {"status": "pending_approval"}
        assert await _run(ran, stored=AiLine.AUTONOMOUS, relaxed=ALL_RELAXED) == {"status": "success"}


async def test_a_forged_tenant_is_refused_and_is_not_replaced_by_the_owners_personal_scope():
    session = _session()
    session.tenant_id = "not-a-uuid"
    session.owner = "alice"
    svc = _service()
    svc.get_session = AsyncMock(return_value=session)
    result = await _run(svc, stored=AiLine.AUTONOMOUS, relaxed=ALL_RELAXED)
    assert result["status"] == "error"
    svc._execute_auto_approved_command.assert_not_awaited()
