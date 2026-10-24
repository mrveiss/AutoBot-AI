# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An unset AUTOBOT_FRONTEND_SERVED_BY leaves no origin to compare: redirects are refused, not guessed (#19326)."""

import pytest
from fastapi import HTTPException

from api import provider_auth_scope as scope
from autobot_shared.ssot_config import AutoBotConfig

_CALLBACK = scope.PROVIDER_OAUTH_CALLBACK_PATH


def _cfg(monkeypatch: pytest.MonkeyPatch, served_by: str | None) -> AutoBotConfig:
    monkeypatch.setenv("AUTOBOT_FRONTEND_HOST", "ui.example.test")
    monkeypatch.setenv("AUTOBOT_FRONTEND_TLS_ENABLED", "true")
    if served_by is None:
        monkeypatch.delenv("AUTOBOT_FRONTEND_SERVED_BY", raising=False)
    else:
        monkeypatch.setenv("AUTOBOT_FRONTEND_SERVED_BY", served_by)
    return AutoBotConfig(_env_file=None)


def test_unset_refuses_every_redirect_with_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scope, "config", _cfg(monkeypatch, None))
    with pytest.raises(HTTPException) as err:
        scope.validate_redirect_uri(f"https://ui.example.test:443{_CALLBACK}")
    assert err.value.status_code == 503


def test_nginx_accepts_the_served_origin_and_refuses_the_dev_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scope, "config", _cfg(monkeypatch, "nginx"))
    scope.validate_redirect_uri(f"https://ui.example.test{_CALLBACK}")  # 443 is the https default
    with pytest.raises(HTTPException) as err:
        scope.validate_redirect_uri(f"http://ui.example.test:5173{_CALLBACK}")
    assert err.value.status_code == 400
