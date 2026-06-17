# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for SSO auth API callback URL validation (MVA-3396 M-2) and
rate-limit enforcement (Issue #9611).

Tests the security hardening for OAuth2/OIDC callback URL construction
to prevent authorization code phishing via X-Forwarded-Host manipulation.

Avoids importing FastAPI directly to bypass python_multipart dependency conflict.
"""

import asyncio
import importlib.util
import sys
import unittest.mock
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "autobot_shared"))


def _make_mock_request(scheme: str, netloc: str, headers: dict | None = None) -> MagicMock:
    """Create a mock request object without importing FastAPI."""
    request = MagicMock()
    request.url = SimpleNamespace(scheme=scheme, netloc=netloc)
    request.headers = MagicMock()

    if headers:
        request.headers.get = lambda k, default=None: headers.get(k, default)
    else:
        request.headers.get = lambda k, default=None: default

    return request


def test_build_callback_url_valid_host_localhost():
    """Test callback URL construction with valid localhost host."""
    # Import after path setup to avoid FastAPI import
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "sso_auth", Path(__file__).parent.parent.parent / "api" / "sso_auth.py"
    )
    sso_auth = importlib.util.module_from_spec(spec)

    # Pre-stub FastAPI dependencies
    sys.modules["fastapi"] = MagicMock()
    sys.modules["fastapi.responses"] = MagicMock()
    sys.modules["user_management.database"] = MagicMock()
    sys.modules["user_management.schemas.sso"] = MagicMock()
    sys.modules["user_management.services.base_service"] = MagicMock()
    sys.modules["user_management.services.sso_service"] = MagicMock()
    sys.modules["services.auth"] = MagicMock()

    spec.loader.exec_module(sso_auth)

    request = _make_mock_request("http", "localhost", {"x-forwarded-proto": "http", "x-forwarded-host": "localhost"})

    result = sso_auth._build_callback_url(request)
    assert result == "http://localhost/api/auth/sso/callback"


def test_build_callback_url_valid_host_127_0_0_1():
    """Test callback URL construction with valid 127.0.0.1 host."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "sso_auth", Path(__file__).parent.parent.parent / "api" / "sso_auth.py"
    )
    sso_auth = importlib.util.module_from_spec(spec)

    sys.modules["fastapi"] = MagicMock()
    sys.modules["fastapi.responses"] = MagicMock()
    sys.modules["user_management.database"] = MagicMock()
    sys.modules["user_management.schemas.sso"] = MagicMock()
    sys.modules["user_management.services.base_service"] = MagicMock()
    sys.modules["user_management.services.sso_service"] = MagicMock()
    sys.modules["services.auth"] = MagicMock()

    spec.loader.exec_module(sso_auth)

    request = _make_mock_request("http", "127.0.0.1", {"x-forwarded-proto": "http", "x-forwarded-host": "127.0.0.1"})

    result = sso_auth._build_callback_url(request)
    assert result == "http://127.0.0.1/api/auth/sso/callback"


def test_build_callback_url_invalid_host_rejected():
    """Test callback URL rejects host not in allowlist (phishing attempt)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "sso_auth", Path(__file__).parent.parent.parent / "api" / "sso_auth.py"
    )
    sso_auth = importlib.util.module_from_spec(spec)

    # Mock HTTPException to avoid FastAPI import
    class MockHTTPException(Exception):
        def __init__(self, status_code, detail):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)

    fastapi_mock = MagicMock()
    fastapi_mock.HTTPException = MockHTTPException
    fastapi_mock.status = SimpleNamespace(HTTP_400_BAD_REQUEST=400)

    sys.modules["fastapi"] = fastapi_mock
    sys.modules["fastapi.responses"] = MagicMock()
    sys.modules["user_management.database"] = MagicMock()
    sys.modules["user_management.schemas.sso"] = MagicMock()
    sys.modules["user_management.services.base_service"] = MagicMock()
    sys.modules["user_management.services.sso_service"] = MagicMock()
    sys.modules["services.auth"] = MagicMock()

    spec.loader.exec_module(sso_auth)

    request = _make_mock_request(
        "https", "attacker.com", {"x-forwarded-proto": "https", "x-forwarded-host": "attacker.com"}
    )

    with pytest.raises(MockHTTPException) as exc_info:
        sso_auth._build_callback_url(request)

    assert exc_info.value.status_code == 400
    assert "Invalid callback host" in exc_info.value.detail


def test_build_callback_url_host_with_port():
    """Test callback URL construction strips port for allowlist validation."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "sso_auth", Path(__file__).parent.parent.parent / "api" / "sso_auth.py"
    )
    sso_auth = importlib.util.module_from_spec(spec)

    sys.modules["fastapi"] = MagicMock()
    sys.modules["fastapi.responses"] = MagicMock()
    sys.modules["user_management.database"] = MagicMock()
    sys.modules["user_management.schemas.sso"] = MagicMock()
    sys.modules["user_management.services.base_service"] = MagicMock()
    sys.modules["user_management.services.sso_service"] = MagicMock()
    sys.modules["services.auth"] = MagicMock()

    spec.loader.exec_module(sso_auth)

    request = _make_mock_request(
        "http", "localhost:8000", {"x-forwarded-proto": "http", "x-forwarded-host": "localhost:8000"}
    )

    result = sso_auth._build_callback_url(request)
    assert result == "http://localhost:8000/api/auth/sso/callback"


