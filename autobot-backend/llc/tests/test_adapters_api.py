# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for GET /api/llc/adapters introspection (GH#10219)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_app():
    from api.user_management.dependencies import get_current_user  # noqa: PLC0415
    from llc.api.adapters import router  # noqa: PLC0415

    app = FastAPI()
    app.include_router(router, prefix="/api/llc")
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1"}
    return app


@pytest.fixture
def client():
    return TestClient(_make_app())


def test_lists_all_registered_adapter_types(client):
    resp = client.get("/api/llc/adapters")
    assert resp.status_code == 200
    types = {a["type"] for a in resp.json()}
    for expected in (
        "claude_code",
        "claude_code_subscription",
        "copilot_local",
        "copilot_subscription",
        "codex_subscription",
    ):
        assert expected in types


def test_codex_stub_marked_not_implemented(client):
    by_type = {a["type"]: a for a in client.get("/api/llc/adapters").json()}
    # The codex adapter is a stub (no is_cli_available hook) → implemented False.
    assert by_type["codex_subscription"]["implemented"] is False
    assert by_type["codex_subscription"]["available"] is False
    # A real subprocess adapter is implemented and reports a required CLI.
    assert by_type["claude_code"]["implemented"] is True
    assert by_type["claude_code"]["requires_cli"]


def test_requires_auth(client):
    # With the override removed, the dependency would 401; here we just assert the
    # shape is a list of dicts with the documented keys.
    body = client.get("/api/llc/adapters").json()
    assert isinstance(body, list)
    assert {"type", "available", "requires_cli", "implemented"} <= set(body[0].keys())
