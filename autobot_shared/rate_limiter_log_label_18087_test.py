# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``RateLimiter.acquire_window`` logs a rejection only when a label is set (#18087)."""

from __future__ import annotations

import logging

import pytest

from autobot_shared.rate_limiter import RateLimiter

CALLER_ID = "alice:203.0.113.9"


def _limiter(allowed: bool, **kwargs) -> RateLimiter:
    lim = RateLimiter("scope-x", **kwargs)

    async def _try(key, max_requests, window_seconds):
        return allowed, 0.0

    lim._try_acquire_window = _try  # type: ignore[assignment]
    return lim


def _warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


@pytest.mark.asyncio
async def test_no_label_means_no_log(caplog):
    with caplog.at_level(logging.DEBUG):
        assert await _limiter(False).acquire_window(CALLER_ID, 5, 60) is False
    assert _warnings(caplog) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("where", ["call", "constructor"])
async def test_label_means_one_warning_without_the_key(caplog, where):
    if where == "call":
        lim, kw = _limiter(False), {"log_label": "lbl"}
    else:
        lim, kw = _limiter(False, log_label="lbl"), {}
    with caplog.at_level(logging.WARNING):
        assert await lim.acquire_window(CALLER_ID, 5, 60, **kw) is False
    assert _warnings(caplog) == ["Rate limit exceeded: lbl over 5 requests/60s"]
    assert CALLER_ID not in caplog.text


@pytest.mark.asyncio
async def test_label_allowed_request_is_silent(caplog):
    with caplog.at_level(logging.DEBUG):
        assert await _limiter(True, log_label="lbl").acquire_window(CALLER_ID, 5, 60) is True
    assert _warnings(caplog) == []
