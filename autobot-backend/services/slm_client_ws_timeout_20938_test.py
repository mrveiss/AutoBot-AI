# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A WebSocket handshake timeout is an expected transient: counted, quiet, and backed off (#20938)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.slm_client import _WS_AUTH_FAIL_THRESHOLD, SLMClient

pytestmark = pytest.mark.usefixtures("slm_egress_open")  # subject is failure accounting, not egress

_SIGNER = "services.slm_client._get_slm_signing_secret"
_CONNECT = "services.slm_client.connect_no_redirect"
_KEY = "unit-test-signing-key-0123456789abcdef"  # pragma: allowlist secret


def _failing_opener(exc: BaseException) -> MagicMock:
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(side_effect=exc)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


async def _connect_once(client: SLMClient, exc: BaseException) -> MagicMock:
    with (
        patch(_SIGNER, return_value=_KEY),
        patch(_CONNECT, side_effect=lambda url, **kw: _failing_opener(exc)),
        patch("services.slm_client.logger") as log,
    ):
        await client._ws_connect_and_listen()
    return log


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", [TimeoutError("timed out during opening handshake"), ConnectionRefusedError("refused")])
async def test_connect_time_oserror_is_counted_and_not_logged_as_error(exc: OSError) -> None:
    client = SLMClient(slm_url="http://autobot-slm:8000")
    log = await _connect_once(client, exc)
    assert client._ws_auth_fail_count == 1
    assert client._ws_connected is False
    log.error.assert_not_called()
    log.warning.assert_called_once()


@pytest.mark.asyncio
async def test_genuinely_unexpected_exception_still_logs_error_and_is_not_counted() -> None:
    client = SLMClient(slm_url="http://autobot-slm:8000")
    log = await _connect_once(client, ValueError("bug"))
    assert client._ws_auth_fail_count == 0
    log.error.assert_called_once()


@pytest.mark.asyncio
async def test_repeated_timeouts_warn_once_then_wait_the_pinned_delay() -> None:
    """Through the real _ws_listener: the shared backoff doubles, then pins at the max after the threshold."""
    client = SLMClient(slm_url="http://autobot-slm:8000")
    slept: list[float] = []

    async def fake_sleep(delay: float) -> None:
        slept.append(delay)
        if len(slept) > _WS_AUTH_FAIL_THRESHOLD:
            client._shutdown = True

    with (
        patch(_SIGNER, return_value=_KEY),
        patch(
            _CONNECT, side_effect=lambda url, **kw: _failing_opener(TimeoutError("timed out during opening handshake"))
        ),
        patch("asyncio.sleep", side_effect=fake_sleep),
        patch("services.slm_client.logger") as log,
    ):
        await client._ws_listener()

    log.error.assert_not_called()
    threshold_warnings = [c for c in log.warning.call_args_list if "consecutive times" in c.args[0]]
    assert len(threshold_warnings) == 1
    # failures 1 and 2 back off 1s then 2s; the 3rd pins the delay at the maximum
    assert slept[:_WS_AUTH_FAIL_THRESHOLD] == [1.0, 2.0, client._max_reconnect_delay]
