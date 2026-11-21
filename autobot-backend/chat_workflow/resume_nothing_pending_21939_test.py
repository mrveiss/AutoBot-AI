# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A resume with no pending interrupt is refused before the graph runs (#21939)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from chat_workflow import stall_pending
from chat_workflow.graph import initialize_session
from chat_workflow.session_init_guard import NO_TURN_MESSAGE

pytestmark = pytest.mark.asyncio


async def test_an_approval_resume_with_nothing_pending_is_a_409_nothing_to_resume(
    monkeypatch,
):
    monkeypatch.setattr(stall_pending, "pending_interrupts", AsyncMock(return_value=[]))
    with pytest.raises(HTTPException) as err:
        await stall_pending.check_resume_binding(MagicMock(), "s1", {"approved": True})
    assert err.value.status_code == 409
    assert err.value.detail == stall_pending.NOTHING_TO_RESUME


async def test_control_an_approval_resume_with_an_approval_interrupt_pending_passes(
    monkeypatch,
):
    monkeypatch.setattr(
        stall_pending,
        "pending_interrupts",
        AsyncMock(return_value=[{"type": "command_approval_request"}]),
    )
    await stall_pending.check_resume_binding(MagicMock(), "s1", {"approved": True})


async def test_the_entry_node_on_an_empty_state_reports_instead_of_raising_key_error():
    sent = []
    manager = MagicMock()
    manager._initialize_chat_session = AsyncMock()
    config = {"configurable": {"manager": manager, "stream_callback": sent.append}}
    update = await initialize_session({}, config)
    assert update["error"] == NO_TURN_MESSAGE
    assert sent == [{"type": "error", "content": NO_TURN_MESSAGE}]
    manager._initialize_chat_session.assert_not_called()
