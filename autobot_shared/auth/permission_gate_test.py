# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one ``require_permission`` / ``require_any_permission`` (#18263): 401, 403 + audit, enum-only."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from autobot_shared.auth import permission_gate
from autobot_shared.auth.permission_gate import PermissionGate
from autobot_shared.auth.permissions import Permission

_REQUEST = SimpleNamespace(url=SimpleNamespace(path="/x"), client=None, headers={})


def _gate(loader=None):
    return PermissionGate(lambda: None, load_db_names=loader or AsyncMock(return_value=[]))


@pytest.fixture
def audit():
    with patch.object(permission_gate, "audit_permission_denied", AsyncMock()) as mock:
        yield mock


async def test_an_allowed_caller_is_returned_and_not_audited(audit):
    caller = {"role": "admin", "sub": "a"}
    assert await _gate().require_permission(Permission.ADMIN_SYSTEM)(request=_REQUEST, caller=caller) is caller
    audit.assert_not_awaited()


async def test_a_denied_caller_is_audited_then_403(audit):
    with pytest.raises(HTTPException) as exc:
        await _gate().require_permission(Permission.ADMIN_SYSTEM)(request=_REQUEST, caller={"role": "user"})
    assert exc.value.status_code == 403
    audit.assert_awaited_once_with(_REQUEST, {"role": "user"}, (Permission.ADMIN_SYSTEM,))


@pytest.mark.parametrize("caller", [None, {}, "token"])
async def test_no_caller_is_401_and_not_audited(audit, caller):
    with pytest.raises(HTTPException) as exc:
        await _gate().require_permission(Permission.API_READ)(request=_REQUEST, caller=caller)
    assert exc.value.status_code == 401
    audit.assert_not_awaited()


async def test_any_allows_on_one_held_permission(audit):
    dep = _gate().require_any_permission(Permission.ADMIN_SYSTEM, Permission.CHAT_USE)
    assert await dep(request=_REQUEST, caller={"role": "user"})


async def test_a_db_grant_opens_the_gate(audit):
    loader = AsyncMock(return_value=["admin.system"])
    caller = {"role": "user", "user_id": "00000000-0000-0000-0000-000000000001"}
    assert await _gate(loader).require_permission(Permission.ADMIN_SYSTEM)(request=_REQUEST, caller=caller)


@pytest.mark.parametrize("bad", ["admin.system", None])
def test_contrast_a_string_fails_when_the_dependency_is_built(bad):
    with pytest.raises(TypeError, match="Permission member"):
        _gate().require_permission(bad)
    with pytest.raises(TypeError, match="Permission member"):
        _gate().require_any_permission(Permission.API_READ, bad)


def test_any_needs_at_least_one_permission():
    with pytest.raises(ValueError):
        _gate().require_any_permission()


def test_the_wiring_hook_runs_before_a_deny_audit(audit):
    calls = []
    gate = PermissionGate(lambda: {"role": "user"}, wire_rbac=lambda: calls.append("wired"))
    app = FastAPI()

    @app.get("/admin")
    async def admin(request: Request, caller: dict = Depends(gate.require_permission(Permission.ADMIN_SYSTEM))):
        return caller

    assert TestClient(app).get("/admin").status_code == 403
    assert calls == ["wired"]


def _broken_wiring():
    raise ModuleNotFoundError("user_management.middleware")


async def test_a_deny_whose_audit_cannot_be_written_is_still_403(caplog):
    """#18338 train 12b: the wiring import on the deny path failed and turned the 403 into a 500."""
    gate = PermissionGate(lambda: None, wire_rbac=_broken_wiring)
    with pytest.raises(HTTPException) as exc:
        await gate.require_permission(Permission.ADMIN_SYSTEM)(request=_REQUEST, caller={"role": "user"})
    assert exc.value.status_code == 403
    assert "deny audit not written (ModuleNotFoundError)" in caplog.text


async def test_unavailable_wiring_grants_no_db_permissions():
    """Fail closed: a DB-granted caller is denied, not 500'd, when RBAC wiring cannot load."""
    loader = AsyncMock(return_value=["admin.system"])
    gate = PermissionGate(lambda: None, wire_rbac=_broken_wiring, load_db_names=loader)
    caller = {"role": "user", "user_id": "00000000-0000-0000-0000-000000000001"}
    with pytest.raises(HTTPException) as exc:
        await gate.require_permission(Permission.ADMIN_SYSTEM)(request=_REQUEST, caller=caller)
    assert exc.value.status_code == 403
    loader.assert_not_awaited()
