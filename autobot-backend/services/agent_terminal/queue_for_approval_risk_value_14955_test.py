# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The UI-facing pending-approval response carries the converted RiskLevel;
internal session state (feeding the auto-approve rules engine) keeps the raw
CommandRisk (#14955 review findings).

`_queue_command_for_approval` builds two things from the same `risk:
CommandRisk` value: a `CommandExecution` (via `create_command_execution`,
which already calls `map_risk_to_level`) and a pending-approval response
dict returned to the caller. Before the first fix, the response dict used
`risk.value` directly -- the raw, lowercase `CommandRisk` wire value
(`"dangerous"`, `"forbidden"`, `"moderate"`, ...) -- while the
`CommandExecution` sibling got the converted, uppercase `RiskLevel` value.
That response dict is what
`chat_workflow/tool_handler.py::_build_approval_request_message` reads via
`result.get("risk")` into `metadata["risk_level"]`, which is exactly the
field `ApprovalRequestCard.vue` and `ChatMessages.vue` render through
`getRiskClass`. A `CommandRisk.DANGEROUS` command reached that surface as
`"dangerous"` -- a value outside the frontend's `RiskLevel` vocabulary,
which fell back to the low-risk/green class on the exact surface a user is
about to approve a destructive command from.

A second review pass found that converting `session.pending_approval["risk"]`
itself (rather than only the returned response) broke the auto-approve rules
engine: `store_auto_approve_rule` (fed from `get_pending_risk_level()`) would
persist the converted `RiskLevel`, but `check_auto_approve_rules` (in
`_check_auto_approval_or_queue`) still compares against the raw
`CommandRisk.value` freshly assessed for each new command -- an exact string
compare that can never match again once the stored vocabulary changes. So
`session.pending_approval["risk"]` -- and everything downstream of
`get_pending_risk_level()` -- must stay in the `CommandRisk` vocabulary;
ONLY the returned UI response is converted.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.asyncio


def _service():
    from services.agent_terminal.service import AgentTerminalService

    svc = AgentTerminalService.__new__(AgentTerminalService)
    svc.command_queue = AsyncMock()
    svc.command_queue.add_command = AsyncMock(return_value=True)
    svc.redis_client = None
    svc.session_manager = AsyncMock()
    svc.terminal_logger = AsyncMock()
    return svc


def _session():
    from services.agent_terminal.models import AgentTerminalSession
    from services.command_approval_manager import AgentRole

    return AgentTerminalSession(
        session_id="sess-14955",
        agent_id="agent-1",
        agent_role=AgentRole.CHAT_AGENT,
        conversation_id=None,
    )


@pytest.mark.parametrize(
    ("raw_risk_name", "expected_ui_risk_level"),
    [
        ("SAFE", "LOW"),
        ("MODERATE", "MEDIUM"),
        ("HIGH", "HIGH"),
        ("CRITICAL", "CRITICAL"),
        ("DANGEROUS", "CRITICAL"),
        ("FORBIDDEN", "CRITICAL"),
    ],
)
async def test_ui_response_carries_converted_risk_level(raw_risk_name, expected_ui_risk_level):
    from autobot_shared.status_enums import CommandRisk

    svc = _service()
    session = _session()
    risk = CommandRisk[raw_risk_name]

    response = await svc._queue_command_for_approval(
        session=session,
        command="shutdown --now",
        description=None,
        risk=risk,
        reasons=["test"],
        is_interactive=False,
        interactive_reasons=[],
    )

    # The raw CommandRisk value (lowercase, e.g. "dangerous") must never reach
    # the response the frontend renders through.
    assert response["risk"] != risk.value
    assert response["risk"] == expected_ui_risk_level


@pytest.mark.parametrize(
    "raw_risk_name",
    ["SAFE", "MODERATE", "HIGH", "CRITICAL", "DANGEROUS", "FORBIDDEN"],
)
async def test_internal_pending_state_keeps_raw_command_risk(raw_risk_name):
    """session.pending_approval must stay in the CommandRisk vocabulary the
    auto-approve rules engine checks against -- converting it here would
    desync store_auto_approve_rule from check_auto_approve_rules."""
    from autobot_shared.status_enums import CommandRisk

    svc = _service()
    session = _session()
    risk = CommandRisk[raw_risk_name]

    await svc._queue_command_for_approval(
        session=session,
        command="shutdown --now",
        description=None,
        risk=risk,
        reasons=["test"],
        is_interactive=False,
        interactive_reasons=[],
    )

    assert session.get_pending_risk_level() == risk.value


async def test_auto_approve_rule_matches_after_the_full_store_and_check_round_trip():
    """Reproduces the review's HIGH finding end-to-end with the real
    ApprovalHandler/CommandApprovalManager (no mocks for these two calls):
    queue a command for approval (populating session.pending_approval["risk"]
    via the real _queue_command_for_approval), store an "always allow" rule
    using that SAME stored value (exactly as _post_execution_updates does via
    get_pending_risk_level() -> store_auto_approve_rule), then check a
    freshly re-assessed risk for the same command against the real rules
    engine (exactly as _check_auto_approval_or_queue does). Before the fix
    that reverted session.pending_approval["risk"] to the raw CommandRisk
    vocabulary, the stored rule held the converted RiskLevel ("CRITICAL")
    while this check still compared against the raw CommandRisk ("dangerous"),
    so the rule could never match again."""
    from autobot_shared.status_enums import CommandRisk
    from services.agent_terminal.approval_handler import ApprovalHandler
    from services.command_approval_manager import CommandApprovalManager

    svc = _service()
    svc.approval_handler = ApprovalHandler(approval_manager=CommandApprovalManager())
    session = _session()
    command = "shutdown --now"
    user_id = "user-1"

    await svc._queue_command_for_approval(
        session=session,
        command=command,
        description=None,
        risk=CommandRisk.DANGEROUS,
        reasons=["destructive pattern"],
        is_interactive=False,
        interactive_reasons=[],
    )
    stored_risk_level = session.get_pending_risk_level()

    # Real store, exactly as _post_execution_updates does on "always allow".
    await svc.approval_handler.store_auto_approve_rule(
        user_id=user_id,
        command=command,
        risk_level=stored_risk_level,
    )

    # SecureCommandExecutor.assess_command_risk is deterministic for the same
    # command text, so a later invocation re-assesses the identical
    # CommandRisk -- checked here exactly as _check_auto_approval_or_queue
    # does.
    is_auto_approved = await svc.approval_handler.check_auto_approve_rules(
        user_id=user_id,
        command=command,
        risk_level=CommandRisk.DANGEROUS.value,
    )

    assert is_auto_approved is True
