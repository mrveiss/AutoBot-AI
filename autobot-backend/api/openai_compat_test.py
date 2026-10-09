# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Integration tests for the openai_compat rate-limit wiring (#7271).

Per-IP rate-limit logic itself lives in the canonical
``autobot_shared.rate_limiter.RateLimiter`` (single-window mode, #18087) and
is tested in ``autobot_shared/rate_limiter_window_18087_test.py``.

This file pins the openai_compat-specific configuration of that helper:
the right key prefix, the right env var, and that the helper is the same
instance referenced by the request handler.

Pre-#7271 this file tested the standalone ``_check_oai_rate_limit``
function shipped in #6588. That function was extracted into the shared
helper, so the tests are now at the helper-level and the integration
tests below pin the per-endpoint configuration.
"""

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api import openai_compat
from autobot_shared.rate_limiter_window import WindowFailurePolicy, WindowQuota


# #13113: asyncio.run() — pytest-asyncio owns the loop lifecycle, so a sync test
# running before any async test on its worker had no current loop for get_event_loop().
class TestGetUserAsync:
    """MVA-169: _get_user must be async and await get_current_user."""

    def test_get_user_is_coroutine_function(self):
        assert inspect.iscoroutinefunction(openai_compat._get_user)

    def test_get_user_awaits_get_current_user(self):
        fake_request = MagicMock()
        fake_user = {"id": "u1", "email": "test@example.com"}

        async def run():
            with patch(
                "api.openai_compat.get_current_user", new_callable=AsyncMock, return_value=fake_user
            ) as mock_gcu:
                result = await openai_compat._get_user(fake_request)
                mock_gcu.assert_awaited_once_with(fake_request)
                assert result == fake_user

        asyncio.run(run())

    def test_get_user_propagates_http_exception(self):
        fake_request = MagicMock()

        async def run():
            with patch(
                "api.openai_compat.get_current_user",
                new_callable=AsyncMock,
                side_effect=HTTPException(status_code=401, detail="Unauthorized"),
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await openai_compat._get_user(fake_request)
                assert exc_info.value.status_code == 401

        asyncio.run(run())

    def test_get_user_converts_unexpected_exception_to_401(self):
        fake_request = MagicMock()

        async def run():
            with patch(
                "api.openai_compat.get_current_user",
                new_callable=AsyncMock,
                side_effect=RuntimeError("jwt decode failed"),
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await openai_compat._get_user(fake_request)
                assert exc_info.value.status_code == 401
                assert exc_info.value.detail == "Unauthorized"

        asyncio.run(run())


class TestOAIRateLimitWiring:
    """Issue #7271/#18087: openai_compat uses the canonical window limiter."""

    def test_module_exposes_limiter_instance(self):
        """``_oai_limiter`` must be a WindowQuota (not the legacy func)."""
        assert isinstance(openai_compat._oai_limiter, WindowQuota)

    def test_limiter_uses_oai_specific_config(self):
        """The instance is configured for the /v1/chat/completions endpoint."""
        quota = openai_compat._oai_limiter
        # #6588 / #7271: scope shared across uvicorn workers via the Redis key.
        assert quota.limiter._prefix == "oai"
        # AUTOBOT_OAI_RATE_LIMIT env var; default 60/min preserved.
        assert quota._limit_env == "AUTOBOT_OAI_RATE_LIMIT"
        assert quota._default_max == 60
        assert quota.window_seconds == 60

    def test_public_endpoint_keeps_enforcing_when_redis_is_down(self):
        """The old per-IP limiter fell back to a per-worker bucket, never open."""
        assert openai_compat._oai_limiter.limiter._window_policy is WindowFailurePolicy.LOCAL
