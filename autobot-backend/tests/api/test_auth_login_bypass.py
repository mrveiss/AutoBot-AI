# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for #6838 — /api/auth/login admin auth bypass.

Before the fix, single_user mode (the default) accepted ANY non-empty value
for the synthetic admin user's credential and returned a 31-year admin JWT.
Anyone with network reach to the SLM Manager could mint admin tokens.

The fix gates that synthetic-admin shortcut behind an explicit
AUTOBOT_DEV_AUTH_BYPASS=true environment flag. Without the flag, the login
endpoint refuses to mint tokens in single_user mode (401), matching production
behavior.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from api.auth import _dev_auth_bypass_enabled, login
from api.schemas_agent import LoginRequest
from user_management.config import DeploymentConfig, DeploymentMode, FeatureFlags


def _make_deploy_cfg(mode: DeploymentMode) -> DeploymentConfig:
    return DeploymentConfig(
        mode=mode,
        features=FeatureFlags(),
        postgres_enabled=mode != DeploymentMode.SINGLE_USER,
    )


def _make_request() -> MagicMock:
    request = MagicMock()
    request.client.host = "127.0.0.1"
    return request


def _login_req(user: str, pw: str) -> LoginRequest:
    return LoginRequest(username=user, password=pw)


class TestDevAuthBypassFlag:
    @pytest.mark.parametrize("raw", ["true", "TRUE", "1", "yes", "on"])
    def test_truthy_values_enable_bypass(self, raw, monkeypatch):
        monkeypatch.setenv("AUTOBOT_DEV_AUTH_BYPASS", raw)
        assert _dev_auth_bypass_enabled() is True

    @pytest.mark.parametrize("raw", ["", "false", "0", "no", "off", "garbage"])
    def test_falsey_or_unset_disables_bypass(self, raw, monkeypatch):
        monkeypatch.setenv("AUTOBOT_DEV_AUTH_BYPASS", raw)
        assert _dev_auth_bypass_enabled() is False

    def test_unset_disables_bypass(self, monkeypatch):
        monkeypatch.delenv("AUTOBOT_DEV_AUTH_BYPASS", raising=False)
        assert _dev_auth_bypass_enabled() is False


class TestSingleUserLoginRejectsWithoutBypass:
    @pytest.mark.asyncio
    async def test_short_value_rejected_when_bypass_disabled(self, monkeypatch):
        monkeypatch.delenv("AUTOBOT_DEV_AUTH_BYPASS", raising=False)
        cfg = _make_deploy_cfg(DeploymentMode.SINGLE_USER)
        with patch("user_management.config.get_deployment_config", return_value=cfg):
            with pytest.raises(HTTPException) as excinfo:
                await login(request=_make_request(), login_data=_login_req("admin", "x"))
        assert excinfo.value.status_code == 401

    @pytest.mark.asyncio
    async def test_other_value_rejected_when_bypass_disabled(self, monkeypatch):
        monkeypatch.delenv("AUTOBOT_DEV_AUTH_BYPASS", raising=False)
        cfg = _make_deploy_cfg(DeploymentMode.SINGLE_USER)
        with patch("user_management.config.get_deployment_config", return_value=cfg):
            with pytest.raises(HTTPException) as excinfo:
                await login(request=_make_request(), login_data=_login_req("admin", "abc"))
        assert excinfo.value.status_code == 401


class TestSingleUserLoginWithExplicitBypass:
    @pytest.mark.asyncio
    async def test_bypass_mints_admin_token_when_flag_set(self, monkeypatch):
        monkeypatch.setenv("AUTOBOT_DEV_AUTH_BYPASS", "true")
        cfg = _make_deploy_cfg(DeploymentMode.SINGLE_USER)
        fake_auth = MagicMock()
        fake_auth.create_jwt_token.return_value = "dummy-token"
        fake_auth.create_session.return_value = "dummy-session"
        with (
            patch("user_management.config.get_deployment_config", return_value=cfg),
            patch("api.auth.get_auth_middleware", return_value=fake_auth),
            patch("api.auth._emit_event"),
        ):
            response = await login(request=_make_request(), login_data=_login_req("admin", "abc"))
        assert response.success is True
        assert response.token == "dummy-token"
        assert response.user["role"] == "admin"


class TestMultiUserModeRejectsWrongPassword:
    @pytest.mark.asyncio
    async def test_wrong_value_returns_401_in_single_company(self, monkeypatch):
        monkeypatch.delenv("AUTOBOT_DEV_AUTH_BYPASS", raising=False)
        cfg = _make_deploy_cfg(DeploymentMode.SINGLE_COMPANY)

        async def _fail_auth(*args, **kwargs):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        with (
            patch("user_management.config.get_deployment_config", return_value=cfg),
            patch("api.auth._authenticate_and_build_user_data", side_effect=_fail_auth),
        ):
            with pytest.raises(HTTPException) as excinfo:
                await login(request=_make_request(), login_data=_login_req("alice", "bad"))
        assert excinfo.value.status_code == 401
