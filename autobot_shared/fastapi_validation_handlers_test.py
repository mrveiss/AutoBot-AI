# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""FastAPI's default 422 body echoes the submitted payload -- fixed once, for
every app that can import autobot_shared (#16428 security review).

Reproduces the two concrete leaks the review found in `SecretCreateRequest`:
a model-level validator failing with the full body still attached to Pydantic
v2's error dict, and a field-level `max_length` violation whose `input` is the
oversized value itself. A password-shaped field stands in for the review's
concrete cross-app finding (`UserCreate.password`, `VNCCredentialCreate.password`
on autobot-slm-backend) since this module is shared, not tied to one app's model.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, model_validator

from autobot_shared.fastapi_validation_handlers import register_validation_error_handlers

_LEAKED_MARKER = "not-a-real-value-but-must-never-appear-in-a-422"  # pragma: allowlist secret


class _PasswordLikeRequest(BaseModel):
    """A password-shaped field plus a cross-field validator, standing in for
    both concrete cases the review found (SecretCreateRequest's connector
    bridge, UserCreate/VNCCredentialCreate's password)."""

    username: str | None = None
    password: str | None = Field(None, max_length=16)
    requires_2fa: bool = False

    @model_validator(mode="after")
    def _require_username_with_password(self) -> "_PasswordLikeRequest":
        if self.password is not None and self.username is None:
            raise ValueError("password requires username")
        return self


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_validation_error_handlers(app)

    @app.post("/account")
    async def _create(body: _PasswordLikeRequest):
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=False)


def test_a_model_validator_failure_never_echoes_the_password(client: TestClient):
    response = client.post("/account", json={"password": _LEAKED_MARKER})

    assert response.status_code == 422
    assert _LEAKED_MARKER not in response.text
    assert "input" not in response.text  # the key itself must be gone, not just this value
    body = response.json()
    assert body["detail"][0]["msg"]
    assert body["detail"][0]["type"]


def test_a_max_length_violation_never_echoes_the_oversized_password(client: TestClient):
    oversized = _LEAKED_MARKER * 3
    response = client.post("/account", json={"username": "u", "password": oversized})

    assert response.status_code == 422
    assert _LEAKED_MARKER not in response.text
    assert "input" not in response.text


def test_the_response_still_says_where_and_why_it_failed(client: TestClient):
    """The fix must not turn every 422 into an unusable opaque blob."""
    response = client.post("/account", json={"password": "x"})

    detail = response.json()["detail"]
    assert detail
    assert detail[0]["loc"] == ["body"]  # model-level error: no specific field beyond the body itself
    assert "username" in detail[0]["msg"]
