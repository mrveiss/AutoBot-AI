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
    with patch.object(client, "get_session", AsyncMock(return_value=fake_session)), patch.object(
        client, "_adjust_pool_size", AsyncMock(return_value=None)
    ):
        with pytest.raises(ConnectionError):
            await client.request("GET", "http://unreachable", suppress_error_log=suppress)


def _failure_records(caplog, level):
    return [
        r
        for r in caplog.records
        if r.levelno == level and "HTTP request failed" in r.getMessage()
    ]


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
