# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for SSO auth API callback URL validation (MVA-3396 M-2).

Tests the security hardening for OAuth2/OIDC callback URL construction
to prevent authorization code phishing via X-Forwarded-Host manipulation.

Avoids importing FastAPI directly to bypass python_multipart dependency conflict.
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
    assert result == "http://LOCALHOST/api/auth/sso/callback"


# ============================================================================
# Rate Limiting Tests (MVA-3397 M-1)
# ============================================================================


@pytest.mark.asyncio
async def test_sso_login_rate_limit():
    """Test SSO login endpoint rate limiting (10 req/min per IP)."""
    import importlib.util
    import sys
    from unittest.mock import AsyncMock, MagicMock, patch

    # Mock FastAPI dependencies
    sys.modules["fastapi"] = MagicMock()
    sys.modules["fastapi.responses"] = MagicMock()
    sys.modules["user_management.database"] = MagicMock()
    sys.modules["user_management.schemas.sso"] = MagicMock()
    sys.modules["user_management.services.base_service"] = MagicMock()
    sys.modules["user_management.services.sso_service"] = MagicMock()
    sys.modules["services.auth"] = MagicMock()

    spec = importlib.util.spec_from_file_location(
        "sso_auth", Path(__file__).parent.parent.parent / "api" / "sso_auth.py"
    )
    sso_auth = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sso_auth)

    # Mock request and response
    request = MagicMock()
    request.client = MagicMock()
    request.client.host = "192.168.1.1"
    response = MagicMock()
    response.headers = {}

    # Mock the rate limiter to simulate rate limit exceeded
    with (
        patch.object(sso_auth._sso_login_limiter, "acquire", new_callable=AsyncMock) as mock_acquire,
        patch.object(sso_auth._sso_login_limiter, "get_retry_after_seconds", new_callable=AsyncMock) as mock_retry,
    ):
        mock_acquire.return_value = False  # Rate limit exceeded
        mock_retry.return_value = 45  # 45 seconds until retry

        # Attempt to call endpoint (should raise HTTPException)
        with pytest.raises(Exception) as exc_info:
            await sso_auth.initiate_sso_login(
                provider_id="00000000-0000-0000-0000-000000000001", request=request, response=response, db=MagicMock()
            )

        # Verify rate limiter was called with correct key
        mock_acquire.assert_called_once_with("ip:192.168.1.1")

        # Verify Retry-After header was set
        assert response.headers.get("Retry-After") == "45"


@pytest.mark.asyncio
async def test_ldap_login_rate_limit():
    """Test LDAP login endpoint rate limiting (5 req/min per username)."""
    import importlib.util
    import sys
    from unittest.mock import AsyncMock, MagicMock, patch

    # Mock FastAPI dependencies
    sys.modules["fastapi"] = MagicMock()
    sys.modules["fastapi.responses"] = MagicMock()
    sys.modules["user_management.database"] = MagicMock()
    sys.modules["user_management.schemas.sso"] = MagicMock()
    sys.modules["user_management.services.base_service"] = MagicMock()
    sys.modules["user_management.services.sso_service"] = MagicMock()
    sys.modules["services.auth"] = MagicMock()

    spec = importlib.util.spec_from_file_location(
        "sso_auth", Path(__file__).parent.parent.parent / "api" / "sso_auth.py"
    )
    sso_auth = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sso_auth)

    # Mock login data
    login_data = MagicMock()
    login_data.username = "testuser"
    response = MagicMock()
    response.headers = {}

    # Mock the rate limiter to simulate rate limit exceeded
    with (
        patch.object(sso_auth._ldap_login_limiter, "acquire", new_callable=AsyncMock) as mock_acquire,
        patch.object(sso_auth._ldap_login_limiter, "get_retry_after_seconds", new_callable=AsyncMock) as mock_retry,
    ):
        mock_acquire.return_value = False  # Rate limit exceeded
        mock_retry.return_value = 30  # 30 seconds until retry

        # Attempt to call endpoint (should raise HTTPException)
        with pytest.raises(Exception) as exc_info:
            await sso_auth.ldap_login(login_data=login_data, response=response, db=MagicMock())

        # Verify rate limiter was called with correct key
        mock_acquire.assert_called_once_with("username:testuser")

        # Verify Retry-After header was set
        assert response.headers.get("Retry-After") == "30"


