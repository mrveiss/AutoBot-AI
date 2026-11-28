# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The resume route records the verified calling admin as approver, not a literal (#21119)."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.budget_policies as bp
import auth_middleware as _stub_auth

_URL = "/api/budget-policies/a1/resume"


@pytest.fixture
def client(real_auth_middleware, monkeypatch):
    identity = SimpleNamespace(user=None)
    seen: list = []

    async def _no_token(_request):
        return None

    middleware = SimpleNamespace(
        get_user_from_request=lambda _request: identity.user,
        _extract_user_from_run_jwt=_no_token,
        _extract_user_from_device_jwt=_no_token,
    )
    monkeypatch.setattr(real_auth_middleware, "get_auth_middleware", lambda: middleware)

    async def _resume(agent_id, approved_by):
        seen.append((agent_id, approved_by))
        return True

    monkeypatch.setattr(bp, "resume_agent", _resume)
    app = FastAPI()
    app.include_router(bp.router, prefix="/api")
    app.dependency_overrides[_stub_auth.check_admin_permission] = real_auth_middleware.check_admin_permission
    app.dependency_overrides[bp.get_current_user] = real_auth_middleware.get_current_user
    return TestClient(app), identity, seen


def test_resume_records_calling_admin_id(client) -> None:
    test_client, identity, seen = client
    identity.user = {"id": "u-42", "username": "alice", "role": "admin"}
    assert test_client.post(_URL, json={"approved_by": "mallory"}).status_code == 200
    assert seen == [("a1", "u-42")]


def test_resume_falls_back_to_username_when_no_id(client) -> None:
    test_client, identity, seen = client
    identity.user = {"username": "root", "role": "admin"}
    assert test_client.post(_URL).status_code == 200
    assert seen == [("a1", "root")]


def test_resume_never_records_placeholder(client) -> None:
    test_client, identity, seen = client
    identity.user = {"sub": "sub-7", "username": "bob", "role": "admin"}
    test_client.post(_URL)
    assert seen[0][1] not in ("admin", "system", "")
