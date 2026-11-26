# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The whole-turn timeout is reported only when the turn deadline expired (#21938)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from chat_workflow import turn_control

pytestmark = pytest.mark.asyncio


async def _events(monkeypatch, body, deadline: float = 30.0) -> list:
    monkeypatch.setattr(turn_control, "_drop_checkpoint", AsyncMock())
    monkeypatch.setattr(turn_control, "CHAT_TURN_TIMEOUT_SECONDS", deadline)
    queue: asyncio.Queue = asyncio.Queue()
    await turn_control._run_turn(body, queue, turn_control._Turn(session_id="s1"))
    return [queue.get_nowait() for _ in range(queue.qsize())]


async def test_an_inner_timeout_is_reported_as_an_error_not_the_turn_deadline(
    monkeypatch,
):
    async def body(_queue):
        raise TimeoutError("Timeout on reading data from socket")

    events = await _events(monkeypatch, body)
    assert events[0] == {"type": "error", "content": turn_control.ERROR_MESSAGE}


async def test_the_expired_turn_deadline_is_reported_as_the_turn_timeout(monkeypatch):
    async def body(_queue):
        await asyncio.sleep(30)

    events = await _events(monkeypatch, body, deadline=0.01)
    assert events[0] == {"type": "error", "content": turn_control.TIMEOUT_MESSAGE}
