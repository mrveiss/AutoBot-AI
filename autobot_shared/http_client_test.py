# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for HTTPClientManager.request error-log severity (#9767).

Genuine outbound-call failures must log at ERROR by default; only callers that
opt in (health probes) get the DEBUG downgrade.
"""

import logging
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import aiohttp
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


# ---------------------------------------------------------------------------
# _active_requests must return to baseline after every completed request
# (#12981)
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal ClientResponse stand-in supporting `async with` and json()."""

    def __init__(self, payload=None, status_exc=None):
        self._payload = {"ok": True} if payload is None else payload
        self._status_exc = status_exc
        self.released = False

    def raise_for_status(self):
        """Raise the configured status error, mirroring ClientResponse."""
        if self._status_exc is not None:
            raise self._status_exc

    async def json(self):
        """Return the canned JSON payload."""
        return self._payload

    async def __aenter__(self):
        """Enter the response context."""
        return self

    async def __aexit__(self, *_exc):
        """Mark the connection released on context exit."""
        self.released = True
        return False


@contextmanager
def _patched_client(request_result):
    """Yield the singleton client with its session/pool-adjust patched out.

    ``request_result`` is used as the mocked ``session.request`` side_effect
    when it is an exception, otherwise as its return_value.
    """
    client = HTTPClientManager()
    fake_session = AsyncMock()
    fake_session.closed = False
    if isinstance(request_result, BaseException):
        fake_session.request = AsyncMock(side_effect=request_result)
    else:
        fake_session.request = AsyncMock(return_value=request_result)
    with (
        patch.object(client, "get_session", AsyncMock(return_value=fake_session)),
        patch.object(client, "_adjust_pool_size", AsyncMock(return_value=None)),
    ):
        yield client


@pytest.mark.asyncio
async def test_get_json_returns_counter_to_baseline():
    """A successful get_json() must not leak an active-request slot (#12981)."""
    response = _FakeResponse({"value": 1})
    with _patched_client(response) as client:
        baseline = client._active_requests
        assert await client.get_json("http://svc/data") == {"value": 1}
        assert client._active_requests == baseline
        assert response.released is True


@pytest.mark.asyncio
async def test_post_json_returns_counter_to_baseline():
    """A successful post_json() must not leak an active-request slot (#12981)."""
    response = _FakeResponse({"created": True})
    with _patched_client(response) as client:
        baseline = client._active_requests
        assert await client.post_json("http://svc/submit", {"k": "v"}) == {"created": True}
        assert client._active_requests == baseline


@pytest.mark.asyncio
async def test_failing_request_returns_counter_to_baseline():
    """A transport failure must release the slot before propagating (#12981)."""
    with _patched_client(ConnectionError("boom")) as client:
        baseline = client._active_requests
        with pytest.raises(ConnectionError):
            await client.get_json("http://svc/down")
        assert client._active_requests == baseline


@pytest.mark.asyncio
async def test_raise_for_status_failure_returns_counter_to_baseline():
    """A non-2xx response consumed by get_json() must still release the slot."""
    response = _FakeResponse(status_exc=aiohttp.ClientResponseError(None, (), status=500))
    with _patched_client(response) as client:
        baseline = client._active_requests
        with pytest.raises(aiohttp.ClientResponseError):
            await client.get_json("http://svc/error")
        assert client._active_requests == baseline
        assert response.released is True


@pytest.mark.asyncio
async def test_sequential_requests_do_not_accumulate():
    """N sequential requests must leave the counter at baseline, not baseline+N.

    This is the regression the issue reports: the counter grew monotonically,
    permanently skewing pool utilisation and blocking deferred recreation.
    """
    with _patched_client(_FakeResponse()) as client:
        baseline = client._active_requests
        for _ in range(5):
            await client.get_json("http://svc/data")
        for _ in range(5):
            await client.post_json("http://svc/data", {"k": "v"})
        assert client._active_requests == baseline


@pytest.mark.asyncio
async def test_streaming_contract_unchanged_single_decrement():
    """request() still hands the caller an un-decremented slot (#680 contract).

    The raw-response path stays caller-owned: the slot is held until the
    caller calls decrement_active() exactly once, returning it to baseline.
    """
    with _patched_client(_FakeResponse()) as client:
        baseline = client._active_requests
        response = await client.request("GET", "http://svc/stream")
        try:
            # Still held: pool recreation is correctly deferred mid-stream.
            assert client._active_requests == baseline + 1
        finally:
            async with response:
                pass
            await client.decrement_active()
        assert client._active_requests == baseline


@pytest.mark.asyncio
async def test_tracked_request_decrements_on_caller_exception():
    """tracked_request() is exception-safe: the slot is released on raise."""
    with _patched_client(_FakeResponse()) as client:
        baseline = client._active_requests
        with pytest.raises(RuntimeError):
            async with client.tracked_request("GET", "http://svc/data"):
                assert client._active_requests == baseline + 1
                raise RuntimeError("boom")
        assert client._active_requests == baseline
