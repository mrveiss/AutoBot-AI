# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for GH #6838 — /api/auth/login accepts any credential.

Linked issue: https://github.com/mrveiss/AutoBot-AI/issues/6838

In SINGLE_USER deployment mode the login endpoint skips PostgreSQL auth
entirely, issuing an admin JWT for any (or no) credential. This is a P0
security vulnerability because any user with network access can mint an
admin token.

Fix: gate the any-credential bypass on AUTOBOT_DEV_AUTH_BYPASS=true with a
loud boot warning; reject wrong credentials in all other cases.

Regression guarantee: tests fail if the any-credential bypass is
re-introduced without the AUTOBOT_DEV_AUTH_BYPASS env-flag gate.
"""

import os
import sys
import types
from contextlib import asynccontextmanager
from typing import TypeVar
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import BaseModel

T = TypeVar("T")

# ── Stub api.schemas_agent with minimal pydantic models ──────────────────────
# api.auth imports LoginRequest/LoginResponse/etc from api.schemas_agent, which
# has a large import chain. Stub the module with only the types api.auth needs.


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    message: str = ""
    user: dict = {}
    token: str = ""
    session_id: str = ""


class LogoutRequest(BaseModel):
    session_id: str | None = None


class AuthCheckResponse(BaseModel):
    authenticated: bool = False
    user: dict = {}


class AuthPermissionResponse(BaseModel):
    allowed: bool = False


class AuthUserInfoResponse(BaseModel):
    username: str = ""
    role: str = ""


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ChangePasswordResponse(BaseModel):
    success: bool = False
    message: str = ""


class SignupRequest(BaseModel):
    username: str
    password: str
    email: str = ""


class SignupResponse(BaseModel):
    success: bool = False
    message: str = ""


def _ensure_pkg(name: str) -> types.ModuleType:
    """Ensure a namespace package exists in sys.modules without overriding real packages.

    Sets __path__ to the real package directory (if it exists on the filesystem)
    so other test files can still import real submodules of the same package.
    """
    mod = sys.modules.get(name)
    if mod is not None:
        return mod
    import os as _os

    mod = types.ModuleType(name)
    # Point __path__ at the real directory so downstream tests can load real submodules.
    top_name = name.split(".")[0]
    for base in sys.path:
        candidate = _os.path.join(base, top_name)
        if _os.path.isdir(candidate):
            mod.__path__ = [candidate]
            break
    sys.modules[name] = mod
    return mod


def _register_stub(name: str, attrs: dict) -> types.ModuleType:
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        mod.__path__ = []  # mark as leaf stub (no filesystem submodules)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# Do NOT register 'api' itself — let Python import the real package from
# autobot-backend/api/ (conftest adds autobot-backend to sys.path). We only
# stub the two submodules that have deep import chains.

_schemas_agent_stub = types.ModuleType("api.schemas_agent")
_schemas_agent_stub.__path__ = []
_schemas_agent_stub.LoginRequest = LoginRequest
_schemas_agent_stub.LoginResponse = LoginResponse
_schemas_agent_stub.LogoutRequest = LogoutRequest
_schemas_agent_stub.AuthCheckResponse = AuthCheckResponse
_schemas_agent_stub.AuthPermissionResponse = AuthPermissionResponse
_schemas_agent_stub.AuthUserInfoResponse = AuthUserInfoResponse
_schemas_agent_stub.ChangePasswordRequest = ChangePasswordRequest
_schemas_agent_stub.ChangePasswordResponse = ChangePasswordResponse
_schemas_agent_stub.SignupRequest = SignupRequest
_schemas_agent_stub.SignupResponse = SignupResponse
sys.modules["api.schemas_agent"] = _schemas_agent_stub

# Import the real api.schemas_common rather than stubbing it — avoids bleed into
# other test files that need the full set of exports (SuccessDataResponse, etc.).
if "api.schemas_common" not in sys.modules:
    import importlib.util as _ilu

    _sc_spec = _ilu.spec_from_file_location(
        "api.schemas_common",
        str(__file__).replace(
            "tests/api/test_auth_login_bypass_regression.py",
            "api/schemas_common.py",
        ),
    )
    if _sc_spec and _sc_spec.loader:
        _sc_mod = _ilu.module_from_spec(_sc_spec)
        sys.modules["api.schemas_common"] = _sc_mod
        try:
            _sc_spec.loader.exec_module(_sc_mod)
        except Exception:
            pass  # fall back to empty stub if load fails


# Passthrough error-handling decorator
def _passthrough(**_kw):
    import functools

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except HTTPException:
                raise
            except Exception:
                raise

        return wrapper

    return decorator


def _passthrough_sync(**_kw):
    import functools

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        return wrapper

    return decorator


if "autobot_shared.error_boundaries" not in sys.modules:
    _register_stub(
        "autobot_shared.error_boundaries",
        {
            "with_error_handling": _passthrough,
            "error_boundary": _passthrough_sync,
            "with_error_boundary": _passthrough_sync,
            "with_async_error_boundary": _passthrough,
            "get_error_boundary_manager": MagicMock(),
            "ErrorCategory": MagicMock(SERVER_ERROR="SERVER_ERROR"),
        },
    )

_ensure_pkg("services")
_register_stub(
    "services.event_log",
    {
        "EventType": MagicMock(USER_LOGIN="USER_LOGIN", USER_LOGOUT="USER_LOGOUT"),
        "emit": MagicMock(),
    },
)

_constants_pkg = _ensure_pkg("constants")
# Add commonly imported names to the constants stub so transitive imports in
# other test modules (loaded in the same pytest session) don't fail.
for _const_name in (
    "CircuitBreakerDefaults",
    "SecurityThresholds",
    "AgentThresholds",
    "RetryConfig",
    "TimeoutDefaults",
    "RateLimitDefaults",
):
    if not hasattr(_constants_pkg, _const_name):
        setattr(_constants_pkg, _const_name, MagicMock())
_register_stub(
    "constants.error_constants",
    {
        "ERR_INVALID_CREDENTIALS": "Invalid username or password",
        "ERR_INVALID_TOKEN": "Invalid or expired token",
    },
)

_ensure_pkg("utils")
_register_stub(
    "utils.catalog_http_exceptions",
    {"raise_auth_error": MagicMock(side_effect=HTTPException(status_code=401, detail="Auth error"))},
)

if "auth_middleware" not in sys.modules:
    _mw = MagicMock()
    _mw.create_jwt_token.return_value = "fake-token-for-tests"
    _mw.create_session.return_value = "fake-session-id"
    _mw.get_user_from_request.return_value = None
    _register_stub(
        "auth_middleware",
        {
            "get_auth_middleware": MagicMock(return_value=_mw),
            "check_admin_permission": MagicMock(return_value=True),
            "get_current_user": MagicMock(return_value={"username": "admin", "role": "admin"}),
            "raise_auth_error": MagicMock(side_effect=HTTPException(status_code=401, detail="Auth error")),
        },
    )

_register_stub("security_layer", {"SecurityLayer": MagicMock})

_config_pkg = _ensure_pkg("config")
# Expose `config` and `cfg` attributes so `from config import config` doesn't fail
# in transitive dependencies of other test modules loaded in the same pytest session.
if not hasattr(_config_pkg, "config"):
    _config_pkg.config = MagicMock()
    _config_pkg.cfg = MagicMock()
    _config_pkg.get_config_manager = MagicMock(return_value=MagicMock(get=MagicMock(return_value={})))
_register_stub(
    "config.manager",
    {"get_config_manager": MagicMock(return_value=MagicMock(get=MagicMock(return_value={})))},
)

# Stub user_management.database without blocking user_management filesystem lookup
_db_session_mock = AsyncMock()


@asynccontextmanager
async def _stub_db_session():
    yield _db_session_mock


_register_stub(
    "user_management.database",
    {"db_session_context": _stub_db_session},
)

_ensure_pkg("user_management.services")
_register_stub(
    "user_management.services.user_service",
    {"UserService": MagicMock},
)

# ── import after stubs ────────────────────────────────────────────────────────

from api.auth import login  # noqa: E402
from user_management.config import DeploymentMode  # noqa: E402

# ── test fixtures ─────────────────────────────────────────────────────────────

_SINGLE_USER_CFG = MagicMock()
_SINGLE_USER_CFG.mode = DeploymentMode.SINGLE_USER

_MULTI_USER_CFG = MagicMock()
_MULTI_USER_CFG.mode = DeploymentMode.SINGLE_COMPANY

_WRONG_CREDENTIAL = "definitely-not-the-right-credential"
_ANY_CREDENTIAL = "anything-in-bypass-mode"


def _make_auth_mw():
    mw = MagicMock()
    mw.create_jwt_token.return_value = "fake-token-for-tests"
    mw.create_session.return_value = "fake-session-id"
    return mw


def _make_request():
    req = MagicMock()
    req.client.host = "127.0.0.1"
    return req


# ── GH #6838 regression tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_single_user_wrong_credential_rejected_without_bypass():
    """GH #6838: wrong credential must return 401 in SINGLE_USER mode without bypass.

    Pre-fix: any credential authenticated in SINGLE_USER mode (no check at all).
    Post-fix: only AUTOBOT_DEV_AUTH_BYPASS=true enables the any-credential bypass.
    """
    env_no_bypass = {k: v for k, v in os.environ.items() if k != "AUTOBOT_DEV_AUTH_BYPASS"}

    with patch("user_management.config.get_deployment_config", return_value=_SINGLE_USER_CFG):
        with patch("api.auth.get_auth_middleware", return_value=_make_auth_mw()):
            with patch("api.auth._emit_event"):
                with patch.dict(os.environ, env_no_bypass, clear=True):
                    try:
                        result = await login(
                            _make_request(),
                            LoginRequest(username="admin", password=_WRONG_CREDENTIAL),
                        )
                        pytest.fail(
                            "GH #6838 regression: login accepted wrong credential in "
                            "SINGLE_USER mode without AUTOBOT_DEV_AUTH_BYPASS=true. "
                            f"Returned success={result.success}."
                        )
                    except HTTPException as exc:
                        assert exc.status_code == 401, f"Expected HTTP 401 for wrong credential, got {exc.status_code}."


@pytest.mark.asyncio
async def test_single_user_dev_bypass_allows_any_credential():
    """GH #6838: AUTOBOT_DEV_AUTH_BYPASS=true must still allow any-credential auth.

    This env-flag is the deliberate opt-in for local development. Verifies
    the bypass path works correctly after the fix is applied.
    """
    with patch("user_management.config.get_deployment_config", return_value=_SINGLE_USER_CFG):
        with patch("api.auth.get_auth_middleware", return_value=_make_auth_mw()):
            with patch("api.auth._emit_event"):
                with patch.dict(os.environ, {"AUTOBOT_DEV_AUTH_BYPASS": "true"}):
                    result = await login(
                        _make_request(),
                        LoginRequest(username="admin", password=_ANY_CREDENTIAL),
                    )

    assert result.success is True, "Dev bypass (AUTOBOT_DEV_AUTH_BYPASS=true) must allow any-credential auth."
    assert result.token, "A valid token must be returned when dev bypass is active."


@pytest.mark.asyncio
async def test_wrong_credential_rejected_in_multi_user_mode():
    """GH #6838: wrong credential must return 401 in multi-user mode (baseline check)."""
    with patch("user_management.config.get_deployment_config", return_value=_MULTI_USER_CFG):
        with patch(
            "api.auth._authenticate_and_build_user_data",
            new_callable=AsyncMock,
            side_effect=HTTPException(status_code=401, detail="Invalid credentials"),
        ):
            with patch("api.auth._emit_event"):
                with pytest.raises(HTTPException) as exc_info:
                    await login(
                        _make_request(),
                        LoginRequest(username="admin", password=_WRONG_CREDENTIAL),
                    )

    assert exc_info.value.status_code == 401
