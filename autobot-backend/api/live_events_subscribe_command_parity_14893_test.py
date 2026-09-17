# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Subscribe/command authorization parity (#14893).

``_handle_subscribe`` used to carry its own inline copy of the per-prefix
authorization rules, separate from ``_authorize_channel`` -- the function
``_handle_command``/``dispatch_command`` uses to gate the command path. The
two drifted within a single commit (#14826 tightened ``_authorize_channel``'s
unknown-prefix default to deny; the inline copy in ``_handle_subscribe``
stayed default-allow).

These tests pin that ``_handle_subscribe`` has no rules of its own: whatever
``_authorize_channel`` decides for a (channel, user) pair is exactly what
subscribe does, for every prefix that resolves without a DB-backed session
(the company/board/session/chat/workflow/heartbeat/task prefixes are already
covered by test_live_events_authz.py and live_events_authz_review_test.py) and
for an unrecognised prefix -- so a future change to the shared function cannot
silently apply to only one of the two paths again.
"""

from unittest.mock import AsyncMock, patch

import pytest

from api.live_events import _authorize_channel, _handle_subscribe

_USER = {"user_id": "u1", "username": "alice", "roles": []}
_ADMIN = {"user_id": "u2", "username": "root", "roles": ["admin"]}


async def _subscribe_outcome(channel: str, user_payload: dict | None) -> bool:
    """True if _handle_subscribe let the subscription through to the bus."""
    ws = AsyncMock()
    bus = AsyncMock()
    bus.subscribe_ws.return_value = True
    with patch("api.live_events.get_event_bus", return_value=bus):
        await _handle_subscribe(ws, channel, user_payload)
    return bool(bus.subscribe_ws.called)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "channel,user_payload",
    [
        ("agent:u1", _USER),
        ("agent:someone-else", _USER),
        ("agent:u1", _ADMIN),
        ("global", _USER),
        ("research:abc", _USER),
        ("research:abc", _ADMIN),
        ("nocolon", _USER),
        ("", _USER),
    ],
)
async def test_subscribe_matches_authorize_channel_verdict(channel, user_payload):
    expected = await _authorize_channel(channel, user_payload)
    actual = await _subscribe_outcome(channel, user_payload)
    assert actual == expected


@pytest.mark.asyncio
async def test_subscribe_denies_an_unrecognised_prefix_without_reaching_the_bus():
    """AC3: denied independently of subscribe_ws/_is_valid_channel -- the bus is
    never asked about a channel _authorize_channel already refused.
    """
    ws = AsyncMock()
    bus = AsyncMock()
    with patch("api.live_events.get_event_bus", return_value=bus):
        await _handle_subscribe(ws, "research:abc", _USER)
    bus.subscribe_ws.assert_not_called()
    ws.send_json.assert_awaited_once()
    sent = ws.send_json.await_args.args[0]
    assert sent["type"] == "error"


@pytest.mark.asyncio
async def test_subscribe_calls_the_shared_authorization_function():
    """AC1 directly: _handle_subscribe has no rules of its own -- it asks
    _authorize_channel, with the exact (channel, user_payload) it received,
    and only _authorize_channel.
    """
    ws = AsyncMock()
    bus = AsyncMock()
    bus.subscribe_ws.return_value = True
    with (
        patch("api.live_events.get_event_bus", return_value=bus),
        patch("api.live_events._authorize_channel", AsyncMock(return_value=True)) as mock_authz,
    ):
        await _handle_subscribe(ws, "whatever:1", _USER)
    mock_authz.assert_awaited_once_with("whatever:1", _USER)
