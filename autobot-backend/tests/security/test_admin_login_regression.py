# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for /api/auth/login credential validation.

AutoBot always runs full, Postgres-backed user management (#10636). Every login
is authenticated against the Postgres user store; a wrong password returns 401.
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
        postgres_enabled=True,
    )


def _request():
    req = MagicMock()
    req.client.host = "127.0.0.1"
    return req


def _login(username: str, password: str) -> LoginRequest:
    return LoginRequest(username=username, password=password)


@pytest.mark.asyncio
async def test_wrong_password_rejected_in_single_company_mode():
    """POST /api/auth/login with wrong password → 401 in SINGLE_COMPANY mode.

    Postgres-backed deployments always require real credentials.
    """
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
