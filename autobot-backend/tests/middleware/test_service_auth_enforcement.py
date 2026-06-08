# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for ServiceAuth enforcement middleware (#3394).

Covers:
  - is_path_exempt / requires_service_auth path matching
  - get_enforcement_mode env-var toggle
  - _should_enforce_by_circuit_breaker percentage logic
  - _is_rate_limited / _record_failed_auth sliding window
  - _has_override_token constant-time comparison
  - get_endpoint_categories summary dict
  - enforce_service_auth: exempt path passthrough, blocked path rejection,
    circuit-breaker bypass, override-token bypass
  - enforcement mode gating: logging vs enforcement mode behavior
"""

import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from middleware.service_auth_enforcement import (
    EXEMPT_PATHS,
    SERVICE_ONLY_PATHS,
    _failed_auth_tracker,
    _has_override_token,
    _is_rate_limited,
    _record_failed_auth,
    _should_enforce_by_circuit_breaker,
    enforce_service_auth,
    get_endpoint_categories,
    get_enforcement_mode,
    is_path_exempt,
    requires_service_auth,
)

# ---------------------------------------------------------------------------
# Path matching
# ---------------------------------------------------------------------------


class TestIsPathExempt:
    def test_health_path_is_exempt(self):
        assert is_path_exempt("/health") is True

    def test_api_health_is_exempt(self):
        assert is_path_exempt("/api/health") is True

    def test_docs_is_exempt(self):
        assert is_path_exempt("/docs/intro") is True

    def test_openapi_is_exempt(self):
        assert is_path_exempt("/openapi.json") is True

    def test_api_chat_is_exempt(self):
        assert is_path_exempt("/api/chats/abc123") is True

    def test_api_knowledge_is_exempt(self):
        assert is_path_exempt("/api/knowledge/items") is True

    def test_service_only_path_is_not_exempt(self):
        assert is_path_exempt("/api/npu/results") is False

    def test_unknown_path_is_not_exempt(self):
        assert is_path_exempt("/api/unknown/route") is False


class TestRequiresServiceAuth:
    def test_npu_results_requires_auth(self):
        assert requires_service_auth("/api/npu/results") is True

    def test_browser_screenshots_requires_auth(self):
        assert requires_service_auth("/api/browser/screenshots") is True

    def test_internal_path_requires_auth(self):
        assert requires_service_auth("/api/internal/sync") is True

    def test_ai_stack_heartbeat_requires_auth(self):
        assert requires_service_auth("/api/ai-stack/heartbeat") is True

    def test_exempt_path_does_not_require_auth(self):
        assert requires_service_auth("/api/chats") is False

    def test_unknown_path_does_not_require_auth(self):
        assert requires_service_auth("/api/unknown") is False


# ---------------------------------------------------------------------------
# Environment flag helpers
# ---------------------------------------------------------------------------


class TestGetEnforcementMode:
    def test_false_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SERVICE_AUTH_ENFORCEMENT_MODE", None)
            assert get_enforcement_mode() is False

    def test_true_when_set(self):
        with patch.dict(os.environ, {"SERVICE_AUTH_ENFORCEMENT_MODE": "true"}):
            assert get_enforcement_mode() is True

    def test_case_insensitive_true(self):
        with patch.dict(os.environ, {"SERVICE_AUTH_ENFORCEMENT_MODE": "TRUE"}):
            assert get_enforcement_mode() is True

    def test_false_for_other_values(self):
        with patch.dict(os.environ, {"SERVICE_AUTH_ENFORCEMENT_MODE": "1"}):
            assert get_enforcement_mode() is False


class TestCircuitBreaker:
    def test_full_enforcement_at_100_percent(self):
        with patch.dict(os.environ, {"SERVICE_AUTH_CIRCUIT_BREAKER_PERCENTAGE": "100"}):
            assert _should_enforce_by_circuit_breaker() is True

    def test_no_enforcement_at_0_percent(self):
        with patch.dict(os.environ, {"SERVICE_AUTH_CIRCUIT_BREAKER_PERCENTAGE": "0"}):
            assert _should_enforce_by_circuit_breaker() is False

    def test_probabilistic_at_50_percent(self):
        with patch.dict(os.environ, {"SERVICE_AUTH_CIRCUIT_BREAKER_PERCENTAGE": "50"}):
            results = {_should_enforce_by_circuit_breaker() for _ in range(200)}
            assert True in results and False in results


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class TestRateLimiting:
    def setup_method(self):
        """Clear tracker before each test."""
        _failed_auth_tracker.clear()

    def test_not_rate_limited_initially(self):
        assert _is_rate_limited("1.2.3.4") is False

    def test_rate_limited_after_max_failures(self):
        with patch.dict(
            os.environ,
            {
                "SERVICE_AUTH_RATE_LIMIT_WINDOW": "300",
                "SERVICE_AUTH_RATE_LIMIT_MAX_FAILURES": "3",
            },
        ):
            for _ in range(3):
                _record_failed_auth("10.0.0.1")
            assert _is_rate_limited("10.0.0.1") is True

    def test_expired_failures_pruned(self):
        with patch.dict(
            os.environ,
            {
                "SERVICE_AUTH_RATE_LIMIT_WINDOW": "1",
                "SERVICE_AUTH_RATE_LIMIT_MAX_FAILURES": "2",
            },
        ):
            _failed_auth_tracker["5.5.5.5"] = [time.time() - 10]  # expired
            assert _is_rate_limited("5.5.5.5") is False

    def test_different_ips_tracked_independently(self):
        with patch.dict(
            os.environ,
            {
                "SERVICE_AUTH_RATE_LIMIT_WINDOW": "300",
                "SERVICE_AUTH_RATE_LIMIT_MAX_FAILURES": "2",
            },
        ):
            for _ in range(2):
                _record_failed_auth("192.168.1.1")
            assert _is_rate_limited("192.168.1.1") is True
            assert _is_rate_limited("192.168.1.2") is False


# ---------------------------------------------------------------------------
# Override token
# ---------------------------------------------------------------------------


class TestHasOverrideToken:
    def _make_request(self, token_value: str) -> MagicMock:
        req = MagicMock()
        req.headers = {"X-Override-Token": token_value}
        return req

    def test_correct_token_returns_true(self):
        with patch.dict(os.environ, {"SERVICE_AUTH_OVERRIDE_TOKEN": "super-secret-token"}):
            req = self._make_request("super-secret-token")
            assert _has_override_token(req) is True

    def test_wrong_token_returns_false(self):
        with patch.dict(os.environ, {"SERVICE_AUTH_OVERRIDE_TOKEN": "super-secret-token"}):
            req = self._make_request("wrong-token")
            assert _has_override_token(req) is False

    def test_no_env_token_returns_false(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SERVICE_AUTH_OVERRIDE_TOKEN", None)
            req = self._make_request("anything")
            assert _has_override_token(req) is False

    def test_missing_header_returns_false(self):
        with patch.dict(os.environ, {"SERVICE_AUTH_OVERRIDE_TOKEN": "super-secret-token"}):
            req = MagicMock()
            req.headers = {}
            req.headers.get = lambda k, d=None: d
            assert _has_override_token(req) is False


# ---------------------------------------------------------------------------
# get_endpoint_categories
# ---------------------------------------------------------------------------


class TestGetEndpointCategories:
    def test_contains_expected_keys(self):
        cats = get_endpoint_categories()
        assert "enforcement_mode" in cats
        assert "exempt_paths" in cats
        assert "service_only_paths" in cats
        assert "total_exempt" in cats
        assert "total_service_only" in cats

    def test_path_counts_match_lists(self):
        cats = get_endpoint_categories()
        assert cats["total_exempt"] == len(EXEMPT_PATHS)
        assert cats["total_service_only"] == len(SERVICE_ONLY_PATHS)


# ---------------------------------------------------------------------------
# enforce_service_auth integration
# ---------------------------------------------------------------------------


def _make_request(path: str, ip: str = "10.0.0.99") -> MagicMock:
    """Build a minimal mock FastAPI Request."""
    req = MagicMock()
    req.url.path = path
    req.method = "GET"
    req.client = MagicMock()
    req.client.host = ip
    req.headers = {}
    req.headers.get = lambda k, d=None: d
    req.state = MagicMock()
    return req


class TestEnforceServiceAuth:
    """Integration-level tests for the enforce_service_auth middleware function.

    All tests that check blocking behavior explicitly set SERVICE_AUTH_ENFORCEMENT_MODE=true.
    See TestEnforcementModeGating for logging-vs-enforcement mode tests.
    """

    @pytest.mark.asyncio
    async def test_exempt_path_passes_through(self):
        """Requests to exempt paths must never be blocked."""
        call_next = AsyncMock(return_value="ok-response")
        req = _make_request("/api/chats/123")
        result = await enforce_service_auth(req, call_next)
        call_next.assert_awaited_once_with(req)
        assert result == "ok-response"

    @pytest.mark.asyncio
    async def test_unknown_path_passes_through(self):
        """Paths that are neither exempt nor service-only pass without auth check."""
        call_next = AsyncMock(return_value="ok-response")
        req = _make_request("/api/unknown")
        await enforce_service_auth(req, call_next)
        call_next.assert_awaited_once_with(req)

    @pytest.mark.asyncio
    async def test_service_path_blocked_without_auth(self):
        """Service-only paths must return 401 when auth headers are absent."""
        from fastapi import HTTPException
        from fastapi.responses import JSONResponse

        call_next = AsyncMock(return_value="should-not-reach")

        with (
            patch.dict(os.environ, {"SERVICE_AUTH_ENFORCEMENT_MODE": "true"}),
            patch(
                "middleware.service_auth_enforcement._should_enforce_by_circuit_breaker",
                return_value=True,
            ),
            patch(
                "middleware.service_auth_enforcement._is_rate_limited",
                return_value=False,
            ),
            patch(
                "middleware.service_auth_enforcement.validate_service_auth",
                side_effect=HTTPException(status_code=401, detail="Missing required headers"),
            ),
        ):
            req = _make_request("/api/npu/results")
            result = await enforce_service_auth(req, call_next)

        assert isinstance(result, JSONResponse)
        assert result.status_code == 401
        call_next.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_service_path_allowed_with_valid_auth(self):
        """Service-only paths pass when validate_service_auth succeeds."""
        call_next = AsyncMock(return_value="auth-ok-response")

        with (
            patch.dict(os.environ, {"SERVICE_AUTH_ENFORCEMENT_MODE": "true"}),
            patch(
                "middleware.service_auth_enforcement._should_enforce_by_circuit_breaker",
                return_value=True,
            ),
            patch(
                "middleware.service_auth_enforcement._is_rate_limited",
                return_value=False,
            ),
            patch(
                "middleware.service_auth_enforcement.validate_service_auth",
                return_value={"service_id": "npu-worker", "authenticated": True},
            ),
        ):
            req = _make_request("/api/npu/results")
            result = await enforce_service_auth(req, call_next)

        call_next.assert_awaited_once_with(req)
        assert result == "auth-ok-response"

    @pytest.mark.asyncio
    async def test_circuit_breaker_bypass_allows_request(self):
        """When circuit breaker returns False, request is allowed without auth."""
        call_next = AsyncMock(return_value="circuit-bypass")

        with (
            patch.dict(os.environ, {"SERVICE_AUTH_ENFORCEMENT_MODE": "true"}),
            patch(
                "middleware.service_auth_enforcement._should_enforce_by_circuit_breaker",
                return_value=False,
            ),
        ):
            req = _make_request("/api/internal/sync")
            await enforce_service_auth(req, call_next)

        call_next.assert_awaited_once_with(req)

    @pytest.mark.asyncio
    async def test_override_token_bypasses_auth(self):
        """Valid override token skips auth validation entirely."""
        call_next = AsyncMock(return_value="override-ok")

        with (
            patch.dict(
                os.environ,
                {
                    "SERVICE_AUTH_OVERRIDE_TOKEN": "emergency-token",
                    "SERVICE_AUTH_ENFORCEMENT_MODE": "true",
                },
            ),
            patch(
                "middleware.service_auth_enforcement._should_enforce_by_circuit_breaker",
                return_value=True,
            ),
            patch(
                "middleware.service_auth_enforcement._is_rate_limited",
                return_value=False,
            ),
        ):
            req = _make_request("/api/npu/heartbeat")
            req.headers = {"X-Override-Token": "emergency-token"}
            req.headers.get = lambda k, d=None: {"X-Override-Token": "emergency-token"}.get(k, d)

            await enforce_service_auth(req, call_next)

        call_next.assert_awaited_once_with(req)

    @pytest.mark.asyncio
    async def test_rate_limited_ip_returns_429(self):
        """IP that exceeds failure threshold receives 429 before auth attempt."""
        from fastapi.responses import JSONResponse

        call_next = AsyncMock(return_value="should-not-reach")

        with (
            patch.dict(os.environ, {"SERVICE_AUTH_ENFORCEMENT_MODE": "true"}),
            patch(
                "middleware.service_auth_enforcement._should_enforce_by_circuit_breaker",
                return_value=True,
            ),
            patch(
                "middleware.service_auth_enforcement._is_rate_limited",
                return_value=True,
            ),
        ):
            req = _make_request("/api/browser/results")
            result = await enforce_service_auth(req, call_next)

        assert isinstance(result, JSONResponse)
        assert result.status_code == 429
        call_next.assert_not_awaited()


# ---------------------------------------------------------------------------
# Enforcement mode gating (SERVICE_AUTH_ENFORCEMENT_MODE env var)
# ---------------------------------------------------------------------------


class TestEnforcementModeGating:
    """Verify that SERVICE_AUTH_ENFORCEMENT_MODE controls enforce-vs-log behaviour."""

    @pytest.mark.asyncio
    async def test_logging_mode_allows_request_with_invalid_auth(self):
        """When enforcement mode is disabled, bad auth is logged but not blocked."""
        from fastapi import HTTPException

        call_next = AsyncMock(return_value="logging-mode-response")

        with (
            patch.dict(os.environ, {"SERVICE_AUTH_ENFORCEMENT_MODE": "false"}),
            patch(
                "middleware.service_auth_enforcement.validate_service_auth",
                side_effect=HTTPException(status_code=401, detail="Missing required headers"),
            ),
        ):
            req = _make_request("/api/npu/results")
            result = await enforce_service_auth(req, call_next)

        call_next.assert_awaited_once_with(req)
        assert result == "logging-mode-response"

    @pytest.mark.asyncio
    async def test_enforcement_mode_blocks_invalid_auth(self):
        """When enforcement mode is enabled, bad auth returns 401."""
        from fastapi import HTTPException
        from fastapi.responses import JSONResponse

        call_next = AsyncMock(return_value="should-not-reach")

        with (
            patch.dict(os.environ, {"SERVICE_AUTH_ENFORCEMENT_MODE": "true"}),
            patch(
                "middleware.service_auth_enforcement._should_enforce_by_circuit_breaker",
                return_value=True,
            ),
            patch(
                "middleware.service_auth_enforcement._is_rate_limited",
                return_value=False,
            ),
            patch(
                "middleware.service_auth_enforcement.validate_service_auth",
                side_effect=HTTPException(status_code=401, detail="Missing required headers"),
            ),
        ):
            req = _make_request("/api/npu/results")
            result = await enforce_service_auth(req, call_next)

        assert isinstance(result, JSONResponse)
        assert result.status_code == 401
        call_next.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_logging_mode_records_valid_auth(self):
        """In logging mode, valid auth is recorded on request.state without blocking."""
        call_next = AsyncMock(return_value="ok")

        with (
            patch.dict(os.environ, {"SERVICE_AUTH_ENFORCEMENT_MODE": "false"}),
            patch(
                "middleware.service_auth_enforcement.validate_service_auth",
                return_value={"service_id": "npu-worker", "authenticated": True},
            ),
        ):
            req = _make_request("/api/npu/heartbeat")
            result = await enforce_service_auth(req, call_next)

        call_next.assert_awaited_once_with(req)
        assert req.state.service_id == "npu-worker"
        assert req.state.authenticated is True
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_enforcement_mode_default_is_false(self):
        """Without SERVICE_AUTH_ENFORCEMENT_MODE set, enforcement is disabled."""
        from fastapi import HTTPException

        call_next = AsyncMock(return_value="default-mode-ok")

        with patch.dict(os.environ, {}, clear=False) as env:
            env.pop("SERVICE_AUTH_ENFORCEMENT_MODE", None)
            with patch(
                "middleware.service_auth_enforcement.validate_service_auth",
                side_effect=HTTPException(status_code=401, detail="Missing required headers"),
            ):
                req = _make_request("/api/npu/results")
                result = await enforce_service_auth(req, call_next)

        call_next.assert_awaited_once_with(req)
        assert result == "default-mode-ok"
