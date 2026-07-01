# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Tests for ElevationWrapper session-expiry enforcement.

Issue #10723: sessions now expire after a configurable TTL instead of
staying valid indefinitely.  These tests verify that _is_session_valid
correctly gates on the elapsed time, without touching real processes or
the elevation GUI client.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from elevation_wrapper import ElevationWrapper

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wrapper_with_session(elapsed_seconds: float, ttl: int = 900) -> ElevationWrapper:
    """Return an ElevationWrapper whose session is `elapsed_seconds` old."""
    w = ElevationWrapper()
    w.active_session = "tok-test-abc"
    # Back-date the creation timestamp so elapsed time = elapsed_seconds
    w.session_created_at = time.monotonic() - elapsed_seconds
    return w, ttl


# ---------------------------------------------------------------------------
# _is_session_valid
# ---------------------------------------------------------------------------


def test_is_session_valid_no_session():
    """No session → invalid."""
    w = ElevationWrapper()
    assert w._is_session_valid() is False


def test_is_session_valid_token_set_but_no_timestamp():
    """active_session set without session_created_at → invalid (defensive)."""
    w = ElevationWrapper()
    w.active_session = "orphan-token"
    w.session_created_at = None
    assert w._is_session_valid() is False


def test_is_session_valid_within_ttl():
    """Session created 1 s ago with 900 s TTL → valid."""
    ttl = 900
    w, _ = _wrapper_with_session(elapsed_seconds=1, ttl=ttl)
    with patch("elevation_wrapper.config") as mock_cfg:
        mock_cfg.timeout.elevation_session_ttl = ttl
        assert w._is_session_valid() is True


def test_is_session_valid_exactly_at_ttl_boundary():
    """Session elapsed exactly TTL seconds is NOT valid (< not <=)."""
    ttl = 900
    w, _ = _wrapper_with_session(elapsed_seconds=ttl, ttl=ttl)
    with patch("elevation_wrapper.config") as mock_cfg:
        mock_cfg.timeout.elevation_session_ttl = ttl
        assert w._is_session_valid() is False


def test_is_session_valid_expired():
    """Session older than TTL → invalid (the core security fix)."""
    ttl = 900
    w, _ = _wrapper_with_session(elapsed_seconds=ttl + 60, ttl=ttl)
    with patch("elevation_wrapper.config") as mock_cfg:
        mock_cfg.timeout.elevation_session_ttl = ttl
        assert w._is_session_valid() is False


def test_is_session_valid_custom_short_ttl():
    """Custom short TTL (e.g. 60 s) is respected."""
    short_ttl = 60
    w, _ = _wrapper_with_session(elapsed_seconds=61, ttl=short_ttl)
    with patch("elevation_wrapper.config") as mock_cfg:
        mock_cfg.timeout.elevation_session_ttl = short_ttl
        assert w._is_session_valid() is False


def test_is_session_valid_custom_short_ttl_fresh():
    """Custom short TTL with a fresh session → valid."""
    short_ttl = 60
    w, _ = _wrapper_with_session(elapsed_seconds=5, ttl=short_ttl)
    with patch("elevation_wrapper.config") as mock_cfg:
        mock_cfg.timeout.elevation_session_ttl = short_ttl
        assert w._is_session_valid() is True


# ---------------------------------------------------------------------------
# clear_session resets timestamp
# ---------------------------------------------------------------------------


def test_clear_session_resets_timestamp():
    """clear_session must null both active_session and session_created_at."""
    w = ElevationWrapper()
    w.active_session = "tok-xyz"
    w.session_created_at = time.monotonic() - 10

    w.clear_session()

    assert w.active_session is None
    assert w.session_created_at is None
    assert w._is_session_valid() is False


# ---------------------------------------------------------------------------
# _record_session sets timestamp
# ---------------------------------------------------------------------------


def test_record_session_sets_timestamp():
    """_record_session must capture a monotonic timestamp."""
    w = ElevationWrapper()
    before = time.monotonic()
    w._record_session("new-token")
    after = time.monotonic()

    assert w.active_session == "new-token"
    assert w.session_created_at is not None
    assert before <= w.session_created_at <= after


# ---------------------------------------------------------------------------
# execute_command: reuses valid session without re-requesting elevation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_command_reuses_valid_session():
    """execute_command uses the cached session when still valid."""
    client = MagicMock()
    client.execute_elevated_command = AsyncMock(return_value={"success": True, "output": "ok"})
    w = ElevationWrapper(elevation_client=client)

    # Plant a fresh session
    w.active_session = "live-session"
    w.session_created_at = time.monotonic()

    with patch("elevation_wrapper.config") as mock_cfg:
        mock_cfg.timeout.elevation_session_ttl = 900
        result = await w.execute_command("systemctl restart myservice")

    client.execute_elevated_command.assert_called_once()
    assert result["success"] is True


@pytest.mark.asyncio
async def test_execute_command_rejects_expired_session():
    """execute_command does NOT reuse an expired session."""
    w = ElevationWrapper()  # no client → "needs_elevation" path
    w.active_session = "stale-session"
    w.session_created_at = time.monotonic() - 1000  # clearly expired

    with patch("elevation_wrapper.config") as mock_cfg:
        mock_cfg.timeout.elevation_session_ttl = 900
        result = await w.execute_command("systemctl restart myservice")

    # No client configured → falls through to "needs_elevation" error
    assert result["success"] is False
    assert result.get("needs_elevation") is True
