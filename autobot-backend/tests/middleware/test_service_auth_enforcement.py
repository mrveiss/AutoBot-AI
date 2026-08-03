# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

import contextlib
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.ssot_config import (
    SERVICE_AUTH_RATE_LIMIT_MAX_FAILURES_DEFAULT,
    SERVICE_AUTH_RATE_LIMIT_WINDOW_DEFAULT,
    MiscConfig,
)
from middleware import service_auth_enforcement as _sae_mod
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


def _cfg(**overrides):
    """Patch SSOT config values for the duration of one test (#11796).

    The middleware reads ``config.service_auth_*`` from autobot_shared's SSOT
    config object, which is populated from the environment ONCE at
    instantiation — so the old env-dict patches never influenced it, and on
    hosts whose real environment sets these variables the tests asserted
    stale expectations.  Patch the config attributes the code actually reads
    instead.
    """
    stack = contextlib.ExitStack()
    for _attr, _value in overrides.items():
        stack.enter_context(patch.object(_sae_mod.config, _attr, _value))
    return stack


class TestGetEnforcementMode:
    def test_false_by_default(self):
        with _cfg(service_auth_enforcement_mode=""):
            assert get_enforcement_mode() is False

    def test_true_when_set(self):
        with _cfg(service_auth_enforcement_mode="true"):
            assert get_enforcement_mode() is True

    def test_case_insensitive_true(self):
        with _cfg(service_auth_enforcement_mode="TRUE"):
            assert get_enforcement_mode() is True

    def test_false_for_other_values(self):
        with _cfg(service_auth_enforcement_mode="1"):
            assert get_enforcement_mode() is False


class TestCircuitBreaker:
    def test_full_enforcement_at_100_percent(self):
        with _cfg(service_auth_circuit_breaker_percentage=100.0):
            assert _should_enforce_by_circuit_breaker() is True

    def test_no_enforcement_at_0_percent(self):
        with _cfg(service_auth_circuit_breaker_percentage=0.0):
            assert _should_enforce_by_circuit_breaker() is False

    def test_probabilistic_at_50_percent(self):
        with _cfg(service_auth_circuit_breaker_percentage=50.0):
            results = {_should_enforce_by_circuit_breaker() for _ in range(200)}
            assert True in results and False in results


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


@pytest.fixture
def unset_rate_limit_config(monkeypatch):
    """A MiscConfig built with the rate-limit vars genuinely unset (#13326).

    Deployed hosts and CI runners may export SERVICE_AUTH_RATE_LIMIT_*; ignore
    both the environment and the .env file so the *declared* default is tested.
    """
    for var in ("SERVICE_AUTH_RATE_LIMIT_MAX_FAILURES", "SERVICE_AUTH_RATE_LIMIT_WINDOW"):
        monkeypatch.delenv(var, raising=False)
    return MiscConfig(_env_file=None)


class TestRateLimiting:
    def setup_method(self):
        """Clear tracker before each test."""
        _failed_auth_tracker.clear()

    def test_not_rate_limited_initially(self):
        with _cfg(service_auth_rate_limit_window=300, service_auth_rate_limit_max_failures=3):
            assert _is_rate_limited("1.2.3.4") is False

    def test_rate_limited_after_max_failures(self):
        with _cfg(service_auth_rate_limit_window=300, service_auth_rate_limit_max_failures=3):
            for _ in range(3):
                _record_failed_auth("10.0.0.1")
            assert _is_rate_limited("10.0.0.1") is True

    def test_expired_failures_pruned(self):
        with _cfg(service_auth_rate_limit_window=1, service_auth_rate_limit_max_failures=2):
            _failed_auth_tracker["5.5.5.5"] = [time.time() - 10]  # expired
            assert _is_rate_limited("5.5.5.5") is False

    def test_different_ips_tracked_independently(self):
        with _cfg(service_auth_rate_limit_window=300, service_auth_rate_limit_max_failures=2):
            for _ in range(2):
                _record_failed_auth("192.168.1.1")
            assert _is_rate_limited("192.168.1.1") is True
            assert _is_rate_limited("192.168.1.2") is False

    @pytest.mark.parametrize("max_failures", [1, 3, 10])
    def test_nth_failure_allowed_and_n_plus_first_limited(self, max_failures):
        """Boundary: the Nth failure must still pass, the N+1th must not (#13326)."""
        ip = "203.0.113.7"
        with _cfg(service_auth_rate_limit_window=300, service_auth_rate_limit_max_failures=max_failures):
            for _ in range(max_failures - 1):
                _record_failed_auth(ip)
            assert _is_rate_limited(ip) is False, "Nth request must not be limited"
            _record_failed_auth(ip)
            assert _is_rate_limited(ip) is True, "N+1th request must be limited"

    def test_unset_config_does_not_reject_first_request(self, unset_rate_limit_config):
        """Default install must serve SERVICE_ONLY_PATHS, not 429 everything (#13326).

        The field defaults previously evaluated ``0 >= 0`` on the very first
        request, rejecting every service-only path before auth ever ran.
        """
        fresh = unset_rate_limit_config
        assert fresh.service_auth_rate_limit_max_failures > 0
        assert fresh.service_auth_rate_limit_window > 0
        with _cfg(
            service_auth_rate_limit_window=fresh.service_auth_rate_limit_window,
            service_auth_rate_limit_max_failures=fresh.service_auth_rate_limit_max_failures,
        ):
            assert _is_rate_limited("198.51.100.4") is False

    def test_defaults_match_declared_constants(self, unset_rate_limit_config):
        fresh = unset_rate_limit_config
        assert fresh.service_auth_rate_limit_max_failures == (SERVICE_AUTH_RATE_LIMIT_MAX_FAILURES_DEFAULT)
        assert fresh.service_auth_rate_limit_window == SERVICE_AUTH_RATE_LIMIT_WINDOW_DEFAULT

    def test_zero_max_failures_disables_rate_limiting(self):
        """0 means DISABLED, not 'block everything' (#13326)."""
        ip = "203.0.113.9"
        with _cfg(service_auth_rate_limit_window=300, service_auth_rate_limit_max_failures=0):
            assert _is_rate_limited(ip) is False
            for _ in range(50):
                _record_failed_auth(ip)
            assert _is_rate_limited(ip) is False

    def test_zero_window_disables_rate_limiting(self):
        """A zero-length window can never retain a failure — treat as disabled."""
        ip = "203.0.113.11"
        with _cfg(service_auth_rate_limit_window=0, service_auth_rate_limit_max_failures=5):
            for _ in range(50):
                _record_failed_auth(ip)
            assert _is_rate_limited(ip) is False

    def test_disabled_rate_limiting_is_logged_not_silent(self):
        _sae_mod._rate_limit_disabled_logged = False
        with _cfg(service_auth_rate_limit_window=300, service_auth_rate_limit_max_failures=0):
            with patch.object(_sae_mod.logger, "warning") as warn:
                _is_rate_limited("203.0.113.13")
                _is_rate_limited("203.0.113.14")
        assert warn.call_count == 1, "warn exactly once, not per request"


