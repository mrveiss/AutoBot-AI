# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
ACP agent surface (#14825).

Drives ``AcpServer`` through a fake transport, so the protocol is exercised end
to end without an LLM or a real editor.  The permission tests deliberately cover
the *denial* paths — an approval gate that only ever gets tested on the approve
branch is not a gate.
"""

from typing import Any, AsyncIterator, Dict, List

import pytest

from acp.protocol import ACP_PROTOCOL_VERSION, AcpErrorCode, StopReason, agent_message_chunk
from acp.server import AcpServer


class FakeTransport:
    """Captures outbound messages and replays a scripted inbound sequence."""

    def __init__(self, inbound: List[Dict[str, Any]] | None = None):
        self.sent: List[Dict[str, Any]] = []
        self._inbound = inbound or []

    async def messages(self) -> AsyncIterator[Dict[str, Any]]:
        for message in self._inbound:
            yield message

    async def send(self, message: Dict[str, Any]) -> None:
        self.sent.append(message)


async def _echo_runner(session_id: str, prompt: str, cwd: str) -> AsyncIterator[Dict[str, Any]]:
    yield agent_message_chunk(session_id, f"echo: {prompt}")


def _results(transport: FakeTransport) -> List[Dict[str, Any]]:
    return [m for m in transport.sent if "result" in m]


def _errors(transport: FakeTransport) -> List[Dict[str, Any]]:
    return [m for m in transport.sent if "error" in m]


def _notifications(transport: FakeTransport, method: str) -> List[Dict[str, Any]]:
    return [m for m in transport.sent if m.get("method") == method]


@pytest.mark.asyncio
async def test_initialize_negotiates_and_advertises_capabilities():
    transport = FakeTransport()
    server = AcpServer(runner=_echo_runner, transport=transport)

    await server._dispatch(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": 1}}
    )

    result = _results(transport)[0]["result"]
    assert result["protocolVersion"] == ACP_PROTOCOL_VERSION
    assert "agentCapabilities" in result


@pytest.mark.asyncio
async def test_initialize_never_claims_a_version_above_its_own():
    """A client asking for v99 must not be told we speak v99."""
    transport = FakeTransport()
    server = AcpServer(runner=_echo_runner, transport=transport)

    await server._dispatch(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": 99}}
    )

    assert _results(transport)[0]["result"]["protocolVersion"] == ACP_PROTOCOL_VERSION


@pytest.mark.asyncio
async def test_capabilities_do_not_advertise_unimplemented_features():
    """An advertised-but-missing capability is worse than an omitted one."""
    from acp.protocol import agent_capabilities

    caps = agent_capabilities()
    assert caps["loadSession"] is False, "loadSession advertised but session/load is not served"


@pytest.mark.asyncio
async def test_methods_before_initialize_are_refused():
    transport = FakeTransport()
    server = AcpServer(runner=_echo_runner, transport=transport)

    await server._dispatch(
        {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": "/tmp"}}
    )

    assert _errors(transport)[0]["error"]["code"] == int(AcpErrorCode.INVALID_REQUEST)


@pytest.mark.asyncio
async def test_session_new_requires_an_absolute_cwd():
    transport = FakeTransport()
    server = AcpServer(runner=_echo_runner, transport=transport)
    server._initialized = True

    await server._dispatch(
        {"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {"cwd": "relative/path"}}
    )

    assert _errors(transport)[0]["error"]["code"] == int(AcpErrorCode.INVALID_PARAMS)


@pytest.mark.asyncio
async def test_full_turn_streams_updates_and_ends():
    transport = FakeTransport()
    server = AcpServer(runner=_echo_runner, transport=transport)

    await server._dispatch({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    await server._dispatch(
        {"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {"cwd": "/work"}}
    )
    session_id = _results(transport)[-1]["result"]["sessionId"]

    await server._dispatch(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "session/prompt",
            "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "hi"}]},
        }
    )

    updates = _notifications(transport, "session/update")
    assert len(updates) == 1
    assert updates[0]["params"]["update"]["content"]["text"] == "echo: hi"
    assert _results(transport)[-1]["result"]["stopReason"] == StopReason.END_TURN.value


@pytest.mark.asyncio
async def test_prompt_for_unknown_session_is_an_error():
    transport = FakeTransport()
    server = AcpServer(runner=_echo_runner, transport=transport)
    server._initialized = True

    await server._dispatch(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "session/prompt",
            "params": {"sessionId": "nope", "prompt": "hi"},
        }
    )

    assert _errors(transport)[0]["error"]["code"] == int(AcpErrorCode.INVALID_PARAMS)


@pytest.mark.asyncio
async def test_unknown_method_returns_method_not_found():
    transport = FakeTransport()
    server = AcpServer(runner=_echo_runner, transport=transport)
    server._initialized = True

    await server._dispatch({"jsonrpc": "2.0", "id": 9, "method": "session/teleport", "params": {}})

    assert _errors(transport)[0]["error"]["code"] == int(AcpErrorCode.METHOD_NOT_FOUND)


@pytest.mark.asyncio
async def test_notification_receives_no_response():
    """A message without an id MUST NOT be answered."""
    transport = FakeTransport()
    server = AcpServer(runner=_echo_runner, transport=transport)
    server._initialized = True

    await server._dispatch({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": "x"}})

    assert transport.sent == [], "a notification was answered"


@pytest.mark.asyncio
async def test_permission_granted_when_client_selects_allow():
    transport = FakeTransport()
    server = AcpServer(runner=_echo_runner, transport=transport)

    import asyncio

    task = asyncio.create_task(server.request_permission("s1", "t1", "Run tests"))
    await asyncio.sleep(0)
    call = [m for m in transport.sent if m.get("method") == "session/request_permission"][0]
    server._resolve_client_call(
        {"id": call["id"], "result": {"outcome": {"outcome": "selected", "optionId": "allow"}}}
    )

    assert await task is True


@pytest.mark.asyncio
async def test_permission_denied_when_client_selects_reject():
    """The denial path — the branch an approval gate exists for."""
    transport = FakeTransport()
    server = AcpServer(runner=_echo_runner, transport=transport)

    import asyncio

    task = asyncio.create_task(server.request_permission("s1", "t1", "Delete everything"))
    await asyncio.sleep(0)
    call = [m for m in transport.sent if m.get("method") == "session/request_permission"][0]
    server._resolve_client_call(
        {"id": call["id"], "result": {"outcome": {"outcome": "selected", "optionId": "reject"}}}
    )

    assert await task is False


@pytest.mark.asyncio
async def test_permission_denied_when_client_cancels():
    transport = FakeTransport()
    server = AcpServer(runner=_echo_runner, transport=transport)

    import asyncio

    task = asyncio.create_task(server.request_permission("s1", "t1", "Run"))
    await asyncio.sleep(0)
    call = [m for m in transport.sent if m.get("method") == "session/request_permission"][0]
    server._resolve_client_call({"id": call["id"], "result": {"outcome": {"outcome": "cancelled"}}})

    assert await task is False


@pytest.mark.asyncio
async def test_permission_denied_when_the_client_errors():
    """An unreadable answer must deny, never fail open."""
    transport = FakeTransport()
    server = AcpServer(runner=_echo_runner, transport=transport)

    import asyncio

    task = asyncio.create_task(server.request_permission("s1", "t1", "Run"))
    await asyncio.sleep(0)
    call = [m for m in transport.sent if m.get("method") == "session/request_permission"][0]
    server._resolve_client_call({"id": call["id"], "error": {"code": -32603, "message": "boom"}})

    assert await task is False


def test_prompt_text_flattens_blocks_and_skips_non_text():
    server = AcpServer(runner=_echo_runner, transport=FakeTransport())

    text = server._prompt_text(
        [
            {"type": "text", "text": "first"},
            {"type": "image", "data": "base64..."},
            {"type": "text", "text": "second"},
        ]
    )

    assert text == "first\nsecond", "a non-text block leaked into the prompt"
