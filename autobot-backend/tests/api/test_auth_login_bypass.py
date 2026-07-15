# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for /api/auth/login credential handling.

AutoBot always runs full, Postgres-backed user management (#10636). The login
endpoint authenticates every request against the Postgres user store; an
invalid credential returns 401.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from api.auth import login
from api.schemas_agent import LoginRequest
from user_management.config import DeploymentConfig, DeploymentMode, FeatureFlags


def _make_deploy_cfg(mode: DeploymentMode) -> DeploymentConfig:
    return DeploymentConfig(
        mode=mode,
        features=FeatureFlags(),
        postgres_enabled=True,
    )


def _make_request() -> MagicMock:
    request = MagicMock()
    request.client.host = "127.0.0.1"
    return request


def _login_req(user: str, pw: str) -> LoginRequest:
    return LoginRequest(username=user, password=pw)


class TestLoginRejectsWrongPassword:
    @pytest.mark.asyncio
    async def test_wrong_value_returns_401_in_single_company(self, monkeypatch):
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