# ---------------------------------------------------------------------------
# Override token
# ---------------------------------------------------------------------------


class TestHasOverrideToken:
    def _make_request(self, token_value: str) -> MagicMock:
        req = MagicMock()
        req.headers = {"X-Override-Token": token_value}
        return req

    def test_correct_token_returns_true(self):
        with _cfg(service_auth_override_token="super-secret-token"):
            req = self._make_request("super-secret-token")
            assert _has_override_token(req) is True

    def test_wrong_token_returns_false(self):
        with _cfg(service_auth_override_token="super-secret-token"):
            req = self._make_request("wrong-token")
            assert _has_override_token(req) is False

    def test_no_env_token_returns_false(self):
        with _cfg(service_auth_override_token=""):
            req = self._make_request("anything")
            assert _has_override_token(req) is False

    def test_missing_header_returns_false(self):
        with _cfg(service_auth_override_token="super-secret-token"):
            req = MagicMock()
            # #11796: a plain dict already provides .get — assigning to
            # dict.get raised AttributeError and the test never ran green.
            req.headers = {}
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
    # #11796: a plain dict already provides .get — assigning to dict.get
    # raised AttributeError and every test using this helper never ran green.
    req.headers = {}
    req.state = MagicMock()
    return req


class TestEnforceServiceAuth:
    """Integration-level tests for the enforce_service_auth middleware function.

    All tests that check blocking behavior explicitly set service_auth_enforcement_mode="true".
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
            _cfg(service_auth_enforcement_mode="true"),
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
            _cfg(service_auth_enforcement_mode="true"),
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
            _cfg(service_auth_enforcement_mode="true"),
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
            _cfg(
                service_auth_override_token="emergency-token",
                service_auth_enforcement_mode="true",
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

            await enforce_service_auth(req, call_next)

        call_next.assert_awaited_once_with(req)

    @pytest.mark.asyncio
    async def test_rate_limited_ip_returns_429(self):
        """IP that exceeds failure threshold receives 429 before auth attempt."""
        from fastapi.responses import JSONResponse

        call_next = AsyncMock(return_value="should-not-reach")

        with (
            _cfg(service_auth_enforcement_mode="true"),
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
# Enforcement mode gating (config.service_auth_enforcement_mode)
# ---------------------------------------------------------------------------


class TestEnforcementModeGating:
    """Verify that config.service_auth_enforcement_mode controls enforce-vs-log behaviour."""

    @pytest.mark.asyncio
    async def test_logging_mode_allows_request_with_invalid_auth(self):
        """When enforcement mode is disabled, bad auth is logged but not blocked."""
        from fastapi import HTTPException

        call_next = AsyncMock(return_value="logging-mode-response")

        with (
            _cfg(service_auth_enforcement_mode="false"),
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
            _cfg(service_auth_enforcement_mode="true"),
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
            _cfg(service_auth_enforcement_mode="false"),
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
        """Without service_auth_enforcement_mode set, enforcement is disabled."""
        from fastapi import HTTPException

        call_next = AsyncMock(return_value="default-mode-ok")

        with _cfg(service_auth_enforcement_mode=""):
            with patch(
                "middleware.service_auth_enforcement.validate_service_auth",
                side_effect=HTTPException(status_code=401, detail="Missing required headers"),
            ):
                req = _make_request("/api/npu/results")
                result = await enforce_service_auth(req, call_next)

        call_next.assert_awaited_once_with(req)
        assert result == "default-mode-ok"
