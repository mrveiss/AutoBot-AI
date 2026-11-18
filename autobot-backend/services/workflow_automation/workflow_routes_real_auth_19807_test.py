# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The workflow routes that start shell commands are judged by the REAL gate (#19807).

Under pytest ``auth_middleware`` is a stub, so overriding ``get_current_user`` would hide which
function a route depends on. These tests execute a FRESH copy of each router with the real
``auth_middleware`` bound as the import (the way ``admin_gate_canonical_18688_test`` does) and
fake only the identity the real ``get_current_user`` reads.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from tests.conftest import load_real_auth_middleware

_BACKEND = Path(__file__).resolve().parents[2]
_ADMIN = {"user_id": "u-1", "role": "admin"}


@pytest.fixture
def identity(monkeypatch):
    """The user the real ``get_current_user`` sees; set ``identity.user`` per test."""
    real = load_real_auth_middleware()
    state = SimpleNamespace(user=None)
    middleware = SimpleNamespace(
        get_user_from_request=lambda _request: state.user,
        _extract_user_from_run_jwt=AsyncMock(return_value=None),
        _extract_user_from_device_jwt=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(real, "get_auth_middleware", lambda: middleware)
    monkeypatch.setitem(sys.modules, "auth_middleware", real)
    import security.human_admin as human_admin

    monkeypatch.setattr(human_admin, "auth_middleware", real)
    return state


def _fresh(dotted: str, alias: str):
    """Execute ``<dotted>.py`` under *alias*, importing the (patched-in) real ``auth_middleware``."""
    path = _BACKEND / (dotted.replace(".", "/") + ".py")
    spec = importlib.util.spec_from_file_location(alias, path, submodule_search_locations=None)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def workflow_client(identity, monkeypatch):
    """The workflow-automation router with the real gate, and what its manager was asked to create."""
    module = _fresh("services.workflow_automation.routes", "services.workflow_automation._routes_real_19807")
    created = []

    class _Manager:
        async def create_automated_workflow(self, **kwargs):
            created.append(kwargs)
            return "wf-1"

        async def create_workflow_from_chat_request(self, *args, **kwargs):
            created.append(kwargs)
            return None

    monkeypatch.setattr(module, "get_workflow_manager", lambda: _Manager())
    app = FastAPI()
    app.include_router(module.router)
    client = TestClient(app, raise_server_exceptions=False)
    client.created = created
    return client


@pytest.fixture
def export_client(identity):
    module = _fresh("api.workflow_export", "_workflow_export_real_19807")
    app = FastAPI()
    app.include_router(module.router)
    return TestClient(app, raise_server_exceptions=False)


_CREATE = ("/create_workflow", {"name": "w", "description": "", "steps": [], "session_id": "s"})
_CHAT = ("/create_from_chat", {"user_request": "list files", "session_id": "s"})


@pytest.mark.parametrize("role", ["user", "operator", "run_jwt", None])
@pytest.mark.parametrize("path,body", [_CREATE, _CHAT])
def test_only_an_administrator_may_create_a_command_workflow(workflow_client, identity, path, body, role):
    identity.user = {"user_id": "u-1", "role": role}
    assert workflow_client.post(path, json=body).status_code == 403
    assert workflow_client.created == []


@pytest.mark.parametrize("path,body", [_CREATE, _CHAT])
def test_an_administrator_can_create_a_command_workflow(workflow_client, identity, path, body):
    identity.user = dict(_ADMIN)
    assert workflow_client.post(path, json=body).status_code == 200


def test_create_from_chat_reports_a_missing_field_as_400_not_500(workflow_client, identity):
    identity.user = dict(_ADMIN)
    response = workflow_client.post("/create_from_chat", json={"user_request": "", "session_id": "s"})
    assert response.status_code == 400
    assert workflow_client.created == []


def test_the_creator_cannot_remove_the_confirmation_gate(workflow_client, identity):
    identity.user = dict(_ADMIN)
    steps = [{"command": "echo hi", "description": "d", "requires_confirmation": False}]
    assert workflow_client.post(_CREATE[0], json={**_CREATE[1], "steps": steps}).status_code == 200
    assert all(step.requires_confirmation for step in workflow_client.created[0]["steps"])


@pytest.mark.parametrize("role", ["user", "operator", None])
def test_import_needs_an_administrator(export_client, identity, role):
    identity.user = {"user_id": "u-1", "role": role}
    doc = {"export_document": {}, "session_id": "s"}
    assert export_client.post("/import", json=doc).status_code == 403


@pytest.mark.parametrize("role", ["user", "operator", None])
def test_cloning_a_shared_workflow_needs_an_administrator(export_client, identity, role):
    """``clone_shared_workflow`` runs the cloned shell steps, so it is closed to non-administrators."""
    identity.user = {"user_id": "u-1", "role": role}
    assert export_client.post("/share/abc/clone", json={"session_id": "s"}).status_code == 403
