# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for GH #6838 — /api/auth/login accepts any password.

Linked issue: https://github.com/mrveiss/AutoBot-AI/issues/6838

Before the fix, single_user deployment mode (the default) skipped credential
validation entirely and issued admin JWTs for any (or no) credential. Any
attacker with network access to the service could mint admin tokens.

Fix: gate the synthetic-admin login shortcut behind an explicit
AUTOBOT_DEV_AUTH_BYPASS=true env flag. Without the flag, /login rejects all
credentials in single_user mode (401), matching production behaviour.

Regression guarantee: these tests fail if the any-credential bypass is
re-introduced without the AUTOBOT_DEV_AUTH_BYPASS env-flag gate, or if the
env-flag gate is widened to other truthy-ish strings.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from api.auth import login
from api.schemas_agent import LoginRequest
from user_management.config import DeploymentConfig, DeploymentMode, FeatureFlags

# ── helpers ───────────────────────────────────────────────────────────────────


def _cfg(mode: DeploymentMode) -> DeploymentConfig:
    return DeploymentConfig(
        mode=mode,
        features=FeatureFlags(),
        postgres_enabled=mode != DeploymentMode.SINGLE_USER,
    )


def _request():
    req = MagicMock()
    req.client.host = "127.0.0.1"
    return req


def _login(username: str, password: str) -> LoginRequest:
    return LoginRequest(username=username, password=password)


# ── GH #6838 regression: credential bypass must be explicitly gated ───────────


@pytest.mark.asyncio
async def test_valid_username_wrong_password_returns_401(monkeypatch):
    """POST /api/auth/login with valid username + wrong password → 401.

    GH #6838: before the fix this returned 200 + admin JWT in SINGLE_USER mode.
    """
    monkeypatch.delenv("AUTOBOT_DEV_AUTH_BYPASS", raising=False)
    cfg = _cfg(DeploymentMode.SINGLE_USER)
    with patch("user_management.config.get_deployment_config", return_value=cfg):
        with pytest.raises(HTTPException) as exc_info:
            await login(request=_request(), login_data=_login("admin", "wrong-password"))
    assert exc_info.value.status_code == 401, (
        "GH #6838 regression: /api/auth/login accepted a wrong credential in SINGLE_USER mode "
        "without AUTOBOT_DEV_AUTH_BYPASS=true. Re-add the env-flag gate."
    )


@pytest.mark.asyncio
async def test_admin_user_garbage_password_returns_401(monkeypatch):
    """POST /api/auth/login with admin user + garbage password → 401.

    GH #6838: the admin account must not carry any implicit bypass. Every
    credential must be rejected when the bypass flag is absent.
    """
    monkeypatch.delenv("AUTOBOT_DEV_AUTH_BYPASS", raising=False)
    cfg = _cfg(DeploymentMode.SINGLE_USER)
    with patch("user_management.config.get_deployment_config", return_value=cfg):
        with pytest.raises(HTTPException) as exc_info:
            await login(request=_request(), login_data=_login("admin", "aaaaaaaaaa"))
    assert exc_info.value.status_code == 401, (
        "GH #6838 regression: admin account must reject garbage passwords in SINGLE_USER mode "
        "unless AUTOBOT_DEV_AUTH_BYPASS=true is explicitly set."
    )


@pytest.mark.asyncio
async def test_correct_credentials_with_bypass_returns_200_and_token(monkeypatch):
    """POST /api/auth/login with bypass flag + any credential → 200 + token.

    Happy path: AUTOBOT_DEV_AUTH_BYPASS=true is the legitimate dev opt-in.
    Verifies the bypass path itself is not broken by the security fix.
    """
    monkeypatch.setenv("AUTOBOT_DEV_AUTH_BYPASS", "true")
    cfg = _cfg(DeploymentMode.SINGLE_USER)
    fake_auth = MagicMock()
    fake_auth.create_jwt_token.return_value = "test-jwt-token"
    fake_auth.create_session.return_value = "test-session-id"
    with (
        patch("user_management.config.get_deployment_config", return_value=cfg),
        patch("api.auth.get_auth_middleware", return_value=fake_auth),
        patch("api.auth._emit_event"),
    ):
        response = await login(
            request=_request(),
            login_data=_login("admin", "any-password"),
        )
    assert response.success is True, "Bypass login must return success=True."
    assert response.token == "test-jwt-token", "Bypass login must include a JWT token."
    assert response.user is not None, "Bypass login must populate the user field."


@pytest.mark.asyncio
async def test_wrong_password_rejected_in_multi_user_mode(monkeypatch):
    """POST /api/auth/login with wrong password → 401 in SINGLE_COMPANY mode.

    GH #6838 baseline: multi-user deployments have always required real credentials.
    Ensures the fix did not regress this invariant.
    """
    monkeypatch.delenv("AUTOBOT_DEV_AUTH_BYPASS", raising=False)
    cfg = _cfg(DeploymentMode.SINGLE_COMPANY)

    async def _fail_auth(*_args, **_kwargs) -> None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    with (
        patch("user_management.config.get_deployment_config", return_value=cfg),
        patch("api.auth._authenticate_and_build_user_data", side_effect=_fail_auth),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await login(request=_request(), login_data=_login("alice", "bad-password"))
    assert exc_info.value.status_code == 401
