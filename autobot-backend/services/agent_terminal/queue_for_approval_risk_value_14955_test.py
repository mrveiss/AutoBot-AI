# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The pending-approval response must carry the converted RiskLevel, not the
raw CommandRisk (#14955 review finding).

`_queue_command_for_approval` builds two objects from the same `risk:
CommandRisk` value: a `CommandExecution` (via `create_command_execution`,
which already calls `map_risk_to_level`) and a pending-approval response
dict. Before this fix, the response dict used `risk.value` directly — the
raw, lowercase `CommandRisk` wire value (`"dangerous"`, `"forbidden"`,
`"moderate"`, ...) — while the `CommandExecution` sibling got the converted,
uppercase `RiskLevel` value. That response dict is what
`chat_workflow/tool_handler.py::_build_approval_request_message` reads via
`result.get("risk")` into `metadata["risk_level"]`, which is exactly the
field `ApprovalRequestCard.vue` and `ChatMessages.vue` render through
`getRiskClass`. A `CommandRisk.DANGEROUS` command reached that surface as
`"dangerous"` — a value outside the frontend's `RiskLevel` vocabulary, which
fell back to the low-risk/green class on the exact surface a user is about
to approve a destructive command from.
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
    ("raw_risk_name", "expected_risk_level"),
    [
        ("SAFE", "LOW"),
        ("MODERATE", "MEDIUM"),
        ("HIGH", "HIGH"),
        ("CRITICAL", "CRITICAL"),
        ("DANGEROUS", "CRITICAL"),
        ("FORBIDDEN", "CRITICAL"),
    ],
)
async def test_pending_approval_response_carries_converted_risk_level(raw_risk_name, expected_risk_level):
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
    assert response["risk"] == expected_risk_level
    assert session.pending_approval["risk"] == expected_risk_level
