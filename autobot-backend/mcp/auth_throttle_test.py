# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the MCP pre-authentication throttle (#13268).

Coverage:
- A run of failed authentications is blocked once the per-IP limit is reached
  (demonstrated by counting attempts, not asserted abstractly)
- Blocking happens BEFORE token validation, so the Redis lookup in
  _validate_redis_token is never reached by a locked-out caller
- Rotating the source IP does not defeat the throttle: the endpoint-wide
  ceiling still trips
- A successful authentication clears the caller's failure record
- The tracked-IP map stays bounded when source addresses are spoofed
- Lockout expires after the configured duration
"""

from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.ssot_config import config
from mcp.auth_throttle import PreAuthThrottle, get_pre_auth_throttle
from mcp.autobot_server import AutoBotMCPServer

TEST_SECRET = "test-mcp-secret"
VALID_TOKEN = f"{TEST_SECRET}:kb,memory,agents"
BAD_TOKEN = "wrong-secret:kb,memory,agents"
CLIENT_IP = "203.0.113.7"


@pytest.fixture(autouse=True)
def _configure_mcp_secret():
    """Configure a secret and reset throttle state between tests."""
    get_pre_auth_throttle().reset()
    with patch.object(config.misc, "mcp_token", TEST_SECRET):
        yield
    get_pre_auth_throttle().reset()


@pytest.fixture(autouse=True)
def _no_redis_fallback():
    """Stop the Redis token fallback from touching a real Redis in unit tests."""
    with patch.object(AutoBotMCPServer, "_validate_redis_token", AsyncMock(return_value=None)):
        yield


def _limits(max_failures=3, window=60, lockout=300, global_max=100, tracked=4096):
    """Patch the env-fed throttle limits to small, fast values."""
    return patch.multiple(
        config.misc,
        mcp_auth_max_failures=max_failures,
        mcp_auth_window_seconds=window,
        mcp_auth_lockout_seconds=lockout,
        mcp_auth_global_max_failures=global_max,
        mcp_auth_max_tracked_ips=tracked,
    )


# ---------------------------------------------------------------------------
# Demonstration: N failed attempts, then blocked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_brute_force_is_blocked_after_configured_attempts():
    """#13268: the Nth+1 guess is throttled, not merely rejected."""
    server = AutoBotMCPServer()
    max_failures = 3

    with _limits(max_failures=max_failures):
        codes = []
        for _ in range(max_failures + 2):
            resp = await server.handle_request("tools/list", {}, BAD_TOKEN, req_id=1, client_ip=CLIENT_IP)
            codes.append(resp["error"]["code"])

    # First `max_failures` guesses are metered auth rejections (-32001);
    # everything after is throttled (-32029) without reaching validation.
    assert codes[:max_failures] == [-32001] * max_failures, codes
    assert codes[max_failures:] == [-32029, -32029], codes


@pytest.mark.asyncio
async def test_throttle_blocks_before_redis_lookup():
    """#13268: a locked-out caller cannot be used as a Redis amplifier."""
    server = AutoBotMCPServer()
    redis_probe = AsyncMock(return_value=None)

    with _limits(max_failures=2), patch.object(AutoBotMCPServer, "_validate_redis_token", redis_probe):
        for _ in range(2):
            await server.handle_request("tools/list", {}, BAD_TOKEN, req_id=1, client_ip=CLIENT_IP)
        calls_before = redis_probe.await_count

        resp = await server.handle_request("tools/list", {}, BAD_TOKEN, req_id=1, client_ip=CLIENT_IP)

    assert resp["error"]["code"] == -32029
    assert redis_probe.await_count == calls_before, "throttled request still reached the Redis fallback"


# ---------------------------------------------------------------------------
# IP rotation resistance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ip_rotation_does_not_defeat_the_throttle():
    """#13268: X-Forwarded-For is caller-controlled behind an appending proxy.

    Every request claims a brand-new source address, so the per-IP counter never
    trips. The endpoint-wide ceiling must still stop the run.
    """
    server = AutoBotMCPServer()
    global_max = 5

    with _limits(max_failures=100, global_max=global_max):
        codes = []
        for i in range(global_max + 2):
            resp = await server.handle_request(
                "tools/list", {}, BAD_TOKEN, req_id=1, client_ip=f"198.51.100.{i}"
            )
            codes.append(resp["error"]["code"])

    assert codes[:global_max] == [-32001] * global_max, codes
    assert codes[global_max:] == [-32029, -32029], codes


def test_tracked_ip_map_stays_bounded():
    """#13268: spoofed source addresses must not grow the tracker without bound."""
    throttle = PreAuthThrottle()
    with _limits(tracked=16, global_max=0, max_failures=100):
        for i in range(200):
            throttle.record_failure(f"198.51.100.{i}")
    assert len(throttle._ips) == 16


# ---------------------------------------------------------------------------
# Success clears state; lockout expires
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_auth_clears_failure_record():
    """A legitimate client that mistypes its token once is not penalised later."""
    server = AutoBotMCPServer()

    with _limits(max_failures=3):
        for _ in range(2):
            await server.handle_request("tools/list", {}, BAD_TOKEN, req_id=1, client_ip=CLIENT_IP)

        ok = await server.handle_request("tools/list", {}, VALID_TOKEN, req_id=1, client_ip=CLIENT_IP)
        assert "result" in ok

        # Budget is reset, so two more failures still do not trip the limit.
        for _ in range(2):
            resp = await server.handle_request("tools/list", {}, BAD_TOKEN, req_id=1, client_ip=CLIENT_IP)
            assert resp["error"]["code"] == -32001


def test_lockout_expires_after_configured_duration():
    """The block lifts once mcp_auth_lockout_seconds has elapsed."""
    throttle = PreAuthThrottle()
    with _limits(max_failures=2, window=60, lockout=300):
        for _ in range(2):
            throttle.record_failure(CLIENT_IP, now=1000.0)

        blocked, reason = throttle.check(CLIENT_IP, now=1001.0)
        assert blocked and reason

        blocked_later, _ = throttle.check(CLIENT_IP, now=1000.0 + 300 + 61)
        assert not blocked_later


def test_check_does_not_consume_budget():
    """check() must be side-effect free so a probe cannot lock a victim out."""
    throttle = PreAuthThrottle()
    with _limits(max_failures=3):
        throttle.record_failure(CLIENT_IP)
        for _ in range(10):
            assert throttle.check(CLIENT_IP)[0] is False
