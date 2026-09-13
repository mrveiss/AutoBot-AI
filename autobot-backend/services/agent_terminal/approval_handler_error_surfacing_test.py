# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A broad `except Exception` hid a TypeError on every approval-state write (#13281).

`update_chat_approval_status` wrapped its persistence call in `except Exception`
and logged "non-fatal". The call passed `role=` and `metadata=`, two keywords
`MessagesMixin.add_message` does not accept, so it raised `TypeError` on EVERY
invocation — approval status was never written to chat history, not once. The
turn continued, the log said non-fatal, and nothing surfaced it.

The keyword fix shipped separately. What these tests hold is the handler shape
that let it survive: a signature mismatch must reach the caller, while a genuine
storage blip still degrades. Both outcomes are asserted, because narrowing that
merely re-raised everything would also pass a test for the first alone.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from services.agent_terminal.approval_handler import ApprovalHandler
from services.agent_terminal.models import AgentTerminalSession
from services.command_approval_manager import AgentRole


class _Boom:
    """A chat-history double whose write raises whatever it was handed."""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def update_message_metadata(self, **_kwargs) -> bool:
        return True

    async def add_message(self, **_kwargs):
        raise self._exc


class _BoomQueue:
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def approve_command(self, **_kwargs):
        raise self._exc

    async def deny_command(self, **_kwargs):
        raise self._exc


def _session() -> AgentTerminalSession:
    return AgentTerminalSession(
        session_id="term-1",
        agent_id="agent-1",
        agent_role=AgentRole.CHAT_AGENT,
        conversation_id="conv-1",
    )


def _handler(*, chat=None, queue=None) -> ApprovalHandler:
    return ApprovalHandler(approval_manager=object(), chat_history_manager=chat, command_queue=queue)


@pytest.mark.asyncio
async def test_a_signature_mismatch_reaches_the_caller():
    """The exact defect: a wrong keyword must not be logged away as non-fatal."""
    exc = TypeError("MessagesMixin.add_message() got an unexpected keyword argument 'role'")
    handler = _handler(chat=_Boom(exc))

    with pytest.raises(TypeError, match="unexpected keyword argument"):
        await handler.update_chat_approval_status(_session(), "ls -la", approved=True)


@pytest.mark.asyncio
async def test_an_attribute_error_reaches_the_caller():
    """An unwired storage object is a programming error too, not a degraded write."""
    handler = _handler(chat=_Boom(AttributeError("'NoneType' object has no attribute 'add_message'")))

    with pytest.raises(AttributeError):
        await handler.update_chat_approval_status(_session(), "ls -la", approved=True)


@pytest.mark.asyncio
async def test_a_transient_storage_error_still_degrades(caplog):
    """Narrowing must not turn a Redis blip into a failed approval turn.

    The oracle for the tests above is only meaningful if the handler still
    catches something — a handler that re-raised everything would satisfy them
    while being a different bug.
    """
    handler = _handler(chat=_Boom(RedisConnectionError("connection reset by peer")))

    with caplog.at_level("ERROR"):
        await handler.update_chat_approval_status(_session(), "ls -la", approved=True)

    assert "was NOT persisted" in caplog.text, "a dropped write was not reported at all"
    assert "ConnectionError" in caplog.text, "the log does not name the exception type"


@pytest.mark.asyncio
async def test_the_queue_handler_surfaces_a_programming_error():
    """The sibling handler in the same file carried the identical shape."""
    handler = _handler(queue=_BoomQueue(TypeError("approve_command() got an unexpected keyword argument")))

    with pytest.raises(TypeError):
        await handler.update_command_queue_status("cmd-1", approved=True)


@pytest.mark.asyncio
async def test_the_queue_handler_still_degrades_on_a_storage_blip(caplog):
    handler = _handler(queue=_BoomQueue(RedisConnectionError("connection reset by peer")))

    with caplog.at_level("ERROR"):
        await handler.update_command_queue_status("cmd-1", approved=True)

    assert "was NOT updated" in caplog.text


@pytest.mark.asyncio
async def test_the_broadcast_handler_surfaces_a_programming_error(monkeypatch):
    """The two handlers inside broadcast_approval_status had the same shape."""
    import events.bus as bus

    async def _bad_publish(*_args, **_kwargs):
        raise TypeError("publish_event() got an unexpected keyword argument 'payload'")

    monkeypatch.setattr(bus, "publish_event", _bad_publish)
    handler = _handler()

    with pytest.raises(TypeError):
        await handler.broadcast_approval_status(_session(), "ls -la", approved=True)


@pytest.mark.asyncio
async def test_the_broadcast_handler_still_degrades_on_a_transport_blip(monkeypatch, caplog):
    import events.bus as bus

    async def _dropped(*_args, **_kwargs):
        raise RedisConnectionError("event bus unreachable")

    monkeypatch.setattr(bus, "publish_event", _dropped)
    handler = _handler()

    with caplog.at_level("WARNING"):
        await handler.broadcast_approval_status(_session(), "ls -la", approved=True)

    assert "broadcast" in caplog.text.lower()
    assert "ConnectionError" in caplog.text


def test_no_broad_except_exception_remains_in_the_handler():
    """The removal criterion, grepped rather than assumed.

    Four handlers carried `except Exception` — two in broadcast_approval_status,
    one in update_chat_approval_status, one in update_command_queue_status.
    """
    import services.agent_terminal.approval_handler as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    offenders = [
        f"{n}: {line.strip()}"
        for n, line in enumerate(source.splitlines(), 1)
        if re.match(r"^\s*except\s+Exception\b", line)
    ]
    assert not offenders, "a broad handler is back — that is the bug:\n" + "\n".join(offenders)