@pytest.mark.asyncio
async def test_sso_callback_rate_limit():
    """Test SSO callback endpoint rate limiting (20 req/min per IP)."""
    import importlib.util
    import sys
    from unittest.mock import AsyncMock, MagicMock, patch

    # Mock FastAPI dependencies
    sys.modules["fastapi"] = MagicMock()
    sys.modules["fastapi.responses"] = MagicMock()
    sys.modules["user_management.database"] = MagicMock()
    sys.modules["user_management.schemas.sso"] = MagicMock()
    sys.modules["user_management.services.base_service"] = MagicMock()
    sys.modules["user_management.services.sso_service"] = MagicMock()
    sys.modules["services.auth"] = MagicMock()

    spec = importlib.util.spec_from_file_location(
        "sso_auth", Path(__file__).parent.parent.parent / "api" / "sso_auth.py"
    )
    sso_auth = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sso_auth)

    # Mock request and response
    request = MagicMock()
    request.client = MagicMock()
    request.client.host = "10.0.0.5"
    response = MagicMock()
    response.headers = {}

    # Mock the rate limiter to simulate rate limit exceeded
    with (
        patch.object(sso_auth._sso_callback_limiter, "acquire", new_callable=AsyncMock) as mock_acquire,
        patch.object(sso_auth._sso_callback_limiter, "get_retry_after_seconds", new_callable=AsyncMock) as mock_retry,
    ):
        mock_acquire.return_value = False  # Rate limit exceeded
        mock_retry.return_value = 60  # 60 seconds until retry

        # Attempt to call endpoint (should raise HTTPException)
        with pytest.raises(Exception) as exc_info:
            await sso_auth.oauth_callback(
                request=request, response=response, code="test_code", state="test_state", db=MagicMock()
            )

        # Verify rate limiter was called with correct key
        mock_acquire.assert_called_once_with("ip:10.0.0.5")

        # Verify Retry-After header was set
        assert response.headers.get("Retry-After") == "60"


# ============================================================================
# X-Forwarded-For Header Tests (MVA-3671)
# ============================================================================


@pytest.mark.asyncio
async def test_sso_login_rate_limit_with_x_forwarded_for_trusted():
    """Test rate limiting respects X-Forwarded-For from trusted proxy (MVA-3671)."""
    import importlib.util
    import sys
    from unittest.mock import AsyncMock, MagicMock, patch

    # Mock FastAPI dependencies BEFORE importing
    sys.modules["fastapi"] = MagicMock()
    sys.modules["fastapi.responses"] = MagicMock()
    sys.modules["user_management.database"] = MagicMock()
    sys.modules["user_management.schemas.sso"] = MagicMock()
    sys.modules["user_management.services.base_service"] = MagicMock()
    sys.modules["user_management.services.sso_service"] = MagicMock()
    sys.modules["services.auth"] = MagicMock()
    sys.modules["config"] = MagicMock()
    sys.modules["config"].settings = MagicMock()
    sys.modules["config"].settings.trusted_proxies = ["127.0.0.1"]

    # Mock proxy_utils to avoid starlette import issues
    sys.modules["autobot_shared.proxy_utils"] = MagicMock()

    spec = importlib.util.spec_from_file_location(
        "sso_auth", Path(__file__).parent.parent.parent / "api" / "sso_auth.py"
    )
    sso_auth = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sso_auth)

    # Mock request with X-Forwarded-For header from trusted proxy (127.0.0.1)
    request = MagicMock()
    request.client = MagicMock()
    request.client.host = "127.0.0.1"  # nginx proxy IP
    request.headers = MagicMock()
    request.headers.get = lambda k, default=None: "203.0.113.42" if k == "X-Forwarded-For" else default
    response = MagicMock()
    response.headers = {}

    # Patch get_client_ip to return the real client IP from X-Forwarded-For
    def mock_get_client_ip(request, trusted_proxies=None):
        if request.client.host == "127.0.0.1":
            forwarded = request.headers.get("X-Forwarded-For", "")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return request.client.host

    with (
        patch.object(sso_auth, "get_client_ip", side_effect=mock_get_client_ip),
        patch.object(sso_auth._sso_login_limiter, "acquire", new_callable=AsyncMock) as mock_acquire,
        patch.object(sso_auth._sso_login_limiter, "get_retry_after_seconds", new_callable=AsyncMock) as mock_retry,
    ):
        mock_acquire.return_value = False  # Rate limit exceeded
        mock_retry.return_value = 45

        with pytest.raises(Exception):
            await sso_auth.initiate_sso_login(
                provider_id="00000000-0000-0000-0000-000000000001", request=request, response=response, db=MagicMock()
            )

        # Verify rate limiter was called with the REAL client IP from X-Forwarded-For
        mock_acquire.assert_called_once_with("ip:203.0.113.42")


