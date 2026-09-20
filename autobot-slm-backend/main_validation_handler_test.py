# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""main.py's real password-field shapes never leak through a 422 (#16428
security review).

`UserCreate.password` (`Field(..., min_length=8)`) and
`VNCCredentialCreate.password` (`Field(..., min_length=1)`), both in
`models/schemas.py`, were the two concrete plaintext fields c0's review named
on this app. `models.schemas` is globally stubbed as a MagicMock in
`conftest.py` for every other test in this suite (165 classes, several
referencing other stubbed modules like `database.NodeStatus`), so importing
the real module here would either fail on unrelated classes or -- worse --
succeed silently against the mock and validate nothing. These two mirror
only the two fields' exact constraints (required + min_length), pinned
against the real file so a constraint change here is caught by
`test_field_constraints_still_match_the_real_schemas` below. Uses the same
registration call `main.py` makes (`register_validation_error_handlers`)
against a fresh `FastAPI()` -- the handler's own logic is covered directly in
`autobot_shared/fastapi_validation_handlers_test.py`; this is the app's wiring.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from autobot_shared.fastapi_validation_handlers import register_validation_error_handlers

_LEAKED_MARKER = "not-a-real-value-but-must-never-appear-in-a-422"  # pragma: allowlist secret


class _UserCreateLike(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8)


class _VNCCredentialCreateLike(BaseModel):
    vnc_type: str = "desktop"
    password: str = Field(..., min_length=1)


def test_field_constraints_still_match_the_real_schemas():
    """Pins the mirror models to the real file's own text, so a constraint
    change on either real field is caught here instead of silently making
    the tests below check a shape that no longer exists."""
    source = (Path(__file__).parent / "models" / "schemas.py").read_text(encoding="utf-8")
    assert re.search(r"password:\s*str\s*=\s*Field\(\.\.\.,\s*min_length=8\)", source), "UserCreate.password changed"
    assert re.search(
        r"password:\s*str\s*=\s*Field\(\.\.\.,\s*min_length=1", source
    ), "VNCCredentialCreate.password changed"


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_validation_error_handlers(app)

    @app.post("/users")
    async def _create_user(body: _UserCreateLike):
        return {"ok": True}

    @app.post("/vnc-credentials")
    async def _create_vnc(body: _VNCCredentialCreateLike):
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=False)


def test_user_create_password_below_min_length_never_echoed(client: TestClient):
    """UserCreate.password requires min_length=8 -- a short real password
    submitted here must not come back in the 422."""
    response = client.post("/users", json={"username": "someone", "password": _LEAKED_MARKER[:4]})

    assert response.status_code == 422
    assert _LEAKED_MARKER[:4] not in response.text
    assert "input" not in response.text
    assert "ctx" not in response.text


def test_vnc_credential_password_missing_never_echoes_the_rest_of_the_body(client: TestClient):
    """VNCCredentialCreate.password is required -- a request missing it but
    carrying other real values must not echo those values either."""
    response = client.post("/vnc-credentials", json={"vnc_type": "nosuchtype"})

    assert response.status_code == 422
    assert "input" not in response.text
    assert "ctx" not in response.text
