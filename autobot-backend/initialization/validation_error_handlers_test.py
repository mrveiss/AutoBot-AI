# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""FastAPI's default 422 body echoes the submitted payload -- fixed once, for
every router (#16428 security review).

Reproduces the two concrete leaks the review found in `SecretCreateRequest`:
a model-level validator failing with the full body still attached to Pydantic
v2's error dict, and a field-level `max_length` violation whose `input` is the
oversized value itself.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, model_validator

from initialization.validation_error_handlers import register_validation_error_handlers

_LEAKED_MARKER = "not-a-real-value-but-must-never-appear-in-a-422"  # pragma: allowlist secret


class _ConnectorLikeRequest(BaseModel):
    """Mirrors SecretCreateRequest's cross-field shape closely enough to
    reproduce the exact failure mode, without depending on the real model."""

    connector_id: str | None = None
    auth_type: str | None = None
    credentials: dict[str, str] | None = None
    value: str | None = Field(None, max_length=16)

    @model_validator(mode="after")
    def _require_auth_type_with_connector(self) -> "_ConnectorLikeRequest":
        if self.connector_id is not None and self.auth_type is None:
            raise ValueError("connector_id requires auth_type")
        return self


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_validation_error_handlers(app)

    @app.post("/secret")
    async def _create(body: _ConnectorLikeRequest):
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=False)


def test_a_model_validator_failure_never_echoes_the_credentials(client: TestClient):
    """The reproduced case: connector_id without auth_type used to put the
    whole body -- including a real OAuth client_secret -- into input."""
    response = client.post(
        "/secret",
        json={"connector_id": "conn-1", "credentials": {"client_secret": _LEAKED_MARKER}},
    )

    assert response.status_code == 422
    assert _LEAKED_MARKER not in response.text
    assert "input" not in response.text  # the key itself must be gone, not just this value
    body = response.json()
    assert body["detail"][0]["msg"]
    assert body["detail"][0]["type"]


def test_a_max_length_violation_never_echoes_the_oversized_value(client: TestClient):
    """The sibling case the review named: a field-level constraint's `input`
    is the value itself, not just the whole body."""
    oversized = _LEAKED_MARKER * 3
    response = client.post("/secret", json={"value": oversized})

    assert response.status_code == 422
    assert _LEAKED_MARKER not in response.text
    assert "input" not in response.text


def test_the_response_still_says_where_and_why_it_failed(client: TestClient):
    """The fix must not turn every 422 into an unusable opaque blob."""
    response = client.post("/secret", json={"connector_id": "conn-1"})

    detail = response.json()["detail"]
    assert detail
    assert detail[0]["loc"] == ["body"]  # model-level error: no specific field beyond the body itself
    assert "auth_type" in detail[0]["msg"]
