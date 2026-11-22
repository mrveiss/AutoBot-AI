# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``require_admin_role`` is the one admin gate (#16333), not a local role check.

It guards the feature-flag, scheduler-toggle and source-liveness routes. Under pytest
``auth_middleware`` is a stub that admits everyone, so these run the REAL
``check_admin_permission`` through ``real_admin_gate``.
"""

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.feature_flags import router
from auth_middleware import get_current_user
from services.feature_flags import get_feature_flags
from testkit.canonical_gate import no_user_middleware, real_admin_gate


def _status_as(caller):
    middleware = no_user_middleware()
    middleware.get_user_from_request.return_value = caller
    app = FastAPI()
    app.include_router(router)
    flags = AsyncMock()
    flags.get_rollout_statistics.return_value = {"mode": "enforced"}
    app.dependency_overrides[get_feature_flags] = lambda: flags
    app.dependency_overrides[get_current_user] = lambda: caller
    with real_admin_gate(middleware) as wire:
        with wire(TestClient(app, raise_server_exceptions=False)) as client:
            return client.get("/feature-flags/status")


def _caller(role):
    return {"username": "someone", "role": role, "auth_method": "session"}


def test_a_non_admin_is_refused_by_the_one_gate():
    resp = _status_as(_caller("user"))
    assert resp.status_code == 403, resp.text


def test_no_credential_is_401():
    assert _status_as(None).status_code == 401


def test_admins_pass_whatever_the_case():
    for role in ("admin", "superadmin", "Admin"):
        resp = _status_as(_caller(role))
        assert resp.status_code == 200, (role, resp.text)
