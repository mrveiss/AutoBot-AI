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
