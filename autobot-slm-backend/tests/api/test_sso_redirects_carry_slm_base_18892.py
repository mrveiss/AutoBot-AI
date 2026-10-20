# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SSO redirects carry the SLM base (#18892).

`location /` on the shared vhost serves the USER frontend, so a bare
`/sso-callback` or `/login` sends the operator into the user app. Every redirect
into the SLM SPA must be prefixed with ``settings.frontend_base_path``.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_sso_auth import _load_sso_auth_with_real_endpoints  # noqa: E402


def _redirect_for(sso_auth, base: str, issue_code):
    token = MagicMock()
    token.model_dump.return_value = {"access_token": "t"}
    auth_service = MagicMock(create_token_response=AsyncMock(return_value=token))
    with (
        patch.object(sso_auth, "settings", SimpleNamespace(frontend_base_path=base)),
        patch.object(sso_auth, "auth_service", auth_service),
        patch.object(sso_auth, "issue_exchange_code", issue_code),
        patch.object(sso_auth, "RedirectResponse", lambda url, status_code: SimpleNamespace(url=url)),
    ):
        return asyncio.run(sso_auth._redirect_with_session_code(object()))


@pytest.mark.parametrize("base", ["/slm", ""])
def test_the_callback_redirect_carries_the_base(base):
    sso_auth, _ = _load_sso_auth_with_real_endpoints()
    response = _redirect_for(sso_auth, base, AsyncMock(return_value="abc"))
    assert response.url == f"{base}/sso-callback?code=abc"


def test_the_unavailable_redirect_carries_the_base():
    sso_auth, _ = _load_sso_auth_with_real_endpoints()

    class _Unavailable(Exception):
        """The loader stubs the service module, so the except clause needs a real class."""

    unavailable = AsyncMock(side_effect=_Unavailable("down"))
    with patch.object(sso_auth, "ExchangeCodeUnavailableError", _Unavailable):
        response = _redirect_for(sso_auth, "/slm", unavailable)
    assert response.url == "/slm/sso-callback?error=sso_unavailable"


def test_the_failed_login_redirect_is_under_the_base():
    sso_auth, _ = _load_sso_auth_with_real_endpoints()
    with patch.object(sso_auth, "settings", SimpleNamespace(frontend_base_path="/slm")):
        assert sso_auth._spa_url("login", "error=sso_failed") == "/slm/login?error=sso_failed"


def _settings_base_path(tmp_path, value):
    """The real Settings' frontend_base_path in a fresh interpreter (conftest stubs `config` in-process)."""
    env = {k: v for k, v in os.environ.items() if k != "SLM_FRONTEND_BASE_PATH"}
    if value is not None:
        env["SLM_FRONTEND_BASE_PATH"] = value
    env.update(
        PYTHONPATH=os.pathsep.join([str(_BACKEND_ROOT.parent), str(_BACKEND_ROOT)]),
        PYTHONDONTWRITEBYTECODE="1",
        SLM_DATA_DIR=str(tmp_path / "data"),
        SLM_CONFIG_DIR=str(tmp_path / "config"),
    )
    snippet = "import config; print('BASE=' + config.settings.frontend_base_path + '|')"
    result = subprocess.run(
        [sys.executable, "-c", snippet],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        cwd=str(tmp_path),
        env=env,
    )
    assert "BASE=" in result.stdout, result.stdout + result.stderr
    return result.stdout.split("BASE=", 1)[1].split("|", 1)[0]


def test_the_runtime_default_matches_the_spa_base(tmp_path):
    """vite.config.ts builds the SPA with base '/slm/'; the backend default must agree."""
    assert _settings_base_path(tmp_path, None) == "/slm"


@pytest.mark.parametrize(
    ("configured", "expected"),
    [("slm", "/slm"), ("/slm/", "/slm"), ("ops/slm", "/ops/slm"), ("/", ""), ("", "")],
)
def test_the_configured_base_is_normalised_to_an_absolute_path(tmp_path, configured, expected):
    """A missing leading slash would make the redirect relative to /api/auth/sso/."""
    assert _settings_base_path(tmp_path, configured) == expected