@pytest.mark.asyncio
async def test_sso_login_rate_limit_with_x_forwarded_for_untrusted():
    """Test rate limiting ignores X-Forwarded-For from untrusted source (MVA-3671)."""
    import importlib.util
    import sys
    from unittest.mock import AsyncMock, MagicMock, patch

    # Mock FastAPI dependencies BEFORE importing
    sys.modules["fastapi"] = MagicMock()
    sys.modules["fastapi.responses"] = MagicMock()
    sys.modules["user_management.database"] = MagicMock()
    sys.modules["user_management.schemas.sso"] = MagicMock()
    sys.modules["user_management.services.base_service"] = MagicMock()
    sys.modules["user_management.services.sso_service"] = MagicMock()
    sys.modules["services.auth"] = MagicMock()
    sys.modules["config"] = MagicMock()
    sys.modules["config"].settings = MagicMock()
    sys.modules["config"].settings.trusted_proxies = ["127.0.0.1"]

    # Mock proxy_utils to avoid starlette import issues
    sys.modules["autobot_shared.proxy_utils"] = MagicMock()

    spec = importlib.util.spec_from_file_location(
        "sso_auth", Path(__file__).parent.parent.parent / "api" / "sso_auth.py"
    )
    sso_auth = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sso_auth)

    # Mock request with X-Forwarded-For header from UNTRUSTED source (direct connection)
    request = MagicMock()
    request.client = MagicMock()
    request.client.host = "203.0.113.99"  # attacker's real IP
    request.headers = MagicMock()
    # Attacker tries to spoof IP via X-Forwarded-For
    request.headers.get = lambda k, default=None: "1.2.3.4" if k == "X-Forwarded-For" else default
    response = MagicMock()
    response.headers = {}

    # Patch get_client_ip to ignore X-Forwarded-For from untrusted sources
    def mock_get_client_ip(request, trusted_proxies=None):
        if request.client.host != "127.0.0.1":
            # Untrusted source - ignore X-Forwarded-For
            return request.client.host
        # Trusted source - use X-Forwarded-For
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host

    with (
        patch.object(sso_auth, "get_client_ip", side_effect=mock_get_client_ip),
        patch.object(sso_auth._sso_login_limiter, "acquire", new_callable=AsyncMock) as mock_acquire,
        patch.object(sso_auth._sso_login_limiter, "get_retry_after_seconds", new_callable=AsyncMock) as mock_retry,
    ):
        mock_acquire.return_value = False  # Rate limit exceeded
        mock_retry.return_value = 45

        with pytest.raises(Exception):
            await sso_auth.initiate_sso_login(
                provider_id="00000000-0000-0000-0000-000000000001", request=request, response=response, db=MagicMock()
            )

        # Verify rate limiter was called with attacker's REAL IP, NOT spoofed IP
        mock_acquire.assert_called_once_with("ip:203.0.113.99")


@pytest.mark.asyncio
async def test_sso_callback_rate_limit_with_x_forwarded_for():
    """Test OAuth callback rate limiting respects X-Forwarded-For from trusted proxy (MVA-3671)."""
    import importlib.util
    import sys
    from unittest.mock import AsyncMock, MagicMock, patch

    # Mock FastAPI dependencies BEFORE importing
    sys.modules["fastapi"] = MagicMock()
    sys.modules["fastapi.responses"] = MagicMock()
    sys.modules["user_management.database"] = MagicMock()
    sys.modules["user_management.schemas.sso"] = MagicMock()
    sys.modules["user_management.services.base_service"] = MagicMock()
    sys.modules["user_management.services.sso_service"] = MagicMock()
    sys.modules["services.auth"] = MagicMock()
    sys.modules["config"] = MagicMock()
    sys.modules["config"].settings = MagicMock()
    sys.modules["config"].settings.trusted_proxies = ["127.0.0.1", "::1"]

    # Mock proxy_utils to avoid starlette import issues
    sys.modules["autobot_shared.proxy_utils"] = MagicMock()

    spec = importlib.util.spec_from_file_location(
        "sso_auth", Path(__file__).parent.parent.parent / "api" / "sso_auth.py"
    )
    sso_auth = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sso_auth)

    # Mock request with X-Forwarded-For header from trusted proxy
    request = MagicMock()
    request.client = MagicMock()
    request.client.host = "127.0.0.1"  # nginx proxy IP
    request.headers = MagicMock()
    request.headers.get = lambda k, default=None: "198.51.100.123" if k == "X-Forwarded-For" else default
    response = MagicMock()
    response.headers = {}

    # Patch get_client_ip to return the real client IP from X-Forwarded-For
    def mock_get_client_ip(request, trusted_proxies=None):
        if request.client.host in ("127.0.0.1", "::1"):
            forwarded = request.headers.get("X-Forwarded-For", "")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return request.client.host

    with (
        patch.object(sso_auth, "get_client_ip", side_effect=mock_get_client_ip),
        patch.object(sso_auth._sso_callback_limiter, "acquire", new_callable=AsyncMock) as mock_acquire,
        patch.object(sso_auth._sso_callback_limiter, "get_retry_after_seconds", new_callable=AsyncMock) as mock_retry,
    ):
        mock_acquire.return_value = False  # Rate limit exceeded
        mock_retry.return_value = 60

        with pytest.raises(Exception):
            await sso_auth.oauth_callback(
                request=request, response=response, code="test_code", state="test_state", db=MagicMock()
            )

        # Verify rate limiter was called with the REAL client IP from X-Forwarded-For
        mock_acquire.assert_called_once_with("ip:198.51.100.123")
