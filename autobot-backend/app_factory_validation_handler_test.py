# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""app_factory's real exception-handler wiring never echoes a secret in a 422
(#16428 security review).

Calls `_register_exception_handlers` -- the exact function `create_fastapi_app`
runs -- on a fresh `FastAPI()` rather than building the full app (heavy: DB,
Redis, every router). This tests the wiring app_factory itself owns, not the
handler's own logic (covered directly in
`autobot_shared/fastapi_validation_handlers_test.py`).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, model_validator

_LEAKED_MARKER = "not-a-real-value-but-must-never-appear-in-a-422"  # pragma: allowlist secret


class _PasswordLikeRequest(BaseModel):
    username: str | None = None
    password: str | None = Field(None, max_length=16)

    @model_validator(mode="after")
    def _require_username_with_password(self) -> "_PasswordLikeRequest":
        if self.password is not None and self.username is None:
            raise ValueError("password requires username")
        return self


@pytest.fixture
def client() -> TestClient:
    from app_factory import _register_exception_handlers

    app = FastAPI()
    _register_exception_handlers(app)

    @app.post("/account")
    async def _create(body: _PasswordLikeRequest):
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=False)


def test_app_factorys_own_wiring_never_echoes_a_password_in_a_422(client: TestClient):
    response = client.post("/account", json={"password": _LEAKED_MARKER})

    assert response.status_code == 422
    assert _LEAKED_MARKER not in response.text
    assert "input" not in response.text
    assert "ctx" not in response.text
