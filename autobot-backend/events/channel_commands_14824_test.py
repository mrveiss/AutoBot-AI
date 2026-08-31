# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Channel command dispatch (#14824).

Route consolidation needs a client-to-server path on the channel socket, and the
property that matters most is that it cannot become a weaker door than
``subscribe``.  These tests pin the refusal branches — unauthorized, unknown
handler, malformed, handler raising — because a dispatch that silently no-ops on
refusal reads to the caller exactly like success.
"""

import pytest

from events.channel_commands import (
    ChannelCommandRegistry,
    CommandRefused,
    dispatch_command,
    get_channel_command_registry,
)


async def _allow(_channel, _user):
    return True


async def _deny(_channel, _user):
    return False


@pytest.fixture(autouse=True)
def clean_registry():
    """Keep the process-wide registry from leaking between tests."""
    registry = get_channel_command_registry()
    saved = dict(registry._handlers)
    registry._handlers.clear()
    yield registry
    registry._handlers.clear()
    registry._handlers.update(saved)


@pytest.mark.asyncio
async def test_command_reaches_the_handler_for_its_prefix(clean_registry):
    seen = {}

    async def handler(channel, command, payload, user):
        seen.update({"channel": channel, "command": command, "payload": payload})
        return {"ok": True}

    clean_registry.register("operation", handler)

    result = await dispatch_command("operation:42", "pause", {"why": "test"}, None, _allow)

    assert result == {"ok": True}
    assert seen["channel"] == "operation:42"
    assert seen["command"] == "pause"
    assert seen["payload"] == {"why": "test"}


@pytest.mark.asyncio
async def test_unauthorized_caller_is_refused(clean_registry):
    """The load-bearing case: commands must not bypass channel authorization."""
    called = False

    async def handler(channel, command, payload, user):
        nonlocal called
        called = True
        return {}

    clean_registry.register("operation", handler)

    with pytest.raises(CommandRefused):
        await dispatch_command("operation:42", "pause", {}, {"user_id": "u1"}, _deny)

    assert called is False, "handler ran despite authorization failing"


@pytest.mark.asyncio
async def test_authorization_is_checked_before_handler_lookup(clean_registry):
    """Whether a handler exists is itself information; deny first."""
    with pytest.raises(CommandRefused) as exc:
        await dispatch_command("secret:1", "peek", {}, {"user_id": "u1"}, _deny)

    assert "Not authorized" in exc.value.reason
    assert "No command handler" not in exc.value.reason


@pytest.mark.asyncio
async def test_unknown_prefix_is_refused(clean_registry):
    with pytest.raises(CommandRefused) as exc:
        await dispatch_command("nosuch:1", "go", {}, None, _allow)

    assert "No command handler" in exc.value.reason


@pytest.mark.asyncio
async def test_missing_channel_or_command_is_refused(clean_registry):
    with pytest.raises(CommandRefused):
        await dispatch_command("", "go", {}, None, _allow)
    with pytest.raises(CommandRefused):
        await dispatch_command("operation:1", "", {}, None, _allow)


@pytest.mark.asyncio
async def test_handler_exception_becomes_a_refusal_not_a_crash(clean_registry):
    async def boom(channel, command, payload, user):
        raise RuntimeError("handler exploded")

    clean_registry.register("operation", boom)

    with pytest.raises(CommandRefused) as exc:
        await dispatch_command("operation:1", "go", {}, None, _allow)

    assert "Command failed" in exc.value.reason


@pytest.mark.asyncio
async def test_handler_may_refuse_explicitly(clean_registry):
    async def picky(channel, command, payload, user):
        raise CommandRefused("operation already finished")

    clean_registry.register("operation", picky)

    with pytest.raises(CommandRefused) as exc:
        await dispatch_command("operation:1", "pause", {}, None, _allow)

    # The handler's own reason must survive, not be flattened into a generic one.
    assert exc.value.reason == "operation already finished"


def test_registry_resolves_by_prefix_only():
    registry = ChannelCommandRegistry()

    async def handler(channel, command, payload, user):
        return None

    registry.register("process", handler)

    assert registry.handler_for("process:abc") is handler
    assert registry.handler_for("process:other") is handler
    assert registry.handler_for("processx:abc") is None
