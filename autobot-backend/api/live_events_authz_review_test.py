# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Channel authorization defaults (review finding, #14819/#14824).

``_authorize_channel`` used to end in ``return True``. That was survivable while
the socket was subscribe-only — every valid prefix has an explicit rule, so
nothing reached data unchecked — but it stopped being survivable once
``dispatch_command`` adopted the same function as the only gate on a *write*
path. A handler registered for a new prefix would have been reachable by any
connected client with no check at all.

The invariant these pin: an unrecognised channel is DENIED, so a new channel
type is inert until someone writes its rule.
"""

import pytest

from api.live_events import _authorize_channel

_USER = {"user_id": "u1", "username": "alice", "roles": []}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "channel",
    [
        "research:abc",
        "operation:1",
        "metrics:cpu",
        "admin:secrets",
        "x-custom:1",
        "nocolon",
        "",
    ],
)
async def test_an_unrecognised_channel_is_denied(channel):
    assert await _authorize_channel(channel, _USER) is False


@pytest.mark.asyncio
async def test_global_remains_readable_by_an_authenticated_client():
    # The shared broadcast channel carries no per-tenant payload and every
    # authenticated client is meant to see it. Default-deny must not break it.
    assert await _authorize_channel("global", _USER) is True


@pytest.mark.asyncio
async def test_a_users_own_agent_channel_is_allowed():
    assert await _authorize_channel("agent:u1", _USER) is True


@pytest.mark.asyncio
async def test_another_users_agent_channel_is_denied():
    assert await _authorize_channel("agent:someone-else", _USER) is False


@pytest.mark.asyncio
async def test_an_admin_may_reach_another_users_agent_channel():
    admin = {"user_id": "u2", "username": "root", "roles": ["admin"]}
    assert await _authorize_channel("agent:u1", admin) is True


@pytest.mark.asyncio
async def test_an_admin_is_still_denied_an_unrecognised_prefix():
    # Admin bypass lives inside each prefix's rule, not in the default arm —
    # an unknown channel has no rule to bypass.
    admin = {"user_id": "u2", "username": "root", "roles": ["admin"]}
    assert await _authorize_channel("research:abc", admin) is False
