# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for HTTPClientManager.request error-log severity (#9767).

Genuine outbound-call failures must log at ERROR by default; only callers that
opt in (health probes) get the DEBUG downgrade.
"""

import logging
from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.http_client import HTTPClientManager


async def _run_request(suppress: bool) -> None:
    client = HTTPClientManager()
    fake_session = AsyncMock()
    fake_session.request = AsyncMock(side_effect=ConnectionError("boom"))
    with (
        patch.object(client, "get_session", AsyncMock(return_value=fake_session)),
        patch.object(client, "_adjust_pool_size", AsyncMock(return_value=None)),
    ):
        with pytest.raises(ConnectionError):
            await client.request("GET", "http://unreachable", suppress_error_log=suppress)


def _failure_records(caplog, level):
    return [r for r in caplog.records if r.levelno == level and "HTTP request failed" in r.getMessage()]


@pytest.mark.asyncio
async def test_request_failure_logs_error_by_default(caplog):
    with caplog.at_level(logging.DEBUG, logger="autobot_shared.http_client"):
        await _run_request(suppress=False)
    assert _failure_records(caplog, logging.ERROR), "default failure must log at ERROR"
    assert not _failure_records(caplog, logging.DEBUG)


@pytest.mark.asyncio
async def test_request_failure_suppressed_logs_debug(caplog):
    with caplog.at_level(logging.DEBUG, logger="autobot_shared.http_client"):
        await _run_request(suppress=True)
    assert _failure_records(caplog, logging.DEBUG), "suppressed failure must log at DEBUG"
    assert not _failure_records(caplog, logging.ERROR)


# ---------------------------------------------------------------------------
# tracked_session() — raw get_session() users must defer pool recreation
# (#11656)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tracked_session_defers_pool_recreation_while_in_flight():
    """A tracked_session() request in flight must NOT have its session closed
    by a concurrent pool-recreation trigger; recreation must defer instead.
    """
    client = HTTPClientManager()
    fake_session = AsyncMock()
    fake_session.closed = False

    orig_session, orig_pending, orig_pool_size = (
        client._session,
        client._pending_pool_recreation,
        client._current_pool_size,
    )
    client._session = fake_session
    try:
        with (
            patch.object(client, "get_session", AsyncMock(return_value=fake_session)),
            patch.object(client, "_create_session", AsyncMock()) as mock_create,
        ):
            async with client.tracked_session() as session:
                assert session is fake_session
                assert client._active_requests == 1

                # Simulate a resize-driven recreation attempt while the
                # tracked raw-session request is still in flight.
                client._current_pool_size = 150
                await client._handle_pool_recreation()

                # Deferred: session must NOT have been closed/recreated,
                # and recreation must be marked pending instead.
                fake_session.close.assert_not_called()
                assert client._pending_pool_recreation is True
                mock_create.assert_not_called()

            # Once the tracked request completes, decrement_active() must
            # apply the deferred recreation.
            assert client._active_requests == 0
            assert client._pending_pool_recreation is False
            mock_create.assert_called_once()
    finally:
        client._session, client._pending_pool_recreation, client._current_pool_size = (
            orig_session,
            orig_pending,
            orig_pool_size,
        )


@pytest.mark.asyncio
async def test_tracked_session_decrements_on_exception():
    """The active-request counter must be decremented even if the caller
    raises inside the `async with` block (exception-safety, #11656).
    """
    client = HTTPClientManager()
    fake_session = AsyncMock()
    fake_session.closed = False

    with patch.object(client, "get_session", AsyncMock(return_value=fake_session)):
        with pytest.raises(RuntimeError):
            async with client.tracked_session():
                assert client._active_requests == 1
                raise RuntimeError("boom")

        assert client._active_requests == 0
