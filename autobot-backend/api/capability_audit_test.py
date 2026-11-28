# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The capability-audit admin route: admin-only and returns the audit report (#22271)."""

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.capability_audit as route
from auth_middleware import get_current_user
from testkit.canonical_gate import real_admin_gate

_ADMIN = {"username": "admin", "role": "admin", "user_id": "admin-1"}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(route.router, prefix="/api/capability-audit")
    app.dependency_overrides[get_current_user] = lambda: _ADMIN
    return TestClient(app)


def test_a_non_admin_is_refused():
    auth = MagicMock()
    auth.get_user_from_request.return_value = {"username": "u2", "role": "user", "user_id": "u2"}

    with real_admin_gate(auth) as wire:
        response = wire(_client()).get("/api/capability-audit")

    assert response.status_code in (401, 403)


def test_admin_gets_the_audit_report():
    auth = MagicMock()
    auth.get_user_from_request.return_value = _ADMIN

    with real_admin_gate(auth) as wire:
        response = wire(_client()).get("/api/capability-audit")

    assert response.status_code == 200
    body = response.json()
    assert body["agent_count"] >= 4
    assert body["error_count"] == 0
    assert isinstance(body["findings"], list)
