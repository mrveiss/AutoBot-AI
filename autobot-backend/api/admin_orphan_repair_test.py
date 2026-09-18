# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The orphan-repair admin routes: admin-only, refused unless genuinely orphaned, every attempt audited (#15779, #16927).

A fake repairer stands in for the per-type services (tested on their own in
``services/orphan_repair_test.py`` and, for envelope secrets, the migration gate)
so these tests judge the route and the break-glass rules, not a store.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.admin_orphan_repair as route
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from services.orphan_repair import Assessment

LIVE_USER = str(uuid.uuid4())
_ADMIN = {"username": "admin", "role": "admin", "user_id": "admin-1"}


class _Session:
    """Only what the break-glass reads: a user by id. LIVE_USER exists; nobody else does."""

    async def get(self, _model, key):
        return SimpleNamespace(deleted_at=None) if str(key) == LIVE_USER else None


class _Repairer:
    def __init__(self, orphaned: bool) -> None:
        self.orphaned = orphaned
        self.repaired = False

    async def assess(self, session, resource_id):
        return Assessment(self.orphaned, {"owner": "deleted" if self.orphaned else "live", "scope": "x"})

    async def repair(self, session, resource_id, new_owner_id, assessment):
        self.repaired = True
        return {"before": {"owner_id": "gone"}, "after": {"owner_id": new_owner_id}}

    async def find_orphans(self, session, limit):
        return [{"resource_id": "r-1", "conditions": {"owner": "deleted"}}] if self.orphaned else []


def _client(user=_ADMIN) -> TestClient:
    app = FastAPI()
    app.include_router(route.router, prefix="/api")
    app.dependency_overrides[get_db_session] = lambda: _Session()
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture
def audit():
    auth = MagicMock()
    auth.get_user_from_request.return_value = _ADMIN
    with (
        patch("auth_rbac.get_auth_middleware", return_value=auth),
        patch("services.orphan_repair.audit_log", new=AsyncMock(return_value=True)) as audit_log,
    ):
        yield audit_log


def _repair(resource_type="fake", new_owner=LIVE_USER):
    body = {"resource_type": resource_type, "resource_id": "r-1", "new_owner_id": new_owner}
    return _client().post("/api/admin/orphans/repair", json=body)


def test_an_orphan_is_repaired_and_the_audit_records_why(audit):
    fake = _Repairer(orphaned=True)
    with patch.dict(route.REPAIRERS, {"fake": fake}):
        response = _repair()

    assert response.status_code == 201, response.text
    assert response.json()["conditions"] == {"owner": "deleted", "scope": "x"}
    assert fake.repaired
    assert audit.await_args.kwargs["result"] == "success"
    assert audit.await_args.kwargs["details"]["conditions"] == {"owner": "deleted", "scope": "x"}


def test_the_negative_control_a_reachable_resource_is_refused_and_audited(audit):
    """bb's review of #16927: the repair granted unconditionally. A reachable resource must be refused."""
    fake = _Repairer(orphaned=False)
    with patch.dict(route.REPAIRERS, {"fake": fake}):
        response = _repair()

    assert response.status_code == 409
    assert response.json()["detail"]["conditions"]["owner"] == "live"
    assert not fake.repaired
    assert audit.await_args.kwargs["result"] == "denied"


def test_an_unknown_resource_type_is_refused_and_audited(audit):
    response = _repair(resource_type="widget")

    assert response.status_code == 400
    assert audit.await_args.kwargs["details"]["refused"] == "UnknownResourceType"


def test_the_new_owner_must_be_a_live_user(audit):
    with patch.dict(route.REPAIRERS, {"fake": _Repairer(orphaned=True)}):
        response = _repair(new_owner=str(uuid.uuid4()))

    assert response.status_code == 400
    assert audit.await_args.kwargs["details"]["refused"] == "InvalidNewOwner"


def test_a_non_admin_is_refused_before_anything_is_judged(audit):
    auth = MagicMock()
    auth.get_user_from_request.return_value = {"username": "u2", "role": "user", "user_id": "u2"}
    with (
        patch("auth_rbac.get_auth_middleware", return_value=auth),
        patch.dict(route.REPAIRERS, {"fake": _Repairer(True)}),
    ):
        body = {"resource_type": "fake", "resource_id": "r-1", "new_owner_id": LIVE_USER}
        response = _client({"username": "u2", "role": "user", "user_id": "u2"}).post(
            "/api/admin/orphans/repair", json=body
        )

    assert response.status_code in (401, 403)
    audit.assert_not_awaited()


def test_orphans_are_listed_with_their_conditions(audit):
    with patch.dict(route.REPAIRERS, {"fake": _Repairer(orphaned=True)}):
        response = _client().get("/api/admin/orphans", params={"resource_type": "fake"})

    assert response.status_code == 200
    assert response.json()["orphans"] == [{"resource_id": "r-1", "conditions": {"owner": "deleted"}}]