def test_build_callback_url_case_insensitive():
    """Test callback URL validation is case-insensitive."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "sso_auth", Path(__file__).parent.parent.parent / "api" / "sso_auth.py"
    )
    sso_auth = importlib.util.module_from_spec(spec)

    sys.modules["fastapi"] = MagicMock()
    sys.modules["fastapi.responses"] = MagicMock()
    sys.modules["user_management.database"] = MagicMock()
    sys.modules["user_management.schemas.sso"] = MagicMock()
    sys.modules["user_management.services.base_service"] = MagicMock()
    sys.modules["user_management.services.sso_service"] = MagicMock()
    sys.modules["services.auth"] = MagicMock()

    spec.loader.exec_module(sso_auth)

    request = _make_mock_request("http", "LOCALHOST", {"x-forwarded-proto": "http", "x-forwarded-host": "LOCALHOST"})

    result = sso_auth._build_callback_url(request)
    # RFC 3986 §3.2.2: host is case-insensitive; _build_callback_url normalises to lowercase.
    assert result == "http://localhost/api/auth/sso/callback"


# ---------------------------------------------------------------------------
# Helpers for rate-limit tests (Issue #9611)
# ---------------------------------------------------------------------------

_SSO_AUTH_PY = Path(__file__).parent.parent.parent / "api" / "sso_auth.py"


class _FakeRateLimiter:
    """Stand-in RateLimiter whose limits are never hit (allows all requests).

    Instantiated during module load for the three module-level limiter objects.
    Tests then replace those instances via patch.object.
    """

    def __init__(self, **kwargs):
        pass

    async def acquire(self, key: str) -> bool:
        return True

    async def get_retry_after_seconds(self, key: str) -> int:
        return 0


def _load_sso_auth_with_real_endpoints() -> object:
    """Load sso_auth.py with identity-decorator stubs so endpoint functions
    remain proper coroutines (not MagicMock wrappers).

    A fresh spec/module is created on every call so tests are isolated.
    """
    _API_PATH = Path(__file__).parent.parent.parent

    # ---- fastapi stub with identity router decorators ----
    class _MockHTTPException(Exception):
        def __init__(self, status_code: int, detail: str) -> None:
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)

    def _identity_deco(*args, **kwargs):
        def decorator(fn):
            return fn

        return decorator

    fake_router = MagicMock()
    fake_router.get = _identity_deco
    fake_router.post = _identity_deco

    fastapi_stub = MagicMock()
    fastapi_stub.APIRouter = MagicMock(return_value=fake_router)
    fastapi_stub.HTTPException = _MockHTTPException
    fastapi_stub.Depends = lambda dep: dep
    fastapi_stub.Form = lambda *a, **kw: None
    fastapi_stub.Query = lambda *a, **kw: None
    fastapi_stub.status = SimpleNamespace(
        HTTP_429_TOO_MANY_REQUESTS=429,
        HTTP_400_BAD_REQUEST=400,
        HTTP_401_UNAUTHORIZED=401,
        HTTP_404_NOT_FOUND=404,
        HTTP_302_FOUND=302,
    )

    # ---- rate_limiter stub: produces _FakeRateLimiter instances ----
    rate_limiter_stub = MagicMock()
    rate_limiter_stub.RateLimiter = _FakeRateLimiter

    # ---- proxy_utils stub ----
    proxy_utils_stub = MagicMock()
    proxy_utils_stub.get_client_ip = MagicMock(return_value="1.2.3.4")

    # ---- config stub ----
    settings_stub = MagicMock()
    settings_stub.trusted_proxies = []
    config_stub = MagicMock()
    config_stub.settings = settings_stub

    stubs = {
        "autobot_shared": MagicMock(),
        "autobot_shared.proxy_utils": proxy_utils_stub,
        "autobot_shared.rate_limiter": rate_limiter_stub,
        "autobot_shared.ssot_config": MagicMock(),
        "config": config_stub,
        "fastapi": fastapi_stub,
        "fastapi.responses": MagicMock(),
        "user_management.database": MagicMock(),
        "user_management.schemas.sso": MagicMock(),
        "user_management.services.base_service": MagicMock(),
        "user_management.services.sso_service": MagicMock(),
        "services.auth": MagicMock(),
    }
    prev = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)

    try:
        spec = importlib.util.spec_from_file_location("sso_auth_rl_" + uuid.uuid4().hex[:8], _SSO_AUTH_PY)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        for k, v in prev.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    return mod, _MockHTTPException


def _throttled_limiter(retry_after: int = 30) -> MagicMock:
    """Return a MagicMock that mimics a saturated RateLimiter (acquire→False)."""
    limiter = MagicMock()
    limiter.acquire = AsyncMock(return_value=False)
    limiter.get_retry_after_seconds = AsyncMock(return_value=retry_after)
    return limiter


# ---------------------------------------------------------------------------
# Rate-limit tests (Issue #9611)
# ---------------------------------------------------------------------------


def test_sso_login_rate_limited_returns_429_with_retry_after():
    """SSO login endpoint returns 429 + Retry-After when _sso_login_limiter throttles."""
    sso_auth, MockHTTPException = _load_sso_auth_with_real_endpoints()
    mock_limiter = _throttled_limiter(30)

    response_headers: dict = {}
    response = MagicMock()
    response.headers = response_headers
    request = _make_mock_request("http", "localhost", {"x-forwarded-proto": "http", "x-forwarded-host": "localhost"})

    async def _call():
        return await sso_auth.initiate_sso_login(
            provider_id=uuid.uuid4(), request=request, response=response, db=MagicMock()
        )

    with unittest.mock.patch.object(sso_auth, "_sso_login_limiter", mock_limiter):
        with pytest.raises(MockHTTPException) as exc_info:
            asyncio.run(_call())

    assert exc_info.value.status_code == 429
    assert response_headers.get("Retry-After") == "30"
    mock_limiter.acquire.assert_awaited_once()
    mock_limiter.get_retry_after_seconds.assert_awaited_once()


def test_sso_callback_rate_limited_returns_429_with_retry_after():
    """OAuth callback endpoint returns 429 + Retry-After when _sso_callback_limiter throttles."""
    sso_auth, MockHTTPException = _load_sso_auth_with_real_endpoints()
    mock_limiter = _throttled_limiter(30)

    response_headers: dict = {}
    response = MagicMock()
    response.headers = response_headers
    request = _make_mock_request("http", "localhost", {"x-forwarded-proto": "http", "x-forwarded-host": "localhost"})

    async def _call():
        return await sso_auth.oauth_callback(
            request=request, response=response, code="auth-code", state="state-val", db=MagicMock()
        )

    with unittest.mock.patch.object(sso_auth, "_sso_callback_limiter", mock_limiter):
        with pytest.raises(MockHTTPException) as exc_info:
            asyncio.run(_call())

    assert exc_info.value.status_code == 429
    assert response_headers.get("Retry-After") == "30"
    mock_limiter.acquire.assert_awaited_once()
    mock_limiter.get_retry_after_seconds.assert_awaited_once()


def test_ldap_login_rate_limited_returns_429_with_retry_after():
    """LDAP login endpoint returns 429 + Retry-After when _ldap_login_limiter throttles."""
    sso_auth, MockHTTPException = _load_sso_auth_with_real_endpoints()
    mock_limiter = _throttled_limiter(30)

    response_headers: dict = {}
    response = MagicMock()
    response.headers = response_headers

    login_data = MagicMock()
    login_data.username = "bruteforce_victim"

    async def _call():
        return await sso_auth.ldap_login(login_data=login_data, response=response, db=MagicMock())

    with unittest.mock.patch.object(sso_auth, "_ldap_login_limiter", mock_limiter):
        with pytest.raises(MockHTTPException) as exc_info:
            asyncio.run(_call())

    assert exc_info.value.status_code == 429
    assert response_headers.get("Retry-After") == "30"
    mock_limiter.acquire.assert_awaited_once()
    mock_limiter.get_retry_after_seconds.assert_awaited_once()
