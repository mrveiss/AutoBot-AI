# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration tests for the openai_compat rate-limit wiring (#7271).

Per-IP rate-limit logic itself lives in
``autobot_shared.rate_limit.IPRateLimiter`` and is comprehensively tested
in ``autobot_shared/rate_limit_test.py`` (covers Redis path, in-process
fallback, env-driven limit, etc.).

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
from autobot_shared.rate_limit import IPRateLimiter


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

        asyncio.get_event_loop().run_until_complete(run())

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

        asyncio.get_event_loop().run_until_complete(run())

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

        asyncio.get_event_loop().run_until_complete(run())


class TestOAIRateLimitWiring:
    """Issue #7271: openai_compat uses the shared IPRateLimiter."""

    def test_module_exposes_limiter_instance(self):
        """``_oai_limiter`` must be an IPRateLimiter (not the legacy func)."""
        assert isinstance(openai_compat._oai_limiter, IPRateLimiter)

    def test_limiter_uses_oai_specific_config(self):
        """The instance is configured for the /v1/chat/completions endpoint."""
        limiter = openai_compat._oai_limiter
        # #6588 / #7271: prefix shared across uvicorn workers via Redis key.
        assert limiter._key_prefix == "ratelimit:oai"
        # AUTOBOT_OAI_RATE_LIMIT env var; default 60/min preserved.
        assert limiter._limit_env == "AUTOBOT_OAI_RATE_LIMIT"
        assert limiter._default_limit == 60
        assert limiter._window_seconds == 60
